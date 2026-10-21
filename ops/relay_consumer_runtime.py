"""Relay MQ runtime only over SSH. Database credentials never leave either host."""
import json
import subprocess
import sys
from pathlib import Path
import paramiko

args=json.load(sys.stdin)
source_script="""
from pathlib import Path
config=dict(line.split('=',1) for line in Path('/etc/365d-crm-to-chat.env').read_text().splitlines() if '=' in line)
assert config['CRM_TO_CHAT_AMQP_URL'] and config['CRM_TO_CHAT_WORKSPACE_IDS']
print('CRM_TO_CHAT_AMQP_URL='+config['CRM_TO_CHAT_AMQP_URL'])
print('CRM_TO_CHAT_WORKSPACE_IDS='+config['CRM_TO_CHAT_WORKSPACE_IDS'])
print('CRM_TO_CHAT_WRITE_ENABLED=false')
print('CRM_TO_CHAT_DB_ENV_STYLE=respond')
"""
client=paramiko.SSHClient()
client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
try:
    source=subprocess.run(['ssh','-p','2204','-o','BatchMode=yes','-o','ConnectTimeout=10',
        'root@165.154.134.51','python3 -'],input=source_script.encode(),stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,timeout=30)
    if source.returncode or not source.stdout.startswith(b'CRM_TO_CHAT_AMQP_URL='):
        raise RuntimeError('source configuration unavailable')
    client.connect(args['host'],port=args['port'],username=args['username'],password=args['password'],
        allow_agent=False,look_for_keys=False,timeout=15)
    command = "sudo -n python3 -c 'import os,sys; p=\"/data/365dCRMToChat/config/consumer.env\"; data=sys.stdin.buffer.read(); fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,data); os.close(fd)'"
    stdin,stdout,stderr=client.exec_command(command,timeout=20)
    stdin.write(source.stdout)
    stdin.flush()
    stdin.channel.shutdown_write()
    stdout.read()
    stderr.read()
    if stdout.channel.recv_exit_status():raise RuntimeError('target configuration unavailable')
    print('MQ runtime installed privately; writes remain disabled')
except Exception:
    print('Runtime relay failed; configuration values were not logged',file=sys.stderr)
    sys.exit(1)
finally:
    client.close()
