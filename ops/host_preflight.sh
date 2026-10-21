set -eu
sudo -n systemd-run --quiet --wait --pipe --collect --unit=365d-crm-to-chat-preflight \
  -p User=www-data -p Group=webgroup \
  -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
  -p EnvironmentFile=/data/365dCRMToChat/config/consumer.env \
  -p WorkingDirectory=/data/365dCRMToChat \
  /data/365dCRMToChat/venv/bin/python /data/365dCRMToChat/ops/migration_preflight.py
systemctl show 365d-crm-to-chat -p Id -p ActiveState -p SubState -p MainPID -p NRestarts
