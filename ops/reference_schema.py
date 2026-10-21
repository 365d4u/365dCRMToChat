"""One-time additive schema, with a server-owned schema preimage."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymysql
from crm_to_chat.environment import mysql_config
root=Path('/data/365dCRMToChat')
db=pymysql.connect(**mysql_config(os.environ),charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
try:
 with db.cursor() as q:
  q.execute("SHOW TABLES LIKE 'crm_respond_customer_link'")
  if q.fetchone():raise RuntimeError('reference_schema_already_exists; inspect before retry')
  q.execute('SHOW CREATE TABLE crm_conversation_link');before=q.fetchone()
  q.execute('SELECT COUNT(*) AS links FROM crm_conversation_link')
  links=q.fetchone()['links']
  backup=root/'state/reference-sync/schema-before-20261012.json'
  with backup.open('x',encoding='utf-8') as f:json.dump({'schema':before,'links':links},f)
  os.chmod(backup,0o600)
  for statement in (root/'migrations/chat_db_references.sql').read_text().split(';'):
   if statement.strip():q.execute(statement)
 db.commit()
 print(json.dumps({'schemaInstalled':True,'existingHistoryLinks':links,'backup':str(backup)}))
finally:db.close()
