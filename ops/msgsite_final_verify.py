"""Read-only checks after removing the retired consumer files."""
import json,os,subprocess,sys
sys.path.insert(0,'/var/www/python/chatwoot_message')
from dotenv import load_dotenv
load_dotenv('/etc/chatwoot-message-crm-media.env')
from service.database import db_manager
from service.crm_media import resolve_rows
db=db_manager.get_connection()
try:
 with db.cursor() as q:
  q.execute('START TRANSACTION READ ONLY')
  q.execute('SELECT COUNT(*) AS references_count FROM crm_respond_customer_link WHERE verified=1')
  stats=q.fetchone()
  q.execute('SELECT COUNT(*) AS historical_conversations FROM crm_conversation_link WHERE verified=1')
  stats.update(q.fetchone())
  q.execute("SELECT conversation_id,attachment FROM crm_contact_response_visible WHERE attachment IS NOT NULL AND attachment!='[]' ORDER BY update_date DESC LIMIT 1")
  row=q.fetchone()
  q.execute("SELECT crm_customer_id FROM crm_conversation_link WHERE conversation_id='193516' AND verified=1")
  sample=q.fetchone()
  db.rollback()
finally:db.close()
if not row:raise RuntimeError('no CRM attachment sample found')
resolve_rows([row])
attachments=json.loads(row['attachment'])
available=sum(str(a.get('data_url','')).startswith('https://') for a in attachments)
if not available:raise RuntimeError('CRM media sample did not resolve')
pid=subprocess.check_output(['systemctl','show','chatwoot_message','-p','MainPID','--value'],text=True).strip()
with open('/proc/'+pid+'/environ','rb') as f:env=dict(p.split(b'=',1) for p in f.read().split(b'\0') if b'=' in p)
if env.get(b'CRM_MEDIA_TOKEN',b'').decode()!=os.environ.get('CRM_MEDIA_TOKEN'):raise RuntimeError('service media configuration mismatch')
print(json.dumps({**stats,'sampleLegacyConversation':'193516','sampleCrmCustomer':str(sample['crm_customer_id']) if sample else None,
 'availableMedia':available,'runtimeMediaConfigMatches':True}))
