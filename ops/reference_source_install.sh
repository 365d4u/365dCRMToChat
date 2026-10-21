set -eu
sudo -n install -d -m 755 /data/365d-crm/operations/msgsite-reference-export
sudo -n install -d -m 700 /data/365d-crm/config/deployments/msgsite-reference-20261012
sudo -n chmod 755 /data/365d-crm/operations/msgsite-reference-export/export.sh
sudo -n chmod 644 /data/365d-crm/operations/msgsite-reference-export/export.mjs
sudo -n python3 - <<'PY'
from pathlib import Path
p=Path('/data/365d-crm/operations/msgsite-reference-export/export.sh')
s=p.read_text().replace('\r','').strip()
if not s.startswith('#!'):s='#!/bin/sh\n'+s
p.write_text(s+'\n')
PY
sudo -n /data/365d-crm/runtime/node/bin/node --check /data/365d-crm/operations/msgsite-reference-export/export.mjs
sudo -n bash -n /data/365d-crm/operations/msgsite-reference-export/export.sh
sudo -n python3 - <<'PY'
import shutil,os
from pathlib import Path
key='AAAAC3NzaC1lZDI1NTE5AAAAIIRIu86/3Ds4tkLewwqqcMIZq1znyDRdJNw1PD1kihOu'
line='restrict,from="107.150.104.4",command="sudo -n /data/365d-crm/operations/msgsite-reference-export/export.sh" ssh-ed25519 '+key+' 365d-crm-reference-sync'
path=Path('/home/ubuntu/.ssh/authorized_keys')
old=path.read_text()
matched=[row for row in old.splitlines() if key in row]
if matched and matched!=[line]:raise RuntimeError('reference_key_options_conflict')
if not matched:
 backup=Path('/data/365d-crm/config/deployments/msgsite-reference-20261012/authorized_keys.before')
 if backup.exists():raise RuntimeError('reference_key_backup_already_exists')
 shutil.copy2(path,backup);os.chmod(backup,0o600)
 with path.open('a') as f:f.write(('' if old.endswith('\n') else '\n')+line+'\n')
print('Restricted CRM reference export key installed; other SSH keys preserved')
PY
