set -eu
sudo -n python3 - <<'PY'
import json,subprocess
cmd=['ssh','-p','2209','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
 '-o','UserKnownHostsFile=/data/365dCRMToChat/state/reference-sync/known_hosts',
 '-i','/data/365dCRMToChat/state/reference-sync/id_ed25519','ubuntu@154.197.57.214','export-crm-references']
p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180)
lines=p.stderr.decode(errors='replace').splitlines()
safe=[line[:200] for line in lines if any(marker in line for marker in ['error:','Permission denied','not found','syntax error','statement timeout'])]
print(json.dumps({'exportExit':p.returncode,'diagnostic':safe}))
PY
