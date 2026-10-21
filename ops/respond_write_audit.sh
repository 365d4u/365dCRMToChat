set -eu
sudo -n python3 - <<'PY'
import json,hashlib,subprocess
from pathlib import Path
pid=subprocess.check_output(['systemctl','show','respond_to_msgsite','-p','MainPID','--value'],text=True).strip()
with open('/proc/'+pid+'/environ','rb') as f:
 values=dict(x.split(b'=',1) for x in f.read().split(b'\0') if b'=' in x)
root=Path('/var/www/respond_webhook/respond_to_msgsite')
processes=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  arguments=(p/'cmdline').read_bytes().split(b'\0')
  if b'/var/www/respond_webhook/respond_to_msgsite/consumer_worker.py' in arguments:processes.append(int(p.name))
 except OSError:pass
print(json.dumps({'legacyWriteEnabled':values.get(b'CHAT_DB_WRITE_ENABLED',b'absent').decode(),
 'consumerProcesses':processes,'sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['service/queue_handle.py','service/database.py']}}))
print(subprocess.check_output(['systemctl','show','respond_to_msgsite','365d-crm-to-chat','-p','Id','-p','ActiveState','-p','MainPID','-p','NRestarts'],text=True))
PY
