import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from crm_to_chat.references import SCOPE,read_snapshot,history_links,plan_import,apply_import

class ReferenceTests(unittest.TestCase):
 def snapshot(self,rows,complete=True,scope=None):
  header={'type':'header','schemaVersion':1,'scope':scope or SCOPE,'exportedAt':'2026-10-12T00:00:00Z'}
  raw=''.join(json.dumps(r)+'\n' for r in [header]+rows).encode()
  if complete:raw+=(json.dumps({'type':'footer','count':len(rows),'sha256':hashlib.sha256(raw).hexdigest()})+'\n').encode()
  folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
  path=Path(folder.name)/'refs';path.write_bytes(raw);return path

 def row(self,rid='765',cid='3001'):
  return {'type':'reference','referenceId':'1','revision':'2','customerId':cid,'respondId':rid}

 def test_complete_snapshot_with_scoped_evidence(self):
  refs,_=read_snapshot(self.snapshot([self.row()]))
  self.assertEqual(refs,{'765':('3001','1','2')})

 def test_partial_duplicate_and_wrong_scope_rejected_before_writes(self):
  for path in [self.snapshot([self.row()],False),self.snapshot([self.row(),self.row()]),
               self.snapshot([self.row()],scope={**SCOPE,'workspaceId':'2'})]:
   with self.assertRaises(ValueError):read_snapshot(path)

 def test_history_uses_respond_edges_without_numeric_or_name_guess(self):
  links,stats=history_links({'765':('3001','1','2')},{'rd_765','193516','765'},[('193516','765')])
  self.assertEqual(set(links),{'rd_765','193516'})
  self.assertEqual(links['193516'][0],'3001')
  self.assertEqual(stats['conflictingHistory'],0)

 def test_multiple_aliases_disagree_or_are_unverified(self):
  refs={'765':('3001','1','2'),'766':('3002','2','3')}
  links,stats=history_links(refs,{'11','12'},[('11','765'),('11','766'),('12','765'),('12','999')])
  self.assertEqual(links,{})
  self.assertEqual(stats,{'conflictingHistory':1,'unverifiedHistory':1})

 def test_protect_manual_history_owner(self):
  q=Mock();q.fetchall.side_effect=[[{'conversation_id':'rd_765'}],[],
   [{'conversation_id':'rd_765','crm_customer_id':3002,'verified':1,'evidence':'manual'}]]
  links,stats=plan_import(q,{'765':('3001','1','2')})
  self.assertEqual(links,{})
  self.assertEqual(stats['protectedExistingLinks'],1)

 def test_database_error_rolls_back_batch(self):
  db=Mock();q=Mock();db.cursor.return_value.__enter__=Mock(return_value=q)
  db.cursor.return_value.__exit__=Mock(return_value=False);q.fetchall.return_value=[]
  q.executemany.side_effect=RuntimeError('synthetic failure')
  with self.assertRaises(RuntimeError):apply_import(db,{'765':('3001','1','2')},{})
  db.rollback.assert_called_once();db.commit.assert_not_called()

 def database(self,old,history):
  db=Mock();q=Mock();db.cursor.return_value.__enter__=Mock(return_value=q)
  db.cursor.return_value.__exit__=Mock(return_value=False);q.fetchall.side_effect=[old,history]
  return db,q

 def old_reference(self,cid='3001',revision=2):
  return {'respond_id':'765','crm_customer_id':cid,'source_reference_id':1,'source_revision':revision,
          'verified':1,'evidence':'crm-ref:v1:1:2'}

 def test_stale_snapshot_and_same_revision_owner_change_refused(self):
  for cid,revision in [('3001',1),('3002',2)]:
   db,q=self.database([self.old_reference()],[])
   with self.assertRaises(ValueError):apply_import(db,{'765':(cid,'1',str(revision))},{})
   q.executemany.assert_not_called()

 def test_higher_revision_rebind_revokes_old_history_first(self):
  old_history=[{'conversation_id':'rd_765','crm_customer_id':'3001','verified':1,'evidence':'crm-ref:v1:old'}]
  db,q=self.database([self.old_reference()],old_history)
  counts=apply_import(db,{'765':('3002','1','3')},{'rd_765':('3002','crm-ref:v1:new')})
  self.assertTrue(q.executemany.call_args_list[0].args[0].startswith('UPDATE crm_conversation_link SET verified=0'))
  self.assertEqual(counts['revokedHistory'],1)
  self.assertEqual(counts['referenceChanges'],1)
  db.rollback.assert_not_called()

 def test_unverified_or_removed_reference_retracts_owned_link(self):
  db,q=self.database([self.old_reference()],
   [{'conversation_id':'rd_765','crm_customer_id':'3001','verified':1,'evidence':'crm-ref:v1:old'}])
  counts=apply_import(db,{'766':('3002','2','3')},{})
  self.assertEqual(counts['revokedReferences'],1)
  self.assertEqual(counts['revokedHistory'],1)

 def test_real_mysql_parameter_formatting_for_revocations_and_inserts(self):
  import pymysql
  connection=pymysql.connect(defer_connect=True,charset='utf8mb4')
  connection.server_status=0
  try:
   db,q=self.database([self.old_reference()],
    [{'conversation_id':'rd_765','crm_customer_id':'3001','verified':1,'evidence':'crm-ref:v1:old'}])
   apply_import(db,{'766':('3002','2','3')},{'rd_766':('3002','crm-ref:v1:new')})
   with connection.cursor() as actual:
    for call in q.executemany.call_args_list:
     sql,values=call.args
     for value in values:
      rendered=actual.mogrify(sql,value)
      self.assertIn('crm_',rendered)
  finally:connection.close()

class SearchIdentityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  p=Path(r'E:\PycharmProjects\chatwoot_message\service\crm_identity.py')
  spec=importlib.util.spec_from_file_location('search_identity',p)
  cls.identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.identity)

 def test_numeric_and_prefixed_crm_ids_include_only_verified_links(self):
  for query in ['3001','crm_3001','CRM_3001']:
   q=Mock();q.fetchall.return_value=[{'conversation_id':'193516'},{'conversation_id':'rd_765'}]
   self.assertEqual(self.identity.search_conversation_ids(q,query),{'crm_3001','193516','rd_765'})
   self.assertIn('verified = 1',q.execute.call_args.args[0])
   self.assertEqual(q.execute.call_args.args[1],('3001',))

 def test_invalid_ids_do_not_query_history(self):
  for query in ['crm_0','crm_01','crm_-1','crm_9223372036854775808',"crm_1' OR 1=1"]:
   q=Mock();self.assertEqual(self.identity.search_conversation_ids(q,query),set());q.execute.assert_not_called()

 def test_canonical_or_verified_crm_wins_over_respond_fallback(self):
  for row,cid in [({'conversation_id':'crm_3001','respond_conv_id':'765'},None),({'conversation_id':'rd_765'},'3001')]:
   result=self.identity.decorate(row,cid,'765')
   self.assertEqual(result['crm_customer_id'],'3001')
   self.assertIsNone(result['respond_url'])

 def test_explicit_respond_fallback_and_numeric_conversation_not_guessed(self):
  self.assertEqual(self.identity.decorate({'conversation_id':'rd_765'})['respond_url'],'https://app.respond.io/space/322951/inbox/765')
  self.assertIsNone(self.identity.decorate({'conversation_id':'765','respond_conv_id':'999'})['respond_url'])
  self.assertIsNone(self.identity.decorate({'conversation_id':"rd_1' OR 1=1"})['respond_url'])

 def decorate_batch(self,rows,links,edges,refs):
  q=Mock();q.fetchall.side_effect=[links,edges]+([refs] if edges or any(str(r['conversation_id']).startswith('rd_') for r in rows) else [])
  return self.identity.decorate_rows(q,rows)

 def test_both_mapping_tables_can_resolve_crm_without_materialized_history_link(self):
  rows=self.decorate_batch([{'conversation_id':'123'}],[],[{'chatwoot_conv_id':'123','respond_conv_id':'765'}],
    [{'respond_id':'765','crm_customer_id':3001}])
  self.assertEqual(rows[0]['crm_customer_id'],'3001');self.assertIsNone(rows[0]['respond_url'])

 def test_missing_crm_uses_only_single_explicit_respond_alias(self):
  rows=self.decorate_batch([{'conversation_id':'123'}],[],[{'chatwoot_conv_id':'123','respond_conv_id':'765'}],[])
  self.assertEqual(rows[0]['respond_customer_id'],'765')

 def test_conflicting_or_partly_unknown_aliases_do_not_guess_crm_or_respond(self):
  edges=[{'chatwoot_conv_id':'123','respond_conv_id':'765'},{'chatwoot_conv_id':'123','respond_conv_id':'766'}]
  for refs in [[{'respond_id':'765','crm_customer_id':3001}],
               [{'respond_id':'765','crm_customer_id':3001},{'respond_id':'766','crm_customer_id':3002}]]:
   row=self.decorate_batch([{'conversation_id':'123'}],[],edges,refs)[0]
   self.assertIsNone(row['crm_url']);self.assertIsNone(row['respond_url'])

 def test_multiple_aliases_with_same_verified_owner_resolve_crm(self):
  row=self.decorate_batch([{'conversation_id':'123'}],[],
    [{'chatwoot_conv_id':'123','respond_conv_id':'765'},{'chatwoot_conv_id':'123','respond_conv_id':'766'}],
    [{'respond_id':'765','crm_customer_id':3001},{'respond_id':'766','crm_customer_id':3001}])[0]
  self.assertEqual(row['crm_customer_id'],'3001')

 def test_rd_prefix_and_conflicting_stored_alias_are_not_arbitrarily_selected(self):
  row=self.decorate_batch([{'conversation_id':'rd_765'}],[],[{'chatwoot_conv_id':'rd_765','respond_conv_id':'766'}],[])[0]
  self.assertIsNone(row['respond_url'])

 def test_malformed_stored_alias_cannot_be_ignored_to_claim_verified_owner(self):
  row=self.decorate_batch([{'conversation_id':'123'}],[],
    [{'chatwoot_conv_id':'123','respond_conv_id':'765'},{'chatwoot_conv_id':'123','respond_conv_id':'unknown'}],
    [{'respond_id':'765','crm_customer_id':3001}])[0]
  self.assertIsNone(row['crm_url']);self.assertIsNone(row['respond_url'])

if __name__=='__main__':unittest.main()
