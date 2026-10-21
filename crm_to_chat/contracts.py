"""Strict, Provider-neutral snapshot contract. No legacy numeric ID mapping."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from .errors import ContractError

MAX_EVENT_BYTES = 1_048_576
MAX_DB_ID = 9_223_372_036_854_775_807


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_json_key")
        result[key] = value
    return result


def decode_json(body: bytes, maximum: int = MAX_EVENT_BYTES):
    if len(body) > maximum:
        raise ContractError("payload_too_large")
    try:
        return json.loads(
            body.decode("utf-8-sig"), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ContractError("invalid_json")),
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ContractError("invalid_json") from None


def object_fields(value, allowed: set[str], required: set[str]):
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ContractError("invalid_fields")
    return value


def string(value, maximum=256, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ContractError("invalid_string")
    return value


def db_id(value, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", value):
        raise ContractError("invalid_crm_id")
    if int(value) > MAX_DB_ID:
        raise ContractError("invalid_crm_id")
    return value


def instant(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ContractError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        raise ContractError("invalid_timestamp") from None


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SnapshotEvent:
    event_id: str
    workspace_id: str
    revision: int
    data: dict

    @property
    def message_id(self):
        return self.data["message"]["messageId"]

    @property
    def fingerprint(self):
        return digest(self.data)

    @property
    def message_fingerprint(self):
        return digest({"message": self.data["message"], "presentation": self.data.get("presentation", {})})


def parse_event(body: bytes) -> SnapshotEvent:
    data = object_fields(decode_json(body),
        {"schemaVersion", "eventType", "eventId", "workspaceId", "revision", "emittedAt", "message", "presentation"},
        {"schemaVersion", "eventType", "eventId", "workspaceId", "revision", "emittedAt", "message"})
    if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise ContractError("unsupported_schema_version")
    if data["eventType"] != "message.snapshot":
        raise ContractError("unsupported_event_type")
    event_id = string(data["eventId"], 200)
    if not event_id or any(ord(c) < 32 for c in event_id):
        raise ContractError("invalid_event_id")
    workspace = db_id(data["workspaceId"])
    revision = db_id(data["revision"])
    emitted_at = instant(data["emittedAt"])
    message = object_fields(data["message"],
        {"messageId", "conversationId", "customerId", "channelAccountId", "channel", "direction",
         "kind", "text", "occurredAt", "updatedAt", "replyToMessageId", "deleted", "attachments", "status"},
        {"messageId", "conversationId", "customerId", "channelAccountId", "channel", "direction",
         "kind", "text", "occurredAt", "updatedAt", "replyToMessageId", "deleted", "attachments"})
    normalized = dict(message)
    for key in ("messageId", "conversationId", "channelAccountId"):
        normalized[key] = db_id(message[key])
    for key in ("customerId", "replyToMessageId"):
        normalized[key] = db_id(message[key], nullable=True)
    for key in ("channel", "kind"):
        normalized[key] = string(message[key], 64)
        if not normalized[key]:
            raise ContractError("invalid_string")
    if message["direction"] not in ("inbound", "outbound"):
        raise ContractError("invalid_direction")
    if type(message["deleted"]) is not bool:
        raise ContractError("invalid_deleted_flag")
    normalized["text"] = string(message["text"], 262_144, nullable=True)
    normalized["occurredAt"] = instant(message["occurredAt"])
    normalized["updatedAt"] = instant(message["updatedAt"])
    normalized["status"] = string(message.get("status"), 64, nullable=True)
    attachments = message["attachments"]
    if not isinstance(attachments, list) or len(attachments) > 100:
        raise ContractError("invalid_attachments")
    normalized["attachments"] = []
    for index, value in enumerate(attachments):
        attachment = object_fields(value, {"index", "type", "mimeType", "fileName", "size", "availability"},
                                   {"index", "type"})
        if type(attachment["index"]) is not int or attachment["index"] != index:
            raise ContractError("invalid_attachment_index")
        size = attachment.get("size")
        if size is not None and (type(size) is not int or not 0 <= size <= MAX_DB_ID):
            raise ContractError("invalid_attachment_size")
        kind = string(attachment["type"], 64)
        if not kind:
            raise ContractError("invalid_attachment_type")
        availability = attachment.get("availability", "unknown")
        if availability not in ("available", "unavailable", "expired", "unknown"):
            raise ContractError("invalid_attachment_availability")
        normalized["attachments"].append({
            "index": index, "type": kind,
            "mimeType": string(attachment.get("mimeType"), 200, nullable=True),
            "fileName": string(attachment.get("fileName"), 255, nullable=True),
            "size": size, "availability": availability,
        })
    if normalized["deleted"] and (normalized["text"] is not None or attachments):
        raise ContractError("deleted_message_contains_content")
    canonical = {"schemaVersion": 1, "eventType": "message.snapshot", "eventId": event_id,
                 "workspaceId": workspace, "revision": revision, "emittedAt": emitted_at,
                 "message": normalized}
    if "presentation" in data:
        profile = object_fields(data["presentation"], {"customerName", "customerAvatar", "accountName"}, set())
        canonical["presentation"] = {key: string(value, 600 if key == "customerAvatar" else 255, nullable=True)
                                     for key, value in profile.items()}
    return SnapshotEvent(event_id, workspace, int(revision), canonical)


def projection(event: SnapshotEvent, crm_base_url="https://crm.365d4u.com"):
    """Presentation preview only. This is deliberately not an INSERT row."""
    message = event.data["message"]
    customer_id = message["customerId"]
    return {
        "mode": "preview", "chatDbWriteSupported": False,
        "identity": {"sourceSystem": "365d_crm", "workspaceId": event.workspace_id,
                     "messageKey": f"crm:{event.workspace_id}:message:{event.message_id}",
                     "conversationKey": f"crm_{customer_id}" if customer_id else None,
                     "crmConversationId": message['conversationId'], "crmCustomerId": customer_id},
        "revision": str(event.revision),
        "crmUrl": (f"{crm_base_url}/inbox/{customer_id}?messageId={event.message_id}" if customer_id else None),
        "message": {**message, "attachments": [
            {**attachment, "resourceId": f"message/{event.message_id}/{attachment['index']}",
             "mediaSource": f"media:message/{event.message_id}/{attachment['index']}"}
            for attachment in message["attachments"]
        ]},
    }
