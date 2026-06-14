param(
    [int]$MaxWaitSeconds = 30,
    [int]$MaxTotalSeconds = 40,
    [int]$DockerWaitSeconds = 20,
    [int]$OllamaWaitSeconds = 10
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$RunDir = Join-Path $Root ".codex-run"
$PidFile = Join-Path $RunDir "dev-pids.txt"
$StartedAt = Get-Date
$GlobalDeadline = $StartedAt.AddSeconds($MaxTotalSeconds)

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
Set-Content -Path $PidFile -Value "" -Encoding UTF8

function Write-Step($Message) {
    Write-Host $Message
}

function Add-Pid($Name, $Process) {
    "$Name=$($Process.Id)" | Add-Content -Path $PidFile -Encoding UTF8
}

function Set-Pid($Name, $PidValue) {
    $lines = @()
    if (Test-Path $PidFile) {
        $lines = @(Get-Content $PidFile | Where-Object { $_ -and $_ -notmatch "^$Name=" })
    }
    $lines += "$Name=$PidValue"
    Set-Content -Path $PidFile -Value $lines -Encoding UTF8
}

function Get-PortPid($Port) {
    $lines = netstat -ano 2>$null | Select-String -Pattern "LISTENING"
    foreach ($line in $lines) {
        $text = $line.ToString().Trim()
        if ($text -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            $pidValue = [int]$Matches[1]
            if ($pidValue -gt 4) {
                return $pidValue
            }
        }
    }
    return $null
}

function Tail-Log($Path) {
    if (Test-Path $Path) {
        Write-Host "----- $([System.IO.Path]::GetFileName($Path)) -----"
        Get-Content -Path $Path -Tail 40 -ErrorAction SilentlyContinue
    }
}

function Start-LoggedProcess($Name, $FilePath, [string[]]$Arguments, $WorkingDirectory) {
    $OutLog = Join-Path $RunDir "$Name.out.log"
    $ErrLog = Join-Path $RunDir "$Name.err.log"
    Remove-Item -LiteralPath $OutLog, $ErrLog -Force -ErrorAction SilentlyContinue

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -WindowStyle Hidden `
        -PassThru

    Add-Pid $Name $process
    return $process
}

function Find-OllamaExe {
    $command = Get-Command "ollama" -ErrorAction SilentlyContinue
    if ($command -and (Test-Path $command.Source)) {
        return $command.Source
    }

    $localApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $localApp) {
        return $localApp
    }

    return $null
}

function Wait-Port($Port) {
    $portDeadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    $deadline = if ($portDeadline -lt $GlobalDeadline) { $portDeadline } else { $GlobalDeadline }
    while ((Get-Date) -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $task = $client.ConnectAsync("127.0.0.1", $Port)
            if ($task.Wait(300) -and $client.Connected) {
                return $true
            }
        } catch {
            # keep waiting
        } finally {
            $client.Close()
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-Port($Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if ($task.Wait(300) -and $client.Connected) {
            return $true
        }
    } catch {
        return $false
    } finally {
        $client.Close()
    }
    return $false
}

function Write-ServiceStatus($Name, $Port, $Url) {
    if (Test-Port $Port) {
        Write-Host ("  {0,-14} OK       {1}" -f $Name, $Url)
    } else {
        Write-Host ("  {0,-14} PENDING  port {1} is not ready yet" -f $Name, $Port)
    }
}

function Start-OllamaIfNeeded {
    if (Test-Port 11434) {
        Write-Host "  Ollama already listening on port 11434."
        return $true
    }

    $ollamaExe = Find-OllamaExe
    if (-not $ollamaExe) {
        Write-Host "  WARN Ollama executable was not found. Install Ollama or add it to PATH."
        return $false
    }

    $OutLog = Join-Path $RunDir "ollama.out.log"
    $ErrLog = Join-Path $RunDir "ollama.err.log"
    Remove-Item -LiteralPath $OutLog, $ErrLog -Force -ErrorAction SilentlyContinue

    try {
        $process = Start-Process `
            -FilePath $ollamaExe `
            -ArgumentList @("serve") `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $OutLog `
            -RedirectStandardError $ErrLog `
            -WindowStyle Hidden `
            -PassThru
        Add-Pid "ollama" $process
    } catch {
        Write-Host "  WARN Failed to start Ollama: $($_.Exception.Message)"
        return $false
    }

    $deadline = (Get-Date).AddSeconds($OllamaWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port 11434) {
            Write-Host "  Ollama OK      http://localhost:11434"
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Host "  WARN Ollama did not open port 11434 within ${OllamaWaitSeconds}s."
    Tail-Log $ErrLog
    return $false
}

function Remaining-Milliseconds {
    $remaining = [int]($GlobalDeadline - (Get-Date)).TotalMilliseconds
    if ($remaining -lt 0) { return 0 }
    return $remaining
}

function Stop-StartedProcesses {
    & (Join-Path $PSScriptRoot "stop-dev.ps1") -NoPause
}

Write-Step "[0/4] Preflight..."
$Python = Join-Path $Backend "venv\Scripts\python.exe"
$Celery = Join-Path $Backend "venv\Scripts\celery.exe"
$Npm = "npm.cmd"

if (-not (Test-Path $Python)) {
    throw "backend venv not found: $Python"
}
if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
    throw "frontend package.json not found: $Frontend"
}

Write-Step "[1/5] Docker infra..."
$dockerOk = $false
try {
    $dockerInfoOut = Join-Path $RunDir "docker-info.out.log"
    $dockerInfoErr = Join-Path $RunDir "docker-info.err.log"
    $docker = Start-Process -FilePath "docker" -ArgumentList @("info") -PassThru -RedirectStandardOutput $dockerInfoOut -RedirectStandardError $dockerInfoErr
    if ($docker.WaitForExit([Math]::Min(3000, (Remaining-Milliseconds)))) {
        $dockerOk = $docker.ExitCode -eq 0
    } else {
        $docker.Kill()
        $dockerOk = $false
    }
} catch {
    $dockerOk = $false
}

if ($dockerOk) {
    $compose = Start-Process -FilePath "docker" -ArgumentList @("compose", "up", "-d") -WorkingDirectory $Root -PassThru -NoNewWindow
    $composeWaitMs = [Math]::Min($DockerWaitSeconds * 1000, (Remaining-Milliseconds))
    if (-not $compose.WaitForExit($composeWaitMs)) {
        $compose.Kill()
        Write-Host "  WARN docker compose did not finish within ${DockerWaitSeconds}s. Continuing app startup."
    } elseif ($compose.ExitCode -ne 0) {
        Write-Host "  WARN docker compose returned exit code $($compose.ExitCode). Check Docker Desktop and image pull logs."
    } else {
        Write-Host "  Docker compose command completed."
    }
} else {
    Write-Host "  WARN Docker Desktop is not running. Skipping docker compose."
}

Write-Host ""
Write-Host "Infra status snapshot:"
Write-ServiceStatus "PostgreSQL" 5433 "localhost:5433"
Write-ServiceStatus "Redis" 6379 "localhost:6379"
Write-ServiceStatus "Elasticsearch" 9200 "http://localhost:9200"
Write-ServiceStatus "Kibana" 5601 "http://localhost:5601"
Write-ServiceStatus "Ollama" 11434 "http://localhost:11434"

Write-Step "[2/5] Ollama..."
Start-OllamaIfNeeded | Out-Null

Write-Step "[3/5] FastAPI (port 8000)..."
Start-LoggedProcess "fastapi" $Python @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") $Backend | Out-Null

Write-Step "[4/5] Celery Worker..."
if (Test-Path $Celery) {
    Start-LoggedProcess "celery" $Celery @("-A", "app.celery_app", "worker", "--loglevel=info", "--pool=solo") $Backend | Out-Null
} else {
    Start-LoggedProcess "celery" $Python @("-m", "celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--pool=solo") $Backend | Out-Null
}

Write-Step "[5/5] Next.js (port 3000)..."
Start-LoggedProcess "next" $Npm @("run", "dev") $Frontend | Out-Null

Write-Host ""
Write-Host "Waiting up to ${MaxWaitSeconds}s for app ports. Total startup budget: ${MaxTotalSeconds}s."
$fastapiReady = Wait-Port 8000
$nextReady = Wait-Port 3000

if ($fastapiReady) {
    $fastapiPortPid = Get-PortPid 8000
    if ($fastapiPortPid) {
        Set-Pid "fastapi" $fastapiPortPid
    }
}
if ($nextReady) {
    $nextPortPid = Get-PortPid 3000
    if ($nextPortPid) {
        Set-Pid "next" $nextPortPid
    }
}

Write-Host ""
if ($fastapiReady) {
    Write-Host "  FastAPI  OK      http://localhost:8000"
} else {
    Write-Host "  FastAPI  FAILED  port 8000 was not ready within ${MaxWaitSeconds}s"
}
if ($nextReady) {
    Write-Host "  Next.js  OK      http://localhost:3000"
} else {
    Write-Host "  Next.js  FAILED  port 3000 was not ready within ${MaxWaitSeconds}s"
}
Write-Host "  Swagger           http://localhost:8000/docs"
Write-Host "  Admin UI          http://localhost:3000/admin"
Write-Host "  Kibana            http://localhost:5601"

if (-not $fastapiReady -or -not $nextReady) {
    Write-Host ""
    Write-Host "EXCEPTION: Startup exceeded ${MaxWaitSeconds}s or a required port did not become ready."
    Tail-Log (Join-Path $RunDir "fastapi.err.log")
    Tail-Log (Join-Path $RunDir "next.err.log")
    Tail-Log (Join-Path $RunDir "celery.err.log")
    $nextErr = if (Test-Path (Join-Path $RunDir "next.err.log")) { Get-Content (Join-Path $RunDir "next.err.log") -Raw } else { "" }
    if ($nextErr -match "spawn EPERM") {
        Write-Host "DIAGNOSIS: Next.js failed because Node child_process.spawn returned EPERM."
        Write-Host "           In Codex sandbox this is expected; unsandboxed Node spawn diagnostic passed."
        Write-Host "           If this appears in a normal terminal, check Windows security/antivirus or Node install permissions."
    }
    Write-Host "Stopping started app processes..."
    Stop-StartedProcesses
    exit 1
}

exit 0
