set -eu
sudo -n chmod 644 /data/365dCRMToChat/crm_to_chat/*.py /data/365dCRMToChat/ops/*.service /data/365dCRMToChat/ops/*.timer
sudo -n chown root:root /data/365dCRMToChat/crm_to_chat/*.py /data/365dCRMToChat/ops/*.service /data/365dCRMToChat/ops/*.timer
sudo -n chmod 755 /data/365dCRMToChat/crm_to_chat /data/365dCRMToChat/ops
sudo -n systemctl start --no-block 365d-crm-reference-sync
systemctl show 365d-crm-reference-sync -p MainPID -p ActiveState -p SubState
