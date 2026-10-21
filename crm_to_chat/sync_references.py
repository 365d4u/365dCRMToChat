"""Service entry point: fetch an authenticated full CRM reference snapshot."""
import json,os,subprocess
from pathlib import Path
import pymysql
from .environment import mysql_config
from .references import read_snapshot,plan_import,apply_import

def main():
    state=Path('/data/365dCRMToChat/state/reference-sync')
    state.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=state/'snapshot.next.ndjson';current=state/'snapshot.ndjson'
    with temporary.open('wb') as output:
        os.chmod(temporary,0o600)
        result=subprocess.run(['ssh','-p','2209','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
             '-o','UserKnownHostsFile='+str(state/'known_hosts'),'-o','ConnectTimeout=15',
             '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',
             '-i',str(state/'id_ed25519'),'ubuntu@154.197.57.214','export-crm-references'],
             stdout=output,stderr=subprocess.PIPE,timeout=240)
    if result.returncode:
        temporary.unlink(missing_ok=True)
        raise RuntimeError('CRM reference export unavailable; current mappings retained')
    try:refs,header=read_snapshot(temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if not refs:raise RuntimeError('empty_reference_import_refused')
    temporary.replace(current)
    db=pymysql.connect(**mysql_config(os.environ),charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)
    try:
        with db.cursor() as q:
            q.execute("SELECT GET_LOCK('crm-reference-import-v1',5) AS acquired")
            if q.fetchone()['acquired']!=1:raise RuntimeError('reference_import_already_running')
            q.execute('START TRANSACTION READ ONLY')
            links,stats=plan_import(q,refs)
        db.rollback()
        changed=apply_import(db,refs,links)
        print(json.dumps({'event':'crm_reference_sync','scope':header['scope'],'exportedAt':header['exportedAt'],**stats,**changed}),flush=True)
    finally:
        with db.cursor() as q:q.execute("SELECT RELEASE_LOCK('crm-reference-import-v1')")
        db.close()

if __name__=='__main__':main()
