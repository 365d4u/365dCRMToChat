"""On target host: consume a bounded source outbox sample from private SSH stdin."""
import json
import sys
sys.path.insert(0,'/var/www/python/chatwoot_message')
from dotenv import load_dotenv
load_dotenv('/var/www/python/chatwoot_message/.env')
from service.database import db_manager
from crm_to_chat.contracts import parse_event
data=json.load(sys.stdin)
c=db_manager.get_connection()
matched=newer=missing=0
try:
 with c.cursor() as q:
  q.execute('START TRANSACTION READ ONLY')
  for value in data:
   event=parse_event(json.dumps(value,ensure_ascii=False).encode())
   q.execute('SELECT revision,snapshot_hash FROM crm_contact_response WHERE msg_id=%s AND workspace_id=%s',
             (event.message_id,event.workspace_id))
   row=q.fetchone()
   if not row:missing+=1
   elif row['revision']>event.revision:newer+=1
   elif row['revision']==event.revision and row['snapshot_hash']==event.message_fingerprint:matched+=1
   else:raise RuntimeError('CRM projection differs from source snapshot')
  c.rollback()
finally:c.close()
assert data and not missing,'Source snapshots missing at target'
print(json.dumps({'reconciled':len(data),'exactMatches':matched,'newerTargetVersions':newer,'missing':missing}))
