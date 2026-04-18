$backendDir = "C:\Users\maksi\projects\vizard-arctic\backend"
$pythonExe = "C:\Users\maksi\projects\vizard-arctic\.venv\Scripts\python.exe"

while ($true) {
    $listening = netstat -ano | Select-String ":8000.*LISTENING"
    if ($listening) {
        Write-Host "Backend already running on port 8000"
        Start-Sleep -Seconds 10
        continue
    }
    Write-Host "Starting backend..."
    Set-Location $backendDir
    & $pythonExe run.py
    Write-Host "Backend exited, restarting in 3s..."
    Start-Sleep -Seconds 3
}
