set -eu
sudo -n python3 - <<'PY'
import ast,hashlib,shutil
from pathlib import Path
root=Path('/var/www/respond_webhook/respond_to_msgsite')
stage=Path('/data/365dCRMToChat/staging/respond-retire-20261012')
backup=Path('/var/backups/respond_to_msgsite/no-chat-db-write-20261012')
expected={'service/queue_handle.py':'baa555e811f644fe2d92eb8319361257816453bb0261b5e2a74f4b265fd96479',
          'service/database.py':'2ae8cca4bfe2577ff6400034015bd82e69f8ba203ec842f49cc0019a59f4a62b'}
for name,checksum in expected.items():
 assert hashlib.sha256((root/name).read_bytes()).hexdigest()==checksum,'Production file changed; deployment aborted'
 ast.parse((stage/name).read_text())
backup.mkdir(parents=True,mode=0o700,exist_ok=True)
for name in expected:
 saved=backup/name
 assert not saved.exists(),'Recovery point already exists; deployment aborted'
 saved.parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(root/name,saved)
for name in expected:
 shutil.copyfile(stage/name,root/name)
print('Deployed only queue_handle.py and database.py; backups preserved')
PY
sudo -n systemctl restart respond_to_msgsite.service
systemctl show respond_to_msgsite 365d-crm-to-chat respond_rabbitmq_consume -p Id -p ActiveState -p SubState -p MainPID -p NRestarts
