set -eu
sudo -n python3 - <<'PY'
import ast,hashlib,os,shutil,subprocess
from pathlib import Path
status=subprocess.check_output(['systemctl','show','365d-crm-reference-sync','-p','ActiveState','--value'],text=True).strip()
if status not in ('inactive','failed'):raise RuntimeError('reference service still running')
root=Path('/data/365dCRMToChat');current=root/'crm_to_chat/references.py';staged=root/'staging/reference-format-final.py'
if hashlib.sha256(current.read_bytes()).hexdigest()!='6747318ddb984c9459788d5f61f90ed72ab342d62f6148207ea4497c298c5d07':raise RuntimeError('reference preimage changed')
if hashlib.sha256(staged.read_bytes()).hexdigest()!='ea79057510b33a78e50cb4751fe31a5d04ca368387a8b6fa048ba6d7f16a7e84':raise RuntimeError('reference staged digest mismatch')
ast.parse(staged.read_text());shutil.copyfile(staged,current);os.chmod(current,0o644)
PY
sudo -n systemctl reset-failed 365d-crm-reference-sync
sudo -n systemctl start --no-block 365d-crm-reference-sync
systemctl show 365d-crm-reference-sync -p MainPID -p ActiveState -p SubState
