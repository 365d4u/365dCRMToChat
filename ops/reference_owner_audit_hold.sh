set -eu
sudo -n systemctl stop 365d-crm-reference-sync.timer
systemctl show 365d-crm-reference-sync.service 365d-crm-reference-sync.timer -p Id -p ActiveState -p SubState -p Result -p MainPID
if systemctl is-active --quiet 365d-crm-reference-sync.service; then
 echo 'Wait for the currently running reference synchronization' >&2
 exit 1
fi
