set -eu
sudo -n python3 - <<'PY'
import os,shutil
from pathlib import Path
key='AAAAC3NzaC1lZDI1NTE5AAAAIAOgNEtX2gzAFxs2VoHu7yKHbUNAxy//Fj+X1EUX3hHA'
p=Path('/home/ubuntu/.ssh/authorized_keys');lines=p.read_text().splitlines()
selected=[line for line in lines if key in line]
if len(selected)!=1:raise RuntimeError('retired tunnel key is not unique')
if '165.154.134.51' not in selected[0]:raise RuntimeError('retired source scope changed')
backup=Path('/data/365d-crm/config/deployments/msgsite-reference-20261012/authorized_keys.before-retired-cleanup')
if backup.exists():raise RuntimeError('key cleanup backup already exists')
shutil.copy2(p,backup);os.chmod(backup,0o600)
p.write_text('\n'.join(line for line in lines if key not in line)+'\n')
for name in ['crm_reference_inspect.mjs','crm_reference_export.mjs']:
 file=Path('/data/365d-crm/tmp')/name
 if file.is_file() and not file.is_symlink():file.unlink()
print('Retired message-site tunnel key and temporary inspection files removed')
PY
