set -eu
sudo -n tar -xzf /data/365dCRMToChat/staging/host-migration-docs-20261012.tar.gz -C /data/365dCRMToChat
sudo -n python3 - <<'PY'
import json,os,shutil,subprocess
from pathlib import Path
root=Path('/data/365dCRMToChat').resolve();stage=root/'staging'
names=['host-migration-docs-20261012.tar.gz','crm-to-chat-host-migration-20261012.tar.gz',
 'respond-retire-20261012.tar.gz','reference-sync-20261012.tar.gz','reference-final.py','reference-format-final.py',
 'respond-retire-20261012']
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 for path in [proc/'cwd',*list((proc/'fd').glob('*'))]:
  try:target=path.resolve(strict=True)
  except (OSError,RuntimeError):continue
  if target.is_relative_to(stage):raise RuntimeError('staging path still in process use')
removed=[]
for name in names:
 path=stage/name
 if not path.exists():continue
 if path.is_symlink() or not path.resolve().is_relative_to(stage):raise RuntimeError('unsafe staging target')
 if path.is_dir():shutil.rmtree(path)
 else:path.unlink()
 removed.append(str(path))
for name in ['README.md','AGENTS.md','docs/crm-reference-search-20261012.md','docs/verification.md','docs/deployment-20261012.md']:
 os.chmod(root/name,0o644)
for folder in ['crm_to_chat','docs','migrations','ops']:
 for path in (root/folder).rglob('*'):
  if path.is_symlink():continue
  os.chmod(path,0o755 if path.is_dir() else 0o644)
  os.chown(path,0,0)
 os.chmod(root/folder,0o755);os.chown(root/folder,0,0)
print(json.dumps({'removedStaging':removed,'runtimeConfigAndStateRetained':True}))
PY
systemctl show 365d-crm-to-chat 365d-crm-to-chat-tunnel 365d-crm-reference-sync 365d-crm-reference-sync.timer -p Id -p ActiveState -p MainPID -p Result -p ExecMainStatus -p UnitFileState
sudo -n journalctl -u 365d-crm-reference-sync -n 50 --no-pager | sed -n '/"event": "crm_reference_sync"/p' | tail -n 2
