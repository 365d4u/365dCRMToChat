set -euo pipefail
root=/var/www/python/chatwoot_message
stage=/tmp/msgsite-identity-fallback-20261012
backup=/var/backups/chatwoot_message/crm-preferred-respond-fallback-20261012
test ! -e "$backup"
python3 - <<'PY'
from pathlib import Path
import hashlib,ast
root=Path('/var/www/python/chatwoot_message');stage=Path('/tmp/msgsite-identity-fallback-20261012')
expected={'service/crm_identity.py':'726320c1ea16b341625af841e886ea93fc18d90a27bfa4a88e4e476cace6a167',
'templates/conversations_list.html':'472b48d9977a2b1e95c0f502618c59b45e3d94e603faed1f401011eb2d518a43',
'templates/conversation_detail.html':'b5cd84638516fc9eb85e625678bb312359750831bab9b2c2edaac222039b8487'}
for f,digest in expected.items():
 if hashlib.sha256((root/f).read_bytes()).hexdigest()!=digest:raise RuntimeError('production_preimage_changed: '+f)
ast.parse((stage/'service/crm_identity.py').read_text(encoding='utf-8-sig'))
print('All three production preimages match; staged Python syntax valid')
PY
install -d -m 700 "$backup/service" "$backup/templates"
cp -p "$root/service/crm_identity.py" "$backup/service/"
cp -p "$root/templates/conversations_list.html" "$root/templates/conversation_detail.html" "$backup/templates/"
rollback() {
 cp -p "$backup/service/crm_identity.py" "$root/service/"
 cp -p "$backup/templates/conversations_list.html" "$backup/templates/conversation_detail.html" "$root/templates/"
 systemctl restart chatwoot_message.service
 echo 'Restored all three files after deployment failure' >&2
}
trap rollback ERR
for f in service/crm_identity.py templates/conversations_list.html templates/conversation_detail.html; do
 install -o www-data -g www-data -m 644 "$stage/$f" "$root/$f"
done
systemctl restart chatwoot_message.service
ready=false
for attempt in 1 2 3 4 5 6 7 8 9 10; do
 code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:5000/ || true)
 if systemctl is-active --quiet chatwoot_message.service && [ "$code" = 302 ]; then ready=true;break;fi
 sleep 1
done
test "$ready" = true
trap - ERR
systemctl show chatwoot_message.service -p MainPID -p ActiveState -p NRestarts
printf 'HTTP %s\n' "$code"
sha256sum "$root/service/crm_identity.py" "$root/templates/conversations_list.html" "$root/templates/conversation_detail.html"
echo "Backup: $backup"
