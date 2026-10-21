"""Host-only read-only checks with server-owned environment. No app imports."""
import json
import os
import pika
import pymysql
from crm_to_chat.environment import mysql_config

database = pymysql.connect(**mysql_config(os.environ), cursorclass=pymysql.cursors.DictCursor,
                           charset='utf8mb4', connect_timeout=10, read_timeout=15)
try:
    with database.cursor() as query:
        query.execute('START TRANSACTION READ ONLY')
        query.execute('SELECT COUNT(*) AS storedMessages, COUNT(DISTINCT workspace_id) AS workspaces FROM crm_contact_response')
        counts = query.fetchone()
        query.execute('SELECT COUNT(*) AS receipts FROM crm_event_receipt')
        counts.update(query.fetchone())
        database.rollback()
finally:
    database.close()
connection = pika.BlockingConnection(pika.URLParameters(os.environ['CRM_TO_CHAT_AMQP_URL']))
try:
    channel = connection.channel()
    queues = {}
    for name in ('365dCRMToChat.snapshot.v1', '365dCRMToChat.snapshot.v1.invalid'):
        method = channel.queue_declare(queue=name, passive=True).method
        queues[name] = {'ready': method.message_count, 'consumers': method.consumer_count}
finally:
    connection.close()
print(json.dumps({'databaseReachable': True, 'brokerReachable': True,
                  'databaseEnvironmentStyle': os.environ.get('CRM_TO_CHAT_DB_ENV_STYLE'),
                  'writeEnabled': os.environ.get('CRM_TO_CHAT_WRITE_ENABLED') == 'true',
                  **counts, 'queues': queues}))
