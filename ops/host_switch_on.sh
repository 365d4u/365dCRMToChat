set -eu
sudo -n python3 - <<'PY'
from pathlib import Path
import shutil
path=Path('/data/365dCRMToChat/config/consumer.env')
backup=Path('/data/365dCRMToChat/backups/host-migration-20261012')
backup.mkdir(mode=0o700,exist_ok=True)
content=path.read_text()
assert content.splitlines().count('CRM_TO_CHAT_WRITE_ENABLED=false') == 1
shutil.copy2(path,backup/'consumer-before-enable.env')
path.write_text(content.replace('CRM_TO_CHAT_WRITE_ENABLED=false','CRM_TO_CHAT_WRITE_ENABLED=true'))
print('Target writer explicitly enabled')
PY
sudo -n systemctl enable --now 365d-crm-to-chat.service
systemctl show 365d-crm-to-chat -p Id -p ActiveState -p SubState -p MainPID -p NRestarts
