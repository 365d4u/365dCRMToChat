"""One AMQP source, one serial database writer; commit before ACK."""
import json
import os
import signal
import threading
import time
from datetime import datetime

from .contracts import parse_event
from .errors import ContractError
from .writer import ChatWriter
from .environment import mysql_config
from .rabbitmq import brokers, connect_broker

QUEUE = '365dCRMToChat.snapshot.v1'
DLQ = QUEUE + '.invalid'
# Keep a small transport window without adding concurrent database writers.
PREFETCH_COUNT = 8
IO_WAIT_SECONDS = 0.25


class ProjectionFailure(Exception):
    """Reset the database session and requeue unacknowledged deliveries."""


def close(resource):
    if resource is not None:
        try:
            resource.close()
        except Exception:
            pass


def receive_with(writer, workspace_ids, role):
    def receive(channel, method, properties, body):
        started = time.monotonic()
        try:
            event = parse_event(body)
            if event.workspace_id not in workspace_ids:
                raise ContractError('workspace_not_allowed')
            parsed = time.monotonic()
            result = writer.apply(event)
        except ContractError as error:
            print(json.dumps({'event': 'rejected', 'source': role, 'code': error.code}), flush=True)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        except Exception:
            raise ProjectionFailure() from None
        # If ACK fails, the existing receipt deduplicates the committed event.
        committed = time.monotonic()
        channel.basic_ack(delivery_tag=method.delivery_tag)
        acked = time.monotonic()
        emitted = datetime.fromisoformat(event.data['emittedAt'].replace('Z', '+00:00')).timestamp()
        print(json.dumps({'event': 'projected', 'source': role, 'result': result,
            'parseMs': round((parsed - started) * 1000, 3),
            'writeMs': round((committed - parsed) * 1000, 3),
            'ackMs': round((acked - committed) * 1000, 3),
            # Snapshot creation age includes upstream Outbox delay/recovery too.
            'snapshotAgeMs': round(max(0, time.time() - emitted) * 1000, 3),
            'redelivered': bool(getattr(method, 'redelivered', False))}), flush=True)
    return receive


def subscribe(rabbit, writer, workspace_ids, exchange, role):
    channel = rabbit.channel()
    channel.exchange_declare(exchange=exchange, passive=True)
    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_declare(queue=QUEUE, durable=True,
        arguments={'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': DLQ})
    channel.queue_bind(queue=QUEUE, exchange=exchange, routing_key='crm.message.snapshot.v1')
    channel.basic_qos(prefetch_count=PREFETCH_COUNT)
    channel.basic_consume(queue=QUEUE,
        on_message_callback=receive_with(writer, workspace_ids, role), auto_ack=False)
    print(json.dumps({'event': 'ready', 'source': role, 'queue': QUEUE,
        'prefetch': PREFETCH_COUNT, 'writers': 1}), flush=True)


def run(connection_factory, amqp_url, exchange='365d.realtime.v1', workspace_ids=('1',), *,
        instance_id='', stop=None,
        rabbit_connect=connect_broker, clock=time.monotonic):
    sources = brokers(amqp_url, instance_id)
    stop = threading.Event() if stop is None else stop
    while not stop.is_set():
        database = None
        states = [{'source': source, 'connection': None, 'retry_at': 0} for source in sources]
        try:
            database = connection_factory()
            writer = ChatWriter(database)
            while not stop.is_set():
                # Pump the source before a bounded reconnect attempt.
                # Callbacks share one thread, writer and database session.
                for state in states:
                    rabbit = state['connection']
                    if rabbit is None:
                        continue
                    try:
                        if not rabbit.is_open:
                            raise ConnectionError()
                        # Wait inside the I/O loop: arriving frames wake it at once.
                        # A fixed sleep after each pump delays ACK credit/refills.
                        rabbit.process_data_events(time_limit=IO_WAIT_SECONDS)
                    except ProjectionFailure:
                        raise
                    except Exception:
                        close(rabbit)
                        state['connection'] = None
                        state['retry_at'] = clock() + 10
                        print(json.dumps({'event': 'connection_failed',
                            'source': state['source'].role, 'retrySeconds': 10}), flush=True)
                for state in states:
                    if stop.is_set():
                        break
                    if state['connection'] is not None or clock() < state['retry_at']:
                        continue
                    rabbit = None
                    try:
                        rabbit = rabbit_connect(state['source'])
                        subscribe(rabbit, writer, workspace_ids, exchange, state['source'].role)
                        state['connection'] = rabbit
                    except ProjectionFailure:
                        close(rabbit)
                        raise
                    except Exception:
                        close(rabbit)
                        state['retry_at'] = clock() + 10
                        print(json.dumps({'event': 'connection_failed',
                            'source': state['source'].role, 'retrySeconds': 10}), flush=True)
                # Connected idle time is bounded by the I/O wait above. Only
                # disconnected retries need an extra wait; never spin on failure.
                stop.wait(0 if any(s['connection'] is not None for s in states)
                          else IO_WAIT_SECONDS)
        except KeyboardInterrupt:
            return
        except Exception:
            print('{"event":"database_session_failed","retrySeconds":10}', flush=True)
        finally:
            for state in states:
                close(state['connection'])
            close(database)
        stop.wait(10)


def main():
    if os.environ.get('CRM_TO_CHAT_WRITE_ENABLED') != 'true':
        raise SystemExit('CRM_TO_CHAT_WRITE_ENABLED must explicitly be true')
    scopes = tuple(os.environ.get('CRM_TO_CHAT_WORKSPACE_IDS', '').split(','))
    if not scopes or any(not x.isascii() or not x.isdigit() or int(x) <= 0 for x in scopes):
        raise SystemExit('CRM_TO_CHAT_WORKSPACE_IDS must explicitly list allowed workspaces')
    options = dict(instance_id=os.environ.get('CRM_TO_CHAT_AMQP_INSTANCE_ID', ''))
    amqp_url = os.environ['CRM_TO_CHAT_AMQP_URL']
    brokers(amqp_url, options['instance_id'])
    import pymysql
    configuration = mysql_config(os.environ)
    def connect():
        return pymysql.connect(**configuration,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False,
            connect_timeout=10, read_timeout=30, write_timeout=30)
    stop = threading.Event()
    def request_stop(*_):
        stop.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_stop)
    run(connect, amqp_url, workspace_ids=scopes, stop=stop, **options)


if __name__ == '__main__':
    main()
