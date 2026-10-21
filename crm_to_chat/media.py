"""Batch JSON URL resolution. No media downloads, Provider locators or redirects."""

from dataclasses import dataclass
from http.client import HTTPException
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

from .contracts import MAX_DB_ID, decode_json, instant, object_fields, string
from .errors import ContractError, IntegrationError

CRM_BATCH_SIZE = 50
BRIDGE_BATCH_SIZE = 250
MAX_RESPONSE_BYTES = 4_194_304
CANDIDATE_KINDS = {"source", "provider", "preview", "backup", "source_backup", "linked_content", "linked_backup"}
VARIANTS = {"original", "preview", "thumbnail"}


def crm_origin(value: str) -> str:
    try:
        if any(ord(char) <= 32 or ord(char) == 127 for char in value):
            raise ValueError()
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or
                url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError()
        _ = url.port
        return value.rstrip("/")
    except ValueError:
        raise IntegrationError("invalid_crm_origin") from None


def direct_url(value):
    value = string(value, 16_384)
    try:
        url = urlsplit(value)
        if (url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or
                any(ord(char) <= 32 or ord(char) == 127 for char in value)):
            raise ValueError()
        _ = url.port
    except ValueError:
        raise ContractError("invalid_media_url") from None
    return value


@dataclass(frozen=True)
class MediaResource:
    resource_id: str
    variant: str = "original"
    excluded_candidates: tuple[str, ...] = ()
    download_name: str | None = None

    @classmethod
    def parse(cls, value):
        value = object_fields(value, {"resourceId", "variant", "excludedCandidates", "downloadName"}, {"resourceId"})
        resource_id = string(value["resourceId"], 200)
        match = re.fullmatch(r"message/([1-9][0-9]{0,18})/(0|[1-9][0-9]{0,15})", resource_id)
        if not match or int(match[1]) > MAX_DB_ID or int(match[2]) > 9_007_199_254_740_991:
            raise ContractError("invalid_media_resource_id")
        variant = value.get("variant", "original")
        if not isinstance(variant, str) or variant not in VARIANTS:
            raise ContractError("invalid_media_variant")
        excluded = value.get("excludedCandidates", [])
        if (not isinstance(excluded, list) or len(excluded) > 7 or
                any(not isinstance(kind, str) or kind not in CANDIDATE_KINDS for kind in excluded)):
            raise ContractError("invalid_excluded_candidates")
        name = value.get("downloadName")
        if "downloadName" in value:
            name = string(name, 255).strip()
            if not name or variant != "original" or any(ord(c) < 32 for c in name):
                raise ContractError("invalid_download_name")
        return cls(resource_id, variant, tuple(sorted(set(excluded))), name)

    def request(self):
        result = {"resourceId": self.resource_id, "variant": self.variant,
                  "excludedCandidates": list(self.excluded_candidates)}
        if self.download_name:
            result["downloadName"] = self.download_name
        return result


def parse_media_request(value) -> list[MediaResource]:
    value = object_fields(value, {"resources"}, {"resources"})
    resources = value["resources"]
    if not isinstance(resources, list) or not 1 <= len(resources) <= BRIDGE_BATCH_SIZE:
        raise ContractError("invalid_media_batch_size")
    return [MediaResource.parse(resource) for resource in resources]


def batches(resources):
    unique = list(dict.fromkeys(resources))
    return [unique[start:start + CRM_BATCH_SIZE] for start in range(0, len(unique), CRM_BATCH_SIZE)]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class JsonTransport:
    def __init__(self, base_url: str, token: str, timeout=10.0, endpoint_path="/api/media/resolve"):
        if endpoint_path not in {"/api/media/resolve", "/api/msgsite/media/resolve"}:
            raise IntegrationError("invalid_media_endpoint")
        self.endpoint = crm_origin(base_url) + endpoint_path
        if not token or len(token) > 8192 or not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
            raise IntegrationError("missing_or_invalid_crm_media_token")
        self.token = token
        self.timeout = timeout
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def __call__(self, resources: list[dict]):
        body = json.dumps({"resources": resources}).encode("utf-8")
        request = Request(self.endpoint, data=body, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Authorization": "Bearer " + self.token,
        })
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    raise IntegrationError("crm_media_invalid_response")
                data = response.read(MAX_RESPONSE_BYTES + 1)
                return decode_json(data, MAX_RESPONSE_BYTES)
        except HTTPError as error:
            # Do not log exception text: it can contain URLs or response contents.
            status = error.code
            error.close()
            if status in (401, 403):
                raise IntegrationError("crm_media_unauthorized") from None
            if status == 429 or status >= 500:
                raise IntegrationError("crm_media_temporarily_unavailable") from None
            raise IntegrationError("crm_media_request_rejected") from None
        except (URLError, TimeoutError, OSError, HTTPException):
            raise IntegrationError("crm_media_temporarily_unavailable") from None


def validate_response(value, requested):
    value = object_fields(value, {"items"}, {"items"})
    items = value["items"]
    if not isinstance(items, list) or len(items) != len(requested):
        raise ContractError("invalid_media_response")
    result = []
    for item, resource in zip(items, requested):
        item = object_fields(item,
            {"resourceId", "variant", "status", "candidates", "exhaustedCandidates", "retryable"},
            {"resourceId", "variant", "status", "candidates"})
        if item["resourceId"] != resource.resource_id or item["variant"] != resource.variant:
            raise ContractError("media_response_identity_mismatch")
        if item["status"] not in ("available", "unavailable", "expired"):
            raise ContractError("invalid_media_status")
        candidates = item["candidates"]
        if not isinstance(candidates, list) or len(candidates) > 7:
            raise ContractError("invalid_media_candidates")
        normalized = []
        for candidate in candidates:
            candidate = object_fields(candidate, {"kind", "url", "expiresAt", "source"},
                                      {"kind", "url", "expiresAt", "source"})
            if (not isinstance(candidate["kind"], str) or candidate["kind"] not in CANDIDATE_KINDS or
                    candidate["source"] not in ("provider", "object_storage", "import", "outbound")):
                raise ContractError("invalid_media_candidate_kind")
            if candidate["kind"] in resource.excluded_candidates:
                raise ContractError("excluded_media_candidate_returned")
            normalized.append({**candidate, "url": direct_url(candidate["url"]),
                               "expiresAt": instant(candidate["expiresAt"]) if candidate["expiresAt"] is not None else None})
        if (item["status"] == "available") != bool(normalized):
            raise ContractError("inconsistent_media_status")
        exhausted = item.get("exhaustedCandidates", [])
        if (not isinstance(exhausted, list) or len(exhausted) > 7 or
                any(not isinstance(kind, str) or kind not in CANDIDATE_KINDS for kind in exhausted)):
            raise ContractError("invalid_exhausted_candidates")
        clean = {"resourceId": resource.resource_id, "variant": resource.variant,
                 "status": item["status"], "candidates": normalized, "exhaustedCandidates": exhausted}
        if "retryable" in item:
            if type(item["retryable"]) is not bool:
                raise ContractError("invalid_retryable_flag")
            clean["retryable"] = item["retryable"]
        result.append(clean)
    return result


class MediaClient:
    def __init__(self, transport):
        self.transport = transport

    def resolve(self, resources: list[MediaResource]):
        # Revalidate even programmatic callers; resource values are never URLs.
        resources = parse_media_request({"resources": [item.request() for item in resources]})
        resolutions = {}
        for group in batches(resources):
            try:
                resolved = validate_response(self.transport([item.request() for item in group]), group)
            except IntegrationError as error:
                retryable = error.code == "crm_media_temporarily_unavailable"
                resolved = [{"resourceId": item.resource_id, "variant": item.variant,
                             "status": "unavailable", "candidates": [], "retryable": retryable,
                             "errorCode": error.code} for item in group]
            resolutions.update(zip(group, resolved))
        return {"items": [resolutions[item] for item in resources]}
