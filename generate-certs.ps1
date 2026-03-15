param(
    [string]$CommonName = "JoystickLocal",
    [int]$Days = 365,
    [string]$IpAddress
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LanIPv4 {
    $candidates = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.InterfaceAlias -notmatch "Loopback|vEthernet"
        }

    $preferred = $candidates |
        Where-Object { $_.InterfaceAlias -match "Wi-Fi|Wireless|Local Area Connection\*|Ethernet" } |
        Select-Object -First 1

    if ($preferred) {
        return $preferred.IPAddress
    }

    $fallback = $candidates | Select-Object -First 1
    if ($fallback) {
        return $fallback.IPAddress
    }

    return "127.0.0.1"
}

if (-not $IpAddress) {
    $IpAddress = Get-LanIPv4
}

$venvPythonPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".venv\Scripts\python.exe"
if (Test-Path $venvPythonPath) {
    $pythonSource = $venvPythonPath
}
else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "Python not found in PATH. Install Python 3.10+ and retry." -ForegroundColor Red
        exit 1
    }
    $pythonSource = $python.Source
}

$openssl = Get-Command openssl -ErrorAction SilentlyContinue

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

try {
    if (Test-Path "cert.pem") {
        Remove-Item "cert.pem" -Force
    }
    if (Test-Path "key.pem") {
        Remove-Item "key.pem" -Force
    }

    if ($openssl) {
        $san = "subjectAltName=DNS:localhost,IP:$IpAddress"

        & $openssl.Source req -x509 -newkey rsa:2048 -sha256 -days $Days -nodes `
            -keyout "key.pem" -out "cert.pem" -subj "/CN=$CommonName" -addext $san

        if ($LASTEXITCODE -ne 0) {
            throw "OpenSSL failed to generate certificate files."
        }

        Write-Host "Generated cert.pem and key.pem in $root (OpenSSL mode)" -ForegroundColor Green
    }
    else {
        Write-Host "OpenSSL not found. Switching to Python certificate generator..." -ForegroundColor Yellow

        & $pythonSource -c "import cryptography" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Installing cryptography package for certificate generation..." -ForegroundColor Yellow
            & $pythonSource -m pip install cryptography
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to install cryptography package automatically."
            }
        }

        & $pythonSource .\generate-certs.py --common-name $CommonName --days $Days --ip-address $IpAddress --out-dir .
        if ($LASTEXITCODE -ne 0) {
            throw "Python certificate generator failed."
        }
    }

    Write-Host "SAN includes IP: $IpAddress" -ForegroundColor Green
    Write-Host "Next: run 'python server.py' and open https://${IpAddress}:8443 on phone." -ForegroundColor Cyan
} finally {
    Pop-Location
}
