param(
    [int]$HttpTimeoutSeconds = 2,
    [int]$TcpTimeoutSeconds = 1,
    [int]$MaxSeconds = 35
)

$ErrorActionPreference = "Continue"
$startedAt = Get-Date
$results = New-Object System.Collections.Generic.List[object]

function Write-Step {
    param(
        [int]$No,
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )

    $elapsed = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
    $line = "[check:{0:D2}] {1,-28} {2,-5} {3} ({4}s)" -f $No, $Name, $Status, $Detail, $elapsed
    Write-Host $line
    $results.Add([pscustomobject]@{
        step = $No
        name = $Name
        status = $Status
        detail = $Detail
        elapsed_seconds = $elapsed
    }) | Out-Null
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        $ok = $task.Wait([TimeSpan]::FromSeconds($TimeoutSeconds))
        return $ok -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-HttpGet {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return @{ ok = $true; code = [int]$response.StatusCode; message = "HTTP $($response.StatusCode)" }
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        $message = if ($statusCode) { "HTTP $statusCode" } else { $_.Exception.Message }
        return @{ ok = $false; code = $statusCode; message = $message }
    }
}

Write-Host "Component check started. This script does not run LLM, upload, or long E2E flows."
Write-Host "HTTP timeout: ${HttpTimeoutSeconds}s, TCP timeout: ${TcpTimeoutSeconds}s, max budget: ${MaxSeconds}s"

function Test-Budget {
    return (((Get-Date) - $startedAt).TotalSeconds -lt $MaxSeconds)
}

$tcpChecks = @(
    @{ name = "Next.js UI"; host = "127.0.0.1"; port = 3000 },
    @{ name = "FastAPI"; host = "127.0.0.1"; port = 8000 },
    @{ name = "PostgreSQL"; host = "127.0.0.1"; port = 5433 },
    @{ name = "Redis"; host = "127.0.0.1"; port = 6379 },
    @{ name = "Elasticsearch"; host = "127.0.0.1"; port = 9200 },
    @{ name = "Kibana"; host = "127.0.0.1"; port = 5601 },
    @{ name = "Ollama"; host = "127.0.0.1"; port = 11434 }
)

$step = 1
$openPorts = @{}
foreach ($check in $tcpChecks) {
    if (-not (Test-Budget)) {
        Write-Step -No $step -Name $check.name -Status "SKIP" -Detail "max budget reached before TCP check"
        $step++
        continue
    }

    $ok = Test-TcpPort -HostName $check.host -Port $check.port -TimeoutSeconds $TcpTimeoutSeconds
    $openPorts[$check.port] = $ok
    $status = if ($ok) { "PASS" } else { "WARN" }
    $detail = if ($ok) { "port $($check.port) is listening" } else { "port $($check.port) is not listening" }
    Write-Step -No $step -Name $check.name -Status $status -Detail $detail
    $step++
}

$httpChecks = @(
    @{ name = "FastAPI root"; url = "http://127.0.0.1:8000/"; port = 8000 },
    @{ name = "FastAPI health"; url = "http://127.0.0.1:8000/api/v1/health"; port = 8000 },
    @{ name = "Elasticsearch health"; url = "http://127.0.0.1:9200/_cluster/health"; port = 9200 },
    @{ name = "Kibana status"; url = "http://127.0.0.1:5601/api/status"; port = 5601 },
    @{ name = "Ollama tags"; url = "http://127.0.0.1:11434/api/tags"; port = 11434 }
)

foreach ($check in $httpChecks) {
    if (-not $openPorts[$check.port]) {
        Write-Step -No $step -Name $check.name -Status "SKIP" -Detail "port $($check.port) is closed"
        $step++
        continue
    }

    if (-not (Test-Budget)) {
        Write-Step -No $step -Name $check.name -Status "SKIP" -Detail "max budget reached before HTTP check"
        $step++
        continue
    }

    $result = Test-HttpGet -Url $check.url -TimeoutSeconds $HttpTimeoutSeconds
    $status = if ($result.ok) { "PASS" } else { "WARN" }
    Write-Step -No $step -Name $check.name -Status $status -Detail $result.message
    $step++
}

$failCount = @($results | Where-Object { $_.status -eq "FAIL" }).Count
$warnCount = @($results | Where-Object { $_.status -eq "WARN" }).Count
$skipCount = @($results | Where-Object { $_.status -eq "SKIP" }).Count
$passCount = @($results | Where-Object { $_.status -eq "PASS" }).Count
$totalElapsed = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)

Write-Host ""
Write-Host "Summary: PASS=$passCount WARN=$warnCount SKIP=$skipCount FAIL=$failCount elapsed=${totalElapsed}s"
if ($warnCount -gt 0) {
    Write-Host "WARN means the component was not reachable within the short timeout. Start the service, then rerun this script."
}

if ($failCount -gt 0) {
    exit 1
}
