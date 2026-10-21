"""Small authenticated WSGI JSON gateway for the message site's backend."""

import hmac
import json

from .contracts import decode_json
from .errors import ContractError
from .media import parse_media_request

MAX_REQUEST_BYTES = 262_144


class MediaApi:
    def __init__(self, client, token: str):
        if not token or len(token) < 32:
            raise ValueError("A bridge token is required")
        self.client = client
        self.token = "Bearer " + token

    def __call__(self, environ, start_response):
        method, path = environ.get("REQUEST_METHOD"), environ.get("PATH_INFO")
        if path == "/health" and method == "GET":
            return self.respond(start_response, "200 OK", {
                "service": "365dCRMToChat", "mode": "preview", "chatDbWriteSupported": False})
        if path != "/api/media/resolve":
            return self.respond(start_response, "404 Not Found", {"error": "not_found"})
        if method != "POST":
            return self.respond(start_response, "405 Method Not Allowed", {"error": "method_not_allowed"})
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        # Encode before compare_digest so arbitrary Unicode cannot trigger a 500.
        if not hmac.compare_digest(authorization.encode("utf-8"), self.token.encode("utf-8")):
            return self.respond(start_response, "401 Unauthorized", {"error": "unauthorized"})
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.respond(start_response, "415 Unsupported Media Type", {"error": "json_required"})
        try:
            length = int(environ.get("CONTENT_LENGTH", ""))
            if not 0 < length <= MAX_REQUEST_BYTES:
                raise ValueError()
        except ValueError:
            return self.respond(start_response, "413 Payload Too Large", {"error": "invalid_body_length"})
        try:
            body = environ["wsgi.input"].read(length)
            if len(body) != length:
                raise ContractError("incomplete_request")
            resources = parse_media_request(decode_json(body, MAX_REQUEST_BYTES))
            result = self.client.resolve(resources)
            return self.respond(start_response, "200 OK", result)
        except ContractError as error:
            return self.respond(start_response, "400 Bad Request", {"error": error.code})
        except Exception:
            return self.respond(start_response, "500 Internal Server Error", {"error": "internal_error"})

    @staticmethod
    def respond(start_response, status, value):
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        start_response(status, [("Content-Type", "application/json; charset=utf-8"),
                                ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                                ("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff")])
        return [body]
