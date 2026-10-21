"""Private stdin sink for non-database integration secrets. No values are printed."""
import os
import sys
from pathlib import Path
data=sys.stdin.buffer.read(16384)
assert data and b'CRM_TO_CHAT_AMQP_URL=' in data and b'CRM_MEDIA_TOKEN=' in data
assert b'DATABASE_' not in data and b'CONV_DB_' not in data
path=Path('/etc/365d-crm-to-chat.env')
assert not path.exists(), 'Target integration config already exists'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as file:file.write(data)
