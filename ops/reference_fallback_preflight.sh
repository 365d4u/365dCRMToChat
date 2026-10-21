set -eu
sudo -n systemctl stop 365d-crm-reference-sync.timer
if systemctl is-active --quiet 365d-crm-reference-sync.service; then
 echo 'Reference sync already running; wait before preview' >&2
 exit 1
fi
systemctl show 365d-crm-reference-sync.service -p Result -p ExecMainStatus
systemctl show 365d-crm-to-chat.service 365d-crm-to-chat-tunnel.service respond_to_msgsite.service -p Id -p ActiveState -p MainPID -p NRestarts
sudo -n python3 - <<'PY'
import hashlib,json,os,subprocess
from pathlib import Path
root=Path('/data/365dCRMToChat');state=root/'state/reference-sync'
old=state/'snapshot.ndjson'
backup=state/'snapshot.before-owner-audit-20261012.ndjson'
if old.exists() and not backup.exists():
 import shutil
 shutil.copy2(old,backup);os.chmod(backup,0o600)
preview=state/'snapshot.owner-audit-preview.ndjson'
with preview.open('wb') as f:
 os.chmod(preview,0o600)
 p=subprocess.run(['ssh','-p','2209','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
 '-o','UserKnownHostsFile='+str(state/'known_hosts'),'-o','ConnectTimeout=15',
 '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-i',str(state/'id_ed25519'),
 'ubuntu@154.197.57.214','export-crm-references'],stdout=f,stderr=subprocess.PIPE,timeout=240)
if p.returncode:raise RuntimeError('reference_preview_export_failed')
import sys
sys.path.insert(0,str(root))
from crm_to_chat.references import read_snapshot
refs,header=read_snapshot(preview)
expected={'429120621':'3755','317763983':'7007','457693542':'20384'}
for rid,cid in expected.items():
 if rid not in refs or refs[rid][0]!=cid:raise RuntimeError('sample_owner_mismatch')
print(json.dumps({'previewReferences':len(refs),'verificationPolicy':header.get('verificationPolicy'),'sampleOwners':{rid:refs[rid][0] for rid in expected}}))
PY
sudo -n systemd-run --quiet --wait --pipe --collect --unit=crm-reference-owner-audit-preview-20261012 \
 -p WorkingDirectory=/data/365dCRMToChat \
 -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
 -p EnvironmentFile=/data/365dCRMToChat/config/consumer.env \
 -p UMask=0077 -p CPUQuota=30% -p MemoryMax=512M \
 /data/365dCRMToChat/venv/bin/python /data/365dCRMToChat/ops/reference_import.py \
 /data/365dCRMToChat/state/reference-sync/snapshot.owner-audit-preview.ndjson
