param(
    [Parameter(Mandatory=$true)][string]$CommandFile,
    [string]$UploadFile,
    [string]$UploadDestination,
    [string]$DownloadFile,
    [string]$DownloadDestination,
    [ValidateSet('ssh_run.py','relay_consumer_runtime.py')][string]$TransportScript='ssh_run.py'
)
$ErrorActionPreference = 'Stop'
$targetSecret = (Get-Content -LiteralPath 'C:\Users\Administrator\.codex\secrets\respond_rabbitmq_consume_ssh_password.dpapi' -Raw).Trim() | ConvertTo-SecureString
$targetCredential = [pscredential]::new('ubuntu', $targetSecret)
$request = @{host='107.150.104.4';port=2208;username=$targetCredential.UserName;
    password=$targetCredential.GetNetworkCredential().Password;
    command=(Get-Content -LiteralPath $CommandFile -Raw);timeout=240}
if($UploadFile){$request.upload=@(@{local=$UploadFile;remote=$UploadDestination})}
if($DownloadFile){$request.download=@(@{local=$DownloadFile;remote=$DownloadDestination})}
$request | ConvertTo-Json -Compress -Depth 5 | python "$PSScriptRoot\$TransportScript"
exit $LASTEXITCODE
