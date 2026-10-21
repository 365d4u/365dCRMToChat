set -eu
sudo -n install -d -m 755 /data/365dCRMToChat /data/365dCRMToChat/ops /data/365dCRMToChat/backups
sudo -n install -d -m 700 /data/365dCRMToChat/config
sudo -n install -d -o www-data -g webgroup -m 700 /data/365dCRMToChat/state
sudo -n tar -xzf /data/365dCRMToChat/staging/crm-to-chat-host-migration-20261012.tar.gz -C /data/365dCRMToChat
sudo -n /usr/bin/python3.12 -m venv /data/365dCRMToChat/venv
sudo -n /data/365dCRMToChat/venv/bin/python -m pip install '/data/365dCRMToChat[writer]'
if ! sudo -n test -f /data/365dCRMToChat/state/tunnel_key; then
  sudo -n ssh-keygen -q -t ed25519 -N '' -f /data/365dCRMToChat/state/tunnel_key -C crm-to-chat-107-host-20261012
fi
sudo -n chown www-data:webgroup /data/365dCRMToChat/state/tunnel_key /data/365dCRMToChat/state/tunnel_key.pub
sudo -n chmod 600 /data/365dCRMToChat/state/tunnel_key
sudo -n install -o www-data -g webgroup -m 600 /data/365dCRMToChat/ops/crm-known-host /data/365dCRMToChat/state/known_hosts
sudo -n install -m 644 /data/365dCRMToChat/ops/365d-crm-to-chat.service /etc/systemd/system/365d-crm-to-chat.service
sudo -n install -m 644 /data/365dCRMToChat/ops/365d-crm-to-chat-tunnel.service /etc/systemd/system/365d-crm-to-chat-tunnel.service
sudo -n systemctl daemon-reload
sudo -n cat /data/365dCRMToChat/state/tunnel_key.pub
systemctl show 365d-crm-to-chat 365d-crm-to-chat-tunnel -p Id -p LoadState -p ActiveState
