$env:VAULTSORT_SERVER_URL="http://192.168.0.247:2345"
$env:VAULTSORT_DIRS="D:\Downloads"

Write-Host "Starting VaultSort remote client..."
Write-Host "Connecting to server: $env:VAULTSORT_SERVER_URL"
Write-Host "Watching directory: $env:VAULTSORT_DIRS"
Write-Host "--------------------------------------------------"

.\vaultsort.exe client
