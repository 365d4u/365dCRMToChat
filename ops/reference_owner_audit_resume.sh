set -eu
test "$(systemctl show 365d-crm-reference-sync.service -p Result --value)" = success
test "$(systemctl show 365d-crm-reference-sync.service -p ExecMainStatus --value)" = 0
if systemctl is-active --quiet 365d-crm-reference-sync.service; then exit 1;fi
sudo -n systemctl start 365d-crm-reference-sync.timer
systemctl show 365d-crm-reference-sync.timer -p ActiveState -p SubState -p NextElapseUSecRealtime
systemctl is-enabled 365d-crm-reference-sync.timer 365d-crm-to-chat.service 365d-crm-to-chat-tunnel.service
systemctl show 365d-crm-to-chat.service 365d-crm-to-chat-tunnel.service respond_to_msgsite.service respond_rabbitmq_consume.service -p Id -p ActiveState -p MainPID -p NRestarts
sudo -n stat -c '%U:%G %a %n' /data/365dCRMToChat/state/reference-sync/snapshot.owner-audit-preview.ndjson /data/365dCRMToChat/state/reference-sync/snapshot.before-owner-audit-20261012.ndjson
