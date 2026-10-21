set -eu
/var/www/python/chatwoot_message/venv/bin/python - <<'PY'
import importlib.util,json,os,shutil,subprocess
from pathlib import Path
old=Path('/var/www/python/365dCRMToChat')
for unit in ('365d-crm-to-chat','365d-crm-to-chat-tunnel'):
 values=subprocess.check_output(['systemctl','show',unit,'-p','MainPID','-p','ActiveState','-p','UnitFileState'],text=True)
 if 'MainPID=0' not in values or 'ActiveState=inactive' not in values or 'UnitFileState=disabled' not in values:
  raise RuntimeError('retired consumer is not fully disabled')
module=Path(importlib.util.find_spec('crm_to_chat').origin).resolve()
if module.is_relative_to(old):raise RuntimeError('message site still imports old project')
env=Path('/etc/365d-crm-to-chat.env')
lines=env.read_text().splitlines();names={line.split('=',1)[0].strip() for line in lines if '=' in line and not line.lstrip().startswith('#')}
if names!={'CRM_MEDIA_TOKEN','CRM_TO_CHAT_AMQP_URL','CRM_TO_CHAT_WORKSPACE_IDS','CRM_TO_CHAT_WRITE_ENABLED'}:
 raise RuntimeError('unexpected old configuration; preserve for inspection')
media=[line for line in lines if line.startswith('CRM_MEDIA_TOKEN=')]
if len(media)!=1:raise RuntimeError('media token entry not unique')
new=Path('/etc/chatwoot-message-crm-media.env')
with new.open('x') as f:f.write(media[0]+'\n')
os.chmod(new,0o600)
backup=Path('/var/backups/chatwoot_message/crm-id-search-20261012/retired-units')
backup.mkdir(mode=0o700,parents=True,exist_ok=True)
drop=Path('/etc/systemd/system/chatwoot_message.service.d/30-crm-media.conf')
shutil.copy2(drop,backup/'30-crm-media.conf')
drop.write_text('[Service]\nEnvironmentFile=/etc/chatwoot-message-crm-media.env\n')
for unit in ('365d-crm-to-chat.service','365d-crm-to-chat-tunnel.service'):
 path=Path('/etc/systemd/system')/unit;shutil.copy2(path,backup/unit);path.unlink()
key=Path('/var/lib/365d-crm-to-chat/tunnel_key.pub').read_text().split()[1]
if old.resolve()!=Path('/var/www/python/365dCRMToChat'):raise RuntimeError('old project path changed')
shutil.rmtree(old)
state=Path('/var/lib/365d-crm-to-chat')
if state.resolve()!=Path('/var/lib/365d-crm-to-chat'):raise RuntimeError('old state path changed')
shutil.rmtree(state);env.unlink()
print(json.dumps({'retiredProjectRemoved':str(old),'mediaLibrary':str(module),'mediaConfig':str(new),'retiredPublicKey':key}))
PY
systemctl daemon-reload
systemctl restart chatwoot_message
systemctl show chatwoot_message -p ActiveState -p MainPID -p NRestarts
