set -eu
sudo -n python3 - <<'PY'
import os,subprocess
pid=subprocess.check_output(['systemctl','show','365d-crm-api','-p','MainPID','--value'],text=True).strip()
with open('/proc/'+pid+'/environ','rb') as f:
 env={k.decode():v.decode() for k,v in (p.split(b'=',1) for p in f.read().split(b'\0') if b'=' in p)}
subprocess.run(['/data/365d-crm/runtime/node/bin/node','/data/365d-crm/tmp/crm_reference_inspect.mjs'],env=env,check=True)
PY
