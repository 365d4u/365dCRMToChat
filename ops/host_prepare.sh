set -eu
sudo -n install -d -o ubuntu -g webgroup -m 755 /data/365dCRMToChat /data/365dCRMToChat/staging
systemctl is-active respond_to_msgsite
systemctl is-active respond_rabbitmq_consume
