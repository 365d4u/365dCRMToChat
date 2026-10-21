set -eu
systemctl show 365d-crm-reference-sync -p ActiveState -p SubState -p MainPID -p Result -p ExecMainStatus -p MemoryPeak
sudo -n journalctl -u 365d-crm-reference-sync --since '-15 minutes' -n 12 --no-pager
systemctl show 365d-crm-to-chat respond_to_msgsite -p Id -p ActiveState -p MainPID -p NRestarts
