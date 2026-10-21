set -eu
sudo -n install -d -m 755 /data/365dCRMToChat/staging/respond-retire-20261012
sudo -n tar -xzf /data/365dCRMToChat/staging/respond-retire-20261012.tar.gz -C /data/365dCRMToChat/staging/respond-retire-20261012
sudo -n systemd-run --quiet --wait --pipe --collect --unit=respond-chat-db-readonly-check \
  -p User=www-data -p Group=webgroup \
  -p EnvironmentFile=/var/www/respond_webhook/respond_to_msgsite/.env \
  -p WorkingDirectory=/var/www/respond_webhook/respond_to_msgsite \
  /var/www/respond_webhook/respond_to_msgsite/venv/bin/python \
  /data/365dCRMToChat/staging/respond-retire-20261012/ops/respond_retire_preflight.py
