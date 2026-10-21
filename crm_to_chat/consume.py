"""Dedicated durable queue; commit before ACK, invalid events preserved in DLQ."""
import json
import os
import ssl
import time
from .contracts import parse_event
from .errors import ContractError
from .writer import ChatWriter
from .environment import mysql_config

QUEUE = '365dCRMToChat.snapshot.v1'
DLQ = QUEUE + '.invalid'


def run(connection_factory, amqp_url, exchange='365d.realtime.v1', workspace_ids=('1',)):
    import pika
    parameters = pika.URLParameters(amqp_url)
    if parameters.ssl_options:
        parameters.ssl_options = pika.SSLOptions(ssl.create_default_context(), parameters.host)
    parameters.heartbeat = 60
    parameters.blocked_connection_timeout = 30
    while True:
        rabbit = database = None
        try:
            database = connection_factory()
            rabbit = pika.BlockingConnection(parameters)
            channel = rabbit.channel()
            channel.exchange_declare(exchange=exchange, passive=True)
            channel.queue_declare(queue=DLQ, durable=True)
            channel.queue_declare(queue=QUEUE, durable=True,
                arguments={'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': DLQ})
            channel.queue_bind(queue=QUEUE, exchange=exchange, routing_key='crm.message.snapshot.v1')
            channel.basic_qos(prefetch_count=1)
            writer = ChatWriter(database)
            def receive(ch, method, properties, body):
                try:
                    event = parse_event(body)
                    if event.workspace_id not in workspace_ids:
                        raise ContractError('workspace_not_allowed')
                    result = writer.apply(event)
                except ContractError as error:
                    print(json.dumps({'event': 'rejected', 'code': error.code}), flush=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                # Database/transport failures escape the callback; the unacked
                # delivery requeues when the connection closes. Reconnect backs off.
                ch.basic_ack(delivery_tag=method.delivery_tag)
                print(json.dumps({'event': 'projected', 'result': result}), flush=True)
            channel.basic_consume(queue=QUEUE, on_message_callback=receive, auto_ack=False)
            print('{"event":"ready","queue":"365dCRMToChat.snapshot.v1"}', flush=True)
            channel.start_consuming()
        except KeyboardInterrupt:
            return
        except Exception:
            print('{"event":"connection_failed","retrySeconds":10}', flush=True)
            time.sleep(10)
        finally:
            if database:
                try: database.close()
                except Exception: pass
            if rabbit and rabbit.is_open:
                try: rabbit.close()
                except Exception: pass


def main():
    if os.environ.get('CRM_TO_CHAT_WRITE_ENABLED') != 'true':
        raise SystemExit('CRM_TO_CHAT_WRITE_ENABLED must explicitly be true')
    import pymysql
    configuration = mysql_config(os.environ)
    def connect():
        return pymysql.connect(**configuration,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False,
            connect_timeout=10, read_timeout=30, write_timeout=30)
    scopes = tuple(os.environ.get('CRM_TO_CHAT_WORKSPACE_IDS', '').split(','))
    if not scopes or any(not x.isascii() or not x.isdigit() or int(x) <= 0 for x in scopes):
        raise SystemExit('CRM_TO_CHAT_WORKSPACE_IDS must explicitly list allowed workspaces')
    run(connect, os.environ['CRM_TO_CHAT_AMQP_URL'], workspace_ids=scopes)


if __name__ == '__main__':
    main()
