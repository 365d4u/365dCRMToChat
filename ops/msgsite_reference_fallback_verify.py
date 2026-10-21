"""Read-only real identity checks and actual template rendering; no app import."""
import importlib.util,json,os,sys
from pathlib import Path
from flask import Flask,render_template
root=Path('/var/www/python/chatwoot_message')
stage=Path(os.environ.get('MSGSITE_IDENTITY_STAGE',str(root)))
sys.path.insert(0,str(root))
from service.database import db_manager
spec=importlib.util.spec_from_file_location('identity_verify',stage/'service/crm_identity.py')
identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)
db=db_manager.get_connection()
try:
 with db.cursor() as q:
  q.execute('START TRANSACTION READ ONLY')
  q.execute('SELECT verified,COUNT(*) AS n FROM crm_respond_customer_link GROUP BY verified')
  reference_counts=q.fetchall()
  q.execute('SELECT verified,COUNT(*) AS n FROM crm_conversation_link GROUP BY verified')
  history_counts=q.fetchall()
  expected={'rd_429120621':'3755','115195':'7007','rd_457693542':'20384'}
  q.execute('SELECT conversation_id FROM chatwoot_conversation_update WHERE conversation_id IN (%s,%s,%s,%s,%s)',
            tuple(expected)+('174800','175409'))
  rows=identity.decorate_rows(q,q.fetchall())
  for row in rows:
   cid=expected.get(str(row['conversation_id']))
   if cid and row['crm_customer_id']!=cid:raise RuntimeError('real_sample_CRM_owner_mismatch')
   if str(row['conversation_id']) in ('174800','175409') and (row['crm_url'] or row['respond_url']):
    raise RuntimeError('unproven_numeric_identity_was_guessed')
  if not all(any(str(row['conversation_id'])==conv for row in rows) for conv in expected):
   raise RuntimeError('expected_real_history_missing')
  q.execute("SELECT u.conversation_id FROM chatwoot_conversation_update u LEFT JOIN crm_conversation_link l ON l.conversation_id=u.conversation_id AND l.verified=1 "
            "LEFT JOIN crm_respond_customer_link r ON r.respond_id=SUBSTRING(u.conversation_id,4) AND r.verified=1 "
            "WHERE u.conversation_id LIKE 'rd\\_%' AND l.conversation_id IS NULL AND r.respond_id IS NULL LIMIT 20")
  candidates=identity.decorate_rows(q,q.fetchall())
  fallback=next((r for r in candidates if r['respond_url'] and not r['crm_url']),None)
  if fallback is None:raise RuntimeError('no_real_explicit_fallback_available')
  canonical=identity.decorate({'conversation_id':'crm_3755'},respond_id='429120621')
  if canonical['respond_url']:raise RuntimeError('canonical_CRM_fell_back')
  rows.extend([fallback,canonical])
  resolutions=[{k:row[k] for k in ('conversation_id','crm_customer_id','respond_customer_id')} for row in rows]
 db.rollback()
finally:db.close()
app=Flask('msgsite_identity_verify',template_folder=str(stage/'templates'))
# The stage has only replaced templates; use unchanged production includes too.
from jinja2 import ChoiceLoader,FileSystemLoader
app.jinja_loader=ChoiceLoader([FileSystemLoader(stage/'templates'),FileSystemLoader(root/'templates')])
checks=0
with app.test_request_context('/conversations_list'):
 for row in rows:
  row.update(no_need_reply=0,is_rd_conv=str(row['conversation_id']).startswith('rd_'))
  context=dict(no_test_mode=True,page=1,total_pages=1,all_source_type={},all_labels=[],all_groups=[],
               label_id='',search_group='',inbox_name='',
               conversation_id=row['conversation_id'],conv_info=row,conversations=[row],messages={},
               message_snapshot=None,oldest_cursor=None,newest_cursor=None)
  for template in ('conversations_list.html','conversation_detail.html'):
   html=render_template(template,**context)
   crm='Go CRM('+str(row['crm_customer_id'])+')'
   respond='Go Respond('+str(row['respond_customer_id'])+')'
   if row['crm_customer_id']:
    if crm not in html or 'Go Respond(' in html:raise RuntimeError('rendered_CRM_preference_failed')
   elif row['respond_customer_id']:
    if respond not in html or 'Go CRM(' in html:raise RuntimeError('rendered_Respond_fallback_failed')
   elif 'Go CRM(' in html or 'Go Respond(' in html:raise RuntimeError('unproven_row_has_jump')
   checks+=1
print(json.dumps({'references':reference_counts,'history':history_counts,'realResolutions':resolutions,'templateChecks':checks}))
