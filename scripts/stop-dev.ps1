param(
    [switch]$Docker,
    [switch]$Ollama,
    [switch]$NoPause
)

$ErrorActionPreference = "SilentlyContinue"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunDir = Join-Path $Root ".codex-run"
$PidFile = Join-Path $RunDir "dev-pids.txt"

function Get-PortPids($Port) {
    $lines = netstat -ano 2>$null | Select-String -Pattern "LISTENING"
    foreach ($line in $lines) {
        $text = $line.ToString().Trim()
        if ($text -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            $pidValue = [int]$Matches[1]
            if ($pidValue -gt 4) {
                $pidValue
            }
        }
    }
}

Write-Host "[1/5] Stopping tracked processes..."
if (Test-Path $PidFile) {
    Get-Content $PidFile | ForEach-Object {
        $parts = $_ -split "=", 2
        if ($parts.Length -eq 2) {
            $name = $parts[0]
            $pidValue = [int]$parts[1]
            if ($pidValue -gt 4) {
                Stop-Process -Id $pidValue -Force
                Write-Host "  Killed $name PID $pidValue"
            }
        }
    }
    Set-Content -Path $PidFile -Value "" -Encoding UTF8
}

Write-Host "[2/5] Stopping app ports..."
foreach ($port in @(8000, 3000)) {
    $pids = Get-PortPids $port | Select-Object -Unique
    foreach ($pidValue in $pids) {
        Stop-Process -Id $pidValue -Force
        Write-Host "  Killed port $port PID $pidValue"
    }
}

Write-Host "[3/5] Stopping known child processes in workspace..."
Get-Process python, node -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$Root*" } |
    ForEach-Object {
        Stop-Process -Id $_.Id -Force
        Write-Host "  Killed $($_.ProcessName) PID $($_.Id)"
    }

Write-Host "[4/5] Docker containers..."
if ($Docker) {
    docker compose -f (Join-Path $Root "docker-compose.yml") down
} else {
    Write-Host "  Docker containers are left running."
    Write-Host "  To stop Docker too: stop.bat --docker"
}

Write-Host "[5/5] Ollama..."
if ($Ollama) {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "ollama*" -or $_.Path -like "*\Ollama\*" } |
        ForEach-Object {
            Stop-Process -Id $_.Id -Force
            Write-Host "  Killed $($_.ProcessName) PID $($_.Id)"
        }
} else {
    Write-Host "  Ollama is left running."
    Write-Host "  To stop Ollama too: stop.bat --ollama"
}

Write-Host ""
Write-Host "Done."
if (-not $NoPause) {
    pause
}
