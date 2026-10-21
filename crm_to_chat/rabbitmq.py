"""Transport configuration shared by the snapshot writer and copy observer."""
from dataclasses import dataclass
import logging
import re
import ssl
from urllib.parse import unquote, urlsplit

from .errors import IntegrationError


@dataclass(frozen=True)
class Broker:
    role: str
    url: str
    instance_id: str = ''


def endpoint(url, instance_id=''):
    try:
        parsed = urlsplit(url)
        if not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError()
        if parsed.scheme != 'amqps' and not (
                parsed.scheme == 'amqp' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError()
        if instance_id and (parsed.scheme != 'amqps' or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', instance_id)):
            raise ValueError()
        if parsed.port == 0:
            raise ValueError()
        port = parsed.port or (5671 if parsed.scheme == 'amqps' else 5672)
        return parsed.scheme, parsed.hostname, port, unquote(parsed.path[1:]) if len(parsed.path) > 1 else '/'
    except (ValueError, TypeError):
        raise IntegrationError('missing_or_invalid_amqp_configuration') from None


def brokers(primary_url, instance_id=''):
    endpoint(primary_url, instance_id)
    return (Broker('primary', primary_url, instance_id),)


def connect_broker(broker):
    endpoint(broker.url, broker.instance_id)
    try:
        import pika
    except ImportError:
        raise IntegrationError('rabbitmq_dependency_not_installed') from None
    logging.getLogger('pika').setLevel(logging.CRITICAL)
    try:
        params = pika.URLParameters(broker.url)
        if broker.url.startswith('amqps://'):
            params.ssl_options = pika.SSLOptions(ssl.create_default_context(), params.host)
        params.heartbeat = 60
        params.socket_timeout = 5
        params.stack_timeout = 8
        params.blocked_connection_timeout = 10
        params.connection_attempts = 1
        params.client_properties = {'365d_connection_name': 'crm-to-chat-' + broker.role}
        if broker.instance_id:
            params.client_properties.update({
                'connection_name': '{__' + broker.instance_id + '__}',
                'aliyun_rabbitmq_instance_id': broker.instance_id,
            })
        return pika.BlockingConnection(params)
    except Exception:
        raise IntegrationError('rabbitmq_connection_failed') from None
