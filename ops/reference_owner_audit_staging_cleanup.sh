set -eu
if systemctl is-active --quiet crm-reference-owner-audit-plan-20261012.service; then exit 1;fi
sudo -n python3 - <<'PY'
from pathlib import Path
p=Path('/data/365dCRMToChat/staging/reference_owner_audit_import.py')
if p.exists():
 if p.is_symlink() or p.resolve()!=p:raise RuntimeError('unexpected_helper_path')
 p.unlink()
print('Removed completed preview helper; private snapshots and backups retained')
PY
