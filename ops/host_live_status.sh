set -eu
systemctl show 365d-crm-to-chat 365d-crm-to-chat-tunnel respond_to_msgsite respond_rabbitmq_consume -p Id -p ActiveState -p SubState -p MainPID -p NRestarts
sudo -n python3 - <<'PY'
import json,subprocess
for service in ['365d-crm-to-chat','respond_to_msgsite']:
 pid=subprocess.check_output(['systemctl','show',service,'-p','MainPID','--value'],text=True).strip()
 with open('/proc/'+pid+'/environ','rb') as f:values=dict(x.split(b'=',1) for x in f.read().split(b'\0') if b'=' in x)
 print(json.dumps({'service':service,'writeEnabled':values.get(b'CRM_TO_CHAT_WRITE_ENABLED',values.get(b'CHAT_DB_WRITE_ENABLED',b'absent')).decode(),
  'environmentStyle':values.get(b'CRM_TO_CHAT_DB_ENV_STYLE',b'legacy').decode()}))
PY
sudo -n journalctl -u 365d-crm-to-chat --since '-3 minutes' -n 15 --no-pager
sudo -n systemd-run --quiet --wait --pipe --collect --unit=365d-crm-to-chat-preflight \
  -p User=www-data -p Group=webgroup \
  -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
  -p EnvironmentFile=/data/365dCRMToChat/config/consumer.env \
  -p WorkingDirectory=/data/365dCRMToChat \
  /data/365dCRMToChat/venv/bin/python /data/365dCRMToChat/ops/migration_preflight.py
