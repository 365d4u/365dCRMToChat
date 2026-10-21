set -eu
systemctl show 365d-crm-reference-sync.service -p ActiveState -p SubState -p MainPID -p Result -p ExecMainStatus -p MemoryPeak
sudo -n journalctl -u 365d-crm-reference-sync.service --since '-15 minutes' --no-pager -o cat | grep '"event": "crm_reference_sync"' | tail -n 2
