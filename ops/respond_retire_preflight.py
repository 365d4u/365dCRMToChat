"""Verify staged read-only policy on host runtime; no business writes or sends."""
import importlib.util
import json
import sys
sys.path.insert(0,'/var/www/respond_webhook/respond_to_msgsite')
path='/data/365dCRMToChat/staging/respond-retire-20261012/service/database.py'
spec=importlib.util.spec_from_file_location('respond_readonly_probe',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.db_manager.pool is None
module.db_manager.execute_query('SELECT 1 AS readonly_probe')
assert module.RespondAllAgentDAO.get_agent_name('codex-readonly-probe@example.invalid',False) is None
connection=module.db_manager.get_connection()
try:
    cursor=connection.cursor()
    cursor.execute("SHOW SESSION VARIABLES WHERE Variable_name IN ('transaction_read_only','tx_read_only')")
    values=cursor.fetchall()
    assert values and all(str(row['Value']).upper() in {'ON','1'} for row in values)
    cursor.close()
finally:
    connection.rollback()
    connection.close()
try:
    module.db_manager.execute_update('UPDATE __retired_writer_probe__ SET x=1')
    raise AssertionError('Retired write method accepted a write')
except RuntimeError as error:
    assert str(error)=='Respond chat_db writes are retired'
print(json.dumps({'readOnlySession':True,'followupLookupReadable':True,'writeBlockedBeforeSql':True}))
