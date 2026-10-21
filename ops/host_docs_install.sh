set -eu
sudo -n tar -xzf /data/365dCRMToChat/staging/host-migration-docs-20261012.tar.gz -C /data/365dCRMToChat
sudo -n /data/365dCRMToChat/venv/bin/python - <<'PY'
import json,hashlib
from pathlib import Path
root=Path('/data/365dCRMToChat')
print(json.dumps({'project':str(root),'hashes':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['crm_to_chat/consume.py','crm_to_chat/environment.py','ops/365d-crm-to-chat.service','ops/365d-crm-to-chat-tunnel.service']}}))
PY
systemctl show 365d-crm-to-chat 365d-crm-to-chat-tunnel -p Id -p ActiveState -p MainPID -p NRestarts -p UnitFileState
