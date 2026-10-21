"""Explicit batch operation: --apply is required; database config stays on server."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymysql
from crm_to_chat.environment import mysql_config
from crm_to_chat.references import read_snapshot,plan_import,apply_import

p=argparse.ArgumentParser();p.add_argument('snapshot');p.add_argument('--apply',action='store_true')
args=p.parse_args();refs,header=read_snapshot(args.snapshot)
if not refs:raise RuntimeError('empty_reference_import_refused')
db=pymysql.connect(**mysql_config(os.environ),charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
try:
 with db.cursor() as q:
  q.execute("SELECT GET_LOCK('crm-reference-import-v1',5) AS acquired")
  if q.fetchone()['acquired']!=1:raise RuntimeError('reference_import_already_running')
  q.execute('START TRANSACTION READ ONLY')
  links,stats=plan_import(q,refs)
 db.rollback()
 if args.apply:apply_import(db,refs,links)
 print(json.dumps({'applied':args.apply,'scope':header['scope'],'exportedAt':header['exportedAt'],**stats}))
finally:
 with db.cursor() as q:q.execute("SELECT RELEASE_LOCK('crm-reference-import-v1')")
 db.close()
