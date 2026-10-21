set -eu
sudo -n tar -xzf /data/365dCRMToChat/staging/reference-sync-20261012.tar.gz -C /data/365dCRMToChat
sudo -n install -d -m 700 /data/365dCRMToChat/state/reference-sync
if ! sudo -n test -f /data/365dCRMToChat/state/reference-sync/id_ed25519; then
 sudo -n ssh-keygen -q -t ed25519 -N '' -C 365d-crm-reference-sync -f /data/365dCRMToChat/state/reference-sync/id_ed25519
fi
sudo -n cp /data/365dCRMToChat/state/known_hosts /data/365dCRMToChat/state/reference-sync/known_hosts
sudo -n chmod 600 /data/365dCRMToChat/state/reference-sync/known_hosts
sudo -n cat /data/365dCRMToChat/state/reference-sync/id_ed25519.pub
sudo -n systemd-analyze verify /data/365dCRMToChat/ops/365d-crm-reference-sync.service /data/365dCRMToChat/ops/365d-crm-reference-sync.timer
