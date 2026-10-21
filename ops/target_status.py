"""Read-only deployment verification on the target host; no app imports."""
import json
import os
import sys
import pika
from dotenv import load_dotenv
load_dotenv('/var/www/python/chatwoot_message/.env')
load_dotenv('/etc/365d-crm-to-chat.env')
sys.path.insert(0,'/var/www/python/chatwoot_message')
from service.database import db_manager
database=db_manager.get_connection()
try:
 with database.cursor() as q:
  q.execute('START TRANSACTION READ ONLY')
  q.execute('SELECT COUNT(*) AS messages,COUNT(DISTINCT conversation_id) AS customers FROM crm_contact_response_visible')
  counts=q.fetchone()
  q.execute('SELECT workspace_id,COUNT(*) AS messages FROM crm_contact_response GROUP BY workspace_id')
  scopes=q.fetchall()
  q.execute("SELECT COLUMN_NAME,DATA_TYPE FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='crm_contact_response' AND column_name IN ('content','attachment','content_attribute','crm_customer_id','revision') ORDER BY COLUMN_NAME")
  types=q.fetchall()
  database.rollback()
finally:database.close()
broker=pika.BlockingConnection(pika.URLParameters(os.environ['CRM_TO_CHAT_AMQP_URL']))
try:
 channel=broker.channel()
 queues={}
 for name in ('365dCRMToChat.snapshot.v1','365dCRMToChat.snapshot.v1.invalid'):
  method=channel.queue_declare(queue=name,passive=True).method
  queues[name]={'ready':method.message_count,'consumers':method.consumer_count}
finally:broker.close()
print(json.dumps({'writeEnabled':os.environ['CRM_TO_CHAT_WRITE_ENABLED']=='true','workspaces':os.environ['CRM_TO_CHAT_WORKSPACE_IDS'],**counts,'storedScopes':scopes,'columnTypes':types,'queues':queues}))
