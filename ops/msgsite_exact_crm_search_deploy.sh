set -euo pipefail
root=/var/www/python/chatwoot_message
stage=/tmp/msgsite-identity-fallback-20261012
backup=/var/backups/chatwoot_message/crm-preferred-respond-fallback-20261012/service/conversation_manager.py
test ! -e "$backup"
test "$(sha256sum "$root/service/conversation_manager.py" | cut -d' ' -f1)" = 5fb0655f010b910dac79e11414569a6be5b4aefb5dfb63cbd1795c27d64fc458
"$root/venv/bin/python" -m py_compile "$stage/service/conversation_manager.py"
cp -p "$root/service/conversation_manager.py" "$backup"
rollback() {
 cp -p "$backup" "$root/service/conversation_manager.py"
 systemctl restart chatwoot_message.service
 echo 'Restored the manager after deployment failure' >&2
}
trap rollback ERR
install -o www-data -g www-data -m 644 "$stage/service/conversation_manager.py" "$root/service/conversation_manager.py"
systemctl restart chatwoot_message.service
ready=false
for attempt in 1 2 3 4 5 6 7 8 9 10; do
 code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:5000/ 2>/dev/null || true)
 if systemctl is-active --quiet chatwoot_message.service && [ "$code" = 302 ]; then ready=true;break;fi
 sleep 1
done
test "$ready" = true
trap - ERR
systemctl show chatwoot_message.service -p MainPID -p ActiveState -p NRestarts
printf 'HTTP %s\n' "$code"
sha256sum "$root/service/conversation_manager.py"
