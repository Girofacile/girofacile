param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$server = $null
try {
    Write-Host '=== GiroFacile: aggiorna e avvia ===' -ForegroundColor Cyan
    if (-not $CheckOnly) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
        try { $listener.Start() } catch { throw 'GiroFacile o un altro server e gia aperto sulla porta 8000. Chiudi il precedente terminale e riprova.' } finally { $listener.Stop() }
    }
    if (-not $CheckOnly) {
        $branch = & git branch --show-current
        if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Il progetto deve essere sul ramo main.' }
        $changes = & git status --porcelain --untracked-files=no
        if ($LASTEXITCODE -ne 0) { throw 'Impossibile controllare lo stato Git.' }
        if ($changes) { throw 'Ci sono modifiche locali non salvate in un commit. Aggiornamento interrotto per preservarle.' }
        $env:GIT_TERMINAL_PROMPT = '0'
        Write-Host 'Aggiornamento da GitHub...'
        & git fetch origin
        if ($LASTEXITCODE -ne 0) { throw 'Download da GitHub fallito. Controlla connessione e accesso Git.' }
        & git merge --ff-only origin/main
        if ($LASTEXITCODE -ne 0) { throw 'Aggiornamento non possibile senza risolvere le differenze locali.' }
    }
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & py -3.11 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Installa Python 3.11 per creare il primo ambiente locale.' }
    }
    if (-not $CheckOnly) {
        Write-Host 'Controllo e aggiornamento dipendenze...'
        & $python -m pip install --disable-pip-version-check -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze fallita.' }
    }
    $env:APP_ENV = 'development'
    $env:COOKIE_SECURE = 'false'
    $env:TRUST_PROXY_HEADERS = 'false'
    $env:DATABASE_URL = 'postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile'
    $env:BILLING_MODE = 'disabled'
    $env:APP_BASE_URL = 'http://127.0.0.1:8000'
    & $python -c "import uvicorn, psycopg2; c=psycopg2.connect(host='localhost',port=5432,dbname='girofacile',user='girofacile',password='girofacile_local',connect_timeout=5); c.close(); print('Python e database locale: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Database locale non disponibile. Verifica PostgreSQL e setup_postgres_locale.bat.' }
    if ($CheckOnly) { exit 0 }
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
    try { $listener.Start() } catch { throw 'La porta 8000 e gia occupata. Chiudi il precedente terminale GiroFacile e riprova.' } finally { $listener.Stop() }
    Write-Host 'Avvio server. Lascia questa finestra aperta; premi CTRL+C per fermarlo.'
    $server = Start-Process -FilePath $python -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -NoNewWindow -PassThru
    $url = 'http://127.0.0.1:8000/login'
    $ready = $false
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if ($server.HasExited) { throw 'Il server si e fermato durante l avvio. Leggi gli errori sopra.' }
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Il server non risponde entro 90 secondi.' }
    $chrome = @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($chrome) { Start-Process -FilePath $chrome -ArgumentList $url } else { Start-Process $url }
    Write-Host "GiroFacile pronto: $url" -ForegroundColor Green
    while (-not $server.HasExited) { Start-Sleep -Seconds 1 }
    if ($server.ExitCode -ne 0) { throw 'Il server si e arrestato con un errore.' }
} catch {
    Write-Host "ERRORE: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
}

