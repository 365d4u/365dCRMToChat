set -eu
sudo -n systemd-run --quiet --wait --pipe --collect --unit=365d-crm-reference-schema \
 -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
 -p EnvironmentFile=/data/365dCRMToChat/config/consumer.env \
 -p WorkingDirectory=/data/365dCRMToChat \
 /data/365dCRMToChat/venv/bin/python /data/365dCRMToChat/ops/reference_schema.py
sudo -n install -m 644 /data/365dCRMToChat/ops/365d-crm-reference-sync.service /etc/systemd/system/365d-crm-reference-sync.service
sudo -n install -m 644 /data/365dCRMToChat/ops/365d-crm-reference-sync.timer /etc/systemd/system/365d-crm-reference-sync.timer
sudo -n systemctl daemon-reload
sudo -n systemctl start --no-block 365d-crm-reference-sync
systemctl show 365d-crm-reference-sync -p ActiveState -p SubState -p MainPID
