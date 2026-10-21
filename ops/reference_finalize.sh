set -eu
sudo -n python3 - <<'PY'
import ast,hashlib,os,shutil,subprocess
from pathlib import Path
status=subprocess.check_output(['systemctl','show','365d-crm-reference-sync','-p','ActiveState','--value'],text=True).strip()
if status not in ('inactive','failed'):raise RuntimeError('reference sync is still running')
root=Path('/data/365dCRMToChat')
current=root/'crm_to_chat/references.py';staged=root/'staging/reference-final.py'
if hashlib.sha256(current.read_bytes()).hexdigest()!='3dd761f0dca72e6ae67b63f684abdb2f49a442ecb1d07889b2640c022c17bf51':raise RuntimeError('reference code preimage changed')
if hashlib.sha256(staged.read_bytes()).hexdigest()!='6747318ddb984c9459788d5f61f90ed72ab342d62f6148207ea4497c298c5d07':raise RuntimeError('reference staged digest mismatch')
ast.parse(staged.read_text());shutil.copyfile(staged,current);os.chmod(current,0o644)
PY
sudo -n systemctl enable --now 365d-crm-reference-sync.timer
sudo -n systemctl start --no-block 365d-crm-reference-sync
systemctl show 365d-crm-reference-sync.timer -p ActiveState -p UnitFileState -p NextElapseUSecMonotonic
