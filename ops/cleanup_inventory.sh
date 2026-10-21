set -eu
sudo -n find /data/365dCRMToChat/staging -maxdepth 2 -type f -printf '%p %s bytes\n'
sudo -n find /data/365dCRMToChat/ops -maxdepth 1 -type f -name '*.tar.gz' -printf '%p %s bytes\n'
systemctl show 365d-crm-reference-sync.timer -p ActiveState -p UnitFileState -p NextElapseUSecMonotonic
