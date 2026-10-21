set -eu
/var/www/python/chatwoot_message/venv/bin/python - <<'PY'
import json,shutil
from pathlib import Path
targets=[Path('/tmp/msgsite-crm-search-20261012'),Path('/tmp/crm-cutover-20261012'),
 Path('/tmp/msgsite-crm-search-20261012.tar.gz'),Path('/tmp/msgsite_final_verify.py'),Path('/tmp/chat_reference_inspect.py')]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 for pointer in [proc/'cwd',*list((proc/'fd').glob('*'))]:
  try:value=pointer.resolve(strict=True)
  except (OSError,RuntimeError):continue
  if any(value==target or value.is_relative_to(target) for target in targets):raise RuntimeError('temporary file still in use')
removed=[]
for target in targets:
 if not target.exists():continue
 if target.is_symlink() or target.resolve()!=target or target.parent!=Path('/tmp'):raise RuntimeError('unsafe temporary target')
 if target.is_dir():shutil.rmtree(target)
 else:target.unlink()
 removed.append(str(target))
print(json.dumps({'temporaryFilesRemoved':removed,'productionAndBackupsRetained':True}))
PY
systemctl show chatwoot_message -p ActiveState -p SubState -p MainPID -p NRestarts
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' --max-time 10 http://127.0.0.1:5000/
