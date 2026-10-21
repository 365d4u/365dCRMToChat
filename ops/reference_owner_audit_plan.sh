set -eu
sudo -n systemd-run --quiet --wait --pipe --collect --unit=crm-reference-owner-audit-plan-20261012 \
 -p WorkingDirectory=/data/365dCRMToChat \
 -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
 -p EnvironmentFile=/data/365dCRMToChat/config/consumer.env \
 -p UMask=0077 -p CPUQuota=30% -p MemoryMax=512M \
 /data/365dCRMToChat/venv/bin/python /data/365dCRMToChat/staging/reference_owner_audit_import.py \
 /data/365dCRMToChat/state/reference-sync/snapshot.owner-audit-preview.ndjson
