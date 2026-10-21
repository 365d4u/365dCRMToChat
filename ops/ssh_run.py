"""Local SSH transport. Credentials arrive only through private process stdin."""
import json
import sys
from pathlib import Path
import paramiko

args = json.load(sys.stdin)
client = paramiko.SSHClient()
client.load_host_keys(str(Path.home() / '.ssh' / 'known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect(args['host'], port=args['port'], username=args['username'],
               password=args['password'], look_for_keys=False, allow_agent=False,
               timeout=15, banner_timeout=15, auth_timeout=15)
if args.get('download') or args.get('upload'):
    with client.open_sftp() as sftp:
        for entry in args.get('download', []): sftp.get(entry['remote'], entry['local'])
        for entry in args.get('upload', []): sftp.put(entry['local'], entry['remote'])
    if not args.get('command'):
        client.close()
        sys.exit(0)
_, stdout, stderr = client.exec_command(args['command'], timeout=args.get('timeout', 60))
sys.stdout.buffer.write(stdout.read())
sys.stderr.buffer.write(stderr.read())
status = stdout.channel.recv_exit_status()
client.close()
sys.exit(status)
