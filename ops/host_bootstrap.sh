set -eu
sudo -n install -d -m 755 /data/365dCRMToChat /data/365dCRMToChat/ops /data/365dCRMToChat/backups
sudo -n install -d -m 700 /data/365dCRMToChat/config
sudo -n install -d -o www-data -g webgroup -m 700 /data/365dCRMToChat/state
sudo -n tar -xzf /data/365dCRMToChat/staging/crm-to-chat-host-migration-20261012.tar.gz -C /data/365dCRMToChat
sudo -n /usr/bin/python3.12 -m venv /data/365dCRMToChat/venv
sudo -n /data/365dCRMToChat/venv/bin/python -m pip install '/data/365dCRMToChat[writer]'
sudo -n install -m 644 /data/365dCRMToChat/ops/365d-crm-to-chat.service /etc/systemd/system/365d-crm-to-chat.service
sudo -n systemctl daemon-reload
