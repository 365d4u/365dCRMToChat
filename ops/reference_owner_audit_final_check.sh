set -eu
systemctl list-timers 365d-crm-reference-sync.timer --no-pager
systemctl show 365d-crm-reference-sync.service -p Result -p ExecMainStatus
sudo -n python3 - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
root=Path('/var/www/respond_webhook/respond_to_msgsite')
expected={
 'service/queue_handle.py':None,
 'service/database.py':None,
}
checks={}
for file in expected:
 body=(root/file).read_text()
 checks[file]={'sha256':hashlib.sha256((root/file).read_bytes()).hexdigest(),
  'hasRetirementGuard':'CHAT_DB_WRITE_ENABLED' in body if 'queue_handle' in file else 'START TRANSACTION READ ONLY' in body or 'SET SESSION TRANSACTION READ ONLY' in body}
pid=subprocess.check_output(['systemctl','show','respond_to_msgsite.service','-p','MainPID','--value'],text=True).strip()
parts=Path('/proc/'+pid+'/environ').read_bytes().split(b'\0')
flag=next((part.split(b'=',1)[1].decode() for part in parts if part.startswith(b'CHAT_DB_WRITE_ENABLED=')),None)
if flag not in ('false','0','off'):raise RuntimeError('legacy_write_flag_not_disabled')
print(json.dumps({'legacyWriteEnabled':False,'codeChecks':checks}))
PY
