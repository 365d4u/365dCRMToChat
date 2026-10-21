"""Exercise staged search with read-only server connections; do not import app.py."""
import importlib.util,json,os,sys
from pathlib import Path
root=Path('/var/www/python/chatwoot_message')
staged=Path(os.getenv('MSGSITE_SEARCH_STAGE',str(root)))
sys.path.insert(0,str(root))
from service.database import db_manager
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
load('service.crm_identity',staged/'service/crm_identity.py')
module=load('search_verify_manager',staged/'service/conversation_manager.py')
manager=module.ConversationManager({})
def read_only():
 db=db_manager.get_connection()
 with db.cursor() as q:q.execute('SET SESSION TRANSACTION READ ONLY')
 return db
manager.get_db_connection=read_only
# External order lookup is separate from CRM ID resolution and not under test.
manager.search_feishu_order=lambda _:None
with read_only() as db:
 with db.cursor() as q:
  q.execute("SELECT conversation_id FROM chatwoot_conversation_update WHERE conversation_id LIKE 'crm\\_%' AND msg_count>0 ORDER BY update_date DESC LIMIT 1")
  canonical=q.fetchone()['conversation_id']
  q.execute('SELECT l.crm_customer_id FROM crm_conversation_link l JOIN chatwoot_conversation_update u ON u.conversation_id=l.conversation_id WHERE l.verified=1 AND u.msg_count>0 ORDER BY u.msg_count ASC LIMIT 1')
  row=q.fetchone()
  historical=str(row['crm_customer_id']) if row else None
cases=[('3',canonical[4:],canonical),('',canonical,canonical),('2',canonical[4:],canonical)]
if historical:cases.extend([('3',historical,None),('','crm_'+historical,None)])
cases.extend([('3','3755','rd_429120621'),('3','7007','115195'),('3','20384','rd_457693542'),('3','902','rd_496040944')])
results=[]
for mode,query,expected in cases:
 result=manager.fetch_paginated_conversations(mode,1,100,query)
 conversations=result.get('conversations',[])
 if result.get('err_msg') or not conversations:raise RuntimeError('CRM search returned no records: '+str(result.get('err_msg')))
 ids=[str(r['conversation_id']) for r in conversations]
 if expected and expected not in ids:raise RuntimeError('canonical CRM conversation missing')
 if mode=='3' and any(str(r.get('crm_customer_id'))!=query for r in conversations):
  raise RuntimeError('CRM search returned unrelated legacy owner: '+json.dumps({'query':query,'rows':[{'conversationId':r['conversation_id'],'crmCustomerId':r.get('crm_customer_id')} for r in conversations]}))
 results.append({'mode':mode,'query':query,'returned':len(ids),'canonicalFound':expected in ids if expected else None,'crmLinksValid':all(r.get('crm_url') for r in conversations)})
empty=manager.fetch_paginated_conversations('3',1,100,"crm_1' OR 1=1")
if empty.get('conversations'):raise RuntimeError('invalid CRM ID matched history')
print(json.dumps({'searchCases':results,'invalidIdReturnsNoRows':True}))
