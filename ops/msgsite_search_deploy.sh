set -eu
/var/www/python/chatwoot_message/venv/bin/python - <<'PY'
import ast,hashlib,os,shutil,tarfile
from pathlib import Path
root=Path('/var/www/python/chatwoot_message')
stage=Path('/tmp/msgsite-crm-search-20261012')
backup=Path('/var/backups/chatwoot_message/crm-id-search-20261012')
expected={'service/conversation_manager.py':'9303ccd1b0cbdd492b27fabe0a8be021ac5a4531b8681d196752c15a5a226c52',
 'service/crm_identity.py':'4c85bb548d6a888254a42659539ab7cb8bcd89cb47fe3250fdaeb9efd5d2dce1',
 'templates/conversations_list.html':'e4af1d057ae0c860e6b082179acc27b1f25290d1fbb9603eb92db0e2a53755f8'}
for name,sha in expected.items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('production preimage changed: '+name)
 if (backup/name).exists():raise RuntimeError('search backup already exists')
 if name.endswith('.py'):ast.parse((stage/name).read_text())
for name in expected:
 target=backup/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 shutil.copy2(root/name,target);shutil.copyfile(stage/name,root/name);os.chmod(root/name,0o644)
print('Three search files installed with checked preimages and backups')
PY
systemctl restart chatwoot_message
systemctl show chatwoot_message -p MainPID -p ActiveState -p SubState -p NRestarts
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' --max-time 10 http://127.0.0.1:5000/
