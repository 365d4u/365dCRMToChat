set -eu
sudo -n systemctl start 365d-crm-to-chat-tunnel
attempt=0
until ss -ltnH 'sport = :35672' | grep -q 35672; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 20 ]; then echo 'SSH tunnel listener unavailable'; exit 1; fi
  sleep 1
done
sudo -n systemd-run --quiet --wait --pipe --collect --unit=365d-crm-to-chat-preflight \
  -p User=www-data -p Group=webgroup \
  -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
  -p EnvironmentFile=/data/365dCRMToChat/config/consumer.env \
  -p WorkingDirectory=/data/365dCRMToChat \
  /data/365dCRMToChat/venv/bin/python /data/365dCRMToChat/ops/migration_preflight.py
systemctl show 365d-crm-to-chat 365d-crm-to-chat-tunnel -p Id -p ActiveState -p SubState -p MainPID -p NRestarts
