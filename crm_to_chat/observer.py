"""Observe future deliveries through an exclusive copy queue, never a business queue."""

import time
import uuid

from .contracts import parse_event
from .errors import IntegrationError
from .rabbitmq import Broker, connect_broker


def observe(connection, exchange, routing_key, store, report, *, max_messages=100, duration=60.0):
    channel = connection.channel()
    # Inspect existence only; do not create or change the CRM exchange.
    channel.exchange_declare(exchange=exchange, passive=True)
    queue = "365dCRMToChat.preview." + uuid.uuid4().hex
    channel.queue_declare(queue=queue, durable=False, exclusive=True, auto_delete=True,
                          arguments={"x-message-ttl": 60_000, "x-expires": 300_000,
                                     "x-max-length": 1000, "x-max-length-bytes": 16_777_216})
    channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
    channel.basic_qos(prefetch_count=1)
    deadline = time.monotonic() + duration
    processed = 0
    try:
        for method, _properties, body in channel.consume(queue=queue, auto_ack=False, inactivity_timeout=1):
            if method is not None:
                try:
                    event = parse_event(body)
                    outcome = store.apply(event)
                except IntegrationError as error:
                    report({"mode": "preview", "outcome": "rejected", "error": error.code})
                    # Only our temporary copy is discarded; never an original business delivery.
                    channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                else:
                    report({"mode": "preview", "eventId": event.event_id, "messageId": event.message_id,
                            "workspaceId": event.workspace_id, "revision": str(event.revision), "outcome": outcome})
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                processed += 1
            if processed >= max_messages or time.monotonic() >= deadline:
                break
    finally:
        if channel.is_open:
            channel.cancel()
    return processed


def connect(amqp_url, instance_id=''):
    return connect_broker(Broker('observer', amqp_url, instance_id))
