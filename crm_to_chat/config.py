import os
import re
from urllib.parse import urlsplit

from .errors import IntegrationError
from .media import JsonTransport, MediaClient


def enforce_preview_only(env=None):
    env = os.environ if env is None else env
    for name in ("CRM_TO_CHAT_WRITE_ENABLED", "CHAT_DB_WRITE_ENABLED"):
        if env.get(name, "false").strip().lower() not in ("", "false", "0", "no", "off"):
            raise IntegrationError("chat_db_writes_not_supported")


def media_client(env=None):
    env = os.environ if env is None else env
    enforce_preview_only(env)
    return MediaClient(JsonTransport(env.get("CRM_BASE_URL", "https://crm.365d4u.com"),
                                     env.get("CRM_MEDIA_TOKEN", "")))


def bridge_token(env=None):
    env = os.environ if env is None else env
    token = env.get("CRM_TO_CHAT_API_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9._~-]{32,8192}", token):
        raise IntegrationError("missing_or_invalid_bridge_token")
    return token


def observer_config(env=None):
    env = os.environ if env is None else env
    enforce_preview_only(env)
    value = env.get("CRM_TO_CHAT_AMQP_URL", "")
    try:
        url = urlsplit(value)
        if not url.hostname or url.fragment or url.query:
            raise ValueError()
        if url.scheme != "amqps" and not (url.scheme == "amqp" and url.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError()
        _ = url.port
    except ValueError:
        raise IntegrationError("missing_or_invalid_amqp_url") from None
    exchange = env.get("CRM_TO_CHAT_EXCHANGE", "")
    routing_key = env.get("CRM_TO_CHAT_ROUTING_KEY", "crm.message.snapshot.v1")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", exchange) or exchange.startswith("amq."):
        raise IntegrationError("named_crm_exchange_required")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", routing_key):
        raise IntegrationError("exact_snapshot_routing_key_required")
    return value, exchange, routing_key
