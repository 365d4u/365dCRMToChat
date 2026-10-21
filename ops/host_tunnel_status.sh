set -eu
systemctl show 365d-crm-to-chat-tunnel -p ActiveState -p SubState -p MainPID -p NRestarts
sudo -n journalctl -u 365d-crm-to-chat-tunnel -n 12 --no-pager
