param([Parameter(Mandatory=$true)][string]$ScriptFile)
$ErrorActionPreference='Stop'
$publicCode=[Convert]::ToBase64String([IO.File]::ReadAllBytes($ScriptFile))
$command=@'
sudo -n python3 - <<'PY'
import base64,subprocess
pid=subprocess.check_output(['systemctl','show','365d-crm-api','-p','MainPID','--value'],text=True).strip()
with open('/proc/'+pid+'/environ','rb') as f:
 env={k.decode():v.decode() for k,v in (p.split(b'=',1) for p in f.read().split(b'\0') if b'=' in p)}
subprocess.run(['/data/365d-crm/runtime/node/bin/node','--input-type=module'],input=base64.b64decode('__PUBLIC_CODE__'),env=env,check=True)
PY
'@
$command=$command.Replace('__PUBLIC_CODE__',$publicCode).Replace("`r",'')
$payload=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($command))
ssh -p 2209 -o BatchMode=yes -o ConnectTimeout=10 ubuntu@154.197.57.214 "echo $payload | base64 -d | bash"
exit $LASTEXITCODE
