set -eu
if systemctl is-active --quiet 365d-crm-reference-sync.service; then
 echo 'Reference sync is already running' >&2
 exit 1
fi
sudo -n systemctl start --no-block 365d-crm-reference-sync.service
systemctl show 365d-crm-reference-sync.service -p ActiveState -p SubState -p MainPID -p Result
