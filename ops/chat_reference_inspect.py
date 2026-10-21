"""Read-only target schema assessment, using only the server runtime config."""
import json,sys
sys.path.insert(0,'/var/www/python/chatwoot_message')
from service.database import db_manager
db=db_manager.get_connection()
try:
 with db.cursor() as q:
  q.execute('START TRANSACTION READ ONLY')
  q.execute("SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('crm_conversation_link','map_conversation_respond','respond_conv_map') ORDER BY table_name,ORDINAL_POSITION")
  columns=q.fetchall()
  q.execute('SELECT COUNT(*) AS links FROM crm_conversation_link')
  links=q.fetchone()
  q.execute('SHOW INDEX FROM crm_conversation_link')
  indexes=[{'name':r['Key_name'],'column':r['Column_name']} for r in q.fetchall()]
  q.execute("SELECT COUNT(*) AS canonical_crm FROM chatwoot_conversation_update WHERE conversation_id LIKE 'crm\\_%'")
  crm=q.fetchone()
  print(json.dumps({'columns':columns,'indexes':indexes,**links,**crm}))
  db.rollback()
finally:db.close()
