# =============================================================================
#  EDUX ULTIMATE LIFEFORM - RUN SCRIPT (POWERSHELL)
# =============================================================================

$ErrorActionPreference = "Stop"

try { chcp 65001 > $null } catch {}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   EDUX ULTIMATE LIFEFORM - KHOI TAO HE THONG TU DONG CMCU LMS" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$EmbedPython = Join-Path $ScriptDir "python_embed\python.exe"
$VenvDir = Join-Path $ScriptDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$EnvFile = Join-Path $ScriptDir ".env"
$ReqFile = Join-Path $ScriptDir "requirements.txt"
$ChromeProfile = Join-Path $ScriptDir "chrome_profile"

# 1. Kiem tra Python Portable tich hop san hoac moi truong may tinh
$ActivePython = $null
if (Test-Path $EmbedPython) {
    $ActivePython = $EmbedPython
    Write-Host "[v] Su dung Python Portable tich hop san (Chay ngay tren moi may khong can cai Python)!" -ForegroundColor Green
} else {
    # Kiem tra .venv co hoat dong binh thuong khong (tu dong phat hien va sua lech may cu)
    $venvValid = $false
    if (Test-Path $VenvPython) {
        try {
            $testOut = & $VenvPython -c "import sys; print(1)" 2>&1
            if ($LASTEXITCODE -eq 0 -and $testOut -match "1") {
                $venvValid = $true
            }
        } catch {}
        if (-not $venvValid) {
            Write-Host "[!] Phat hien .venv bi lech duong dan tu may khac. Dang tu dong tao lai..." -ForegroundColor Yellow
            Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if ($venvValid) {
        $ActivePython = $VenvPython
    } else {
        # Tim Python tren may tinh
        $SysPython = $null
        $pyCheck = Get-Command "py.exe" -ErrorAction SilentlyContinue
        if ($pyCheck) {
            $SysPython = "py"
        } else {
            $pythonCheck = Get-Command "python.exe" -ErrorAction SilentlyContinue
            if ($pythonCheck) {
                $SysPython = "python"
            } else {
                $defaultPyPath = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
                if (Test-Path $defaultPyPath) { $SysPython = $defaultPyPath }
            }
        }

        if (-not $SysPython) {
            Write-Host "[X] KHONG TIM THAY PYTHON TREN MAY TINH!" -ForegroundColor Red
            Write-Host "Vui long cai dat Python 3.10+ tu https://www.python.org" -ForegroundColor Yellow
            Exit 1
        }

        # Tao moi truong ao .venv moi
        Write-Host "[+] Dang tao moi truong ao (.venv)..." -ForegroundColor Cyan
        if ($SysPython -eq "py") {
            & py -3.11 -m venv .venv
            if (-not (Test-Path $VenvPython)) { & py -m venv .venv }
        } else {
            & $SysPython -m venv .venv
        }

        if (-not (Test-Path $VenvPython)) {
            Write-Host "[X] Loi tao moi truong ao .venv!" -ForegroundColor Red
            Exit 1
        }
        Write-Host "[v] Tao .venv thanh cong!" -ForegroundColor Green

        # Cai dat thu vien
        Write-Host "[+] Dang kiem tra va cai dat thu vien..." -ForegroundColor Cyan
        & $VenvPython -m pip install -r $ReqFile --quiet
        if ($LASTEXITCODE -ne 0) {
            & $VenvPython -m pip install playwright google-genai rich python-dotenv
        }
        $ActivePython = $VenvPython
    }
}

# 4. Kiem tra GEMINI_API_KEY
$hasKey = $false
if (Test-Path $EnvFile) {
    $envContent = Get-Content $EnvFile -Raw
    if ($envContent -match "GEMINI_API_KEY\s*=\s*(AIza[0-9A-Za-z_\-]+|[^\s#]+)") {
        $keyVal = $matches[1]
        if ($keyVal.Length -gt 10) {
            $hasKey = $true
        }
    }
}

if (-not $hasKey) {
    Write-Host ""
    Write-Host "---------------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  CAU HINH GEMINI API KEY (Lay mien phi tai https://aistudio.google.com/apikey)" -ForegroundColor Yellow
    Write-Host "---------------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
    
    $inputKey = ""
    while ([string]::IsNullOrWhiteSpace($inputKey)) {
        $inputKey = Read-Host "Nhap GEMINI_API_KEY cua ban"
        $inputKey = $inputKey.Trim()
    }

    $newEnv = "GEMINI_API_KEY=$inputKey`nGEMINI_MODEL=gemini-3.5-flash-lite`n"
    if (Test-Path $EnvFile) {
        Add-Content -Path $EnvFile -Value "`nGEMINI_API_KEY=$inputKey"
    } else {
        Set-Content -Path $EnvFile -Value $newEnv
    }
    Write-Host "[v] Da luu API key vao .env!" -ForegroundColor Green
}

# 5. Kiem tra va khoi chay Google Chrome that qua cong Remote Debugging 9222
$cdpReady = $false
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($res -and $res.Browser) {
        $cdpReady = $true
    }
} catch {}

if (-not $cdpReady) {
    Write-Host "[+] Dang khoi dong Google Chrome that (Port 9222)..." -ForegroundColor Cyan
    $chromePaths = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chromeExe = $null
    foreach ($p in $chromePaths) {
        if (Test-Path $p) { $chromeExe = $p; break }
    }

    if ($chromeExe) {
        # Xoa sach phien session cu de tranh Chrome khoi phuc lai cac tab loi/tab rac
        Remove-Item -Path (Join-Path $ChromeProfile "Default\Sessions\*") -Force -ErrorAction SilentlyContinue

        $launchArgs = "--remote-debugging-port=9222 --user-data-dir=`"$ChromeProfile`" --disable-features=OptimizationGuideModelDownloading,OptimizationHints,OptimizationGuideOnDeviceModel,OnDeviceModelExecution --disable-component-update --disk-cache-size=209715200 --media-cache-size=209715200 --no-default-browser-check --no-first-run https://edux.cmcu.edu.vn/student"
        Start-Process -FilePath $chromeExe -ArgumentList $launchArgs
        Start-Sleep -Seconds 3
    } else {
        Write-Host "[!] Khong tim thay Chrome theo duong dan tieu chuan. Bot se tu dong tim kiem." -ForegroundColor Yellow
    }
} else {
    Write-Host "[v] Da tim thay Google Chrome dang chay tren cong 9222!" -ForegroundColor Green
}

Write-Host ""
Write-Host "[+] Dang ket noi Bot vao Chrome..." -ForegroundColor Green
Write-Host ""

# 6. Khoi chay bot.py
try {
    & $ActivePython bot.py
} finally {
    $junk = @("optimization_guide_model_store", "component_crx_cache", "WasmTtsEngine", "GrShaderCache", "Default\Cache", "Default\Code Cache", "Default\Sessions")
    foreach ($j in $junk) {
        $jp = Join-Path $ChromeProfile $j
        if (Test-Path $jp) { Remove-Item -Path $jp -Recurse -Force -ErrorAction SilentlyContinue }
    }
    # Duy tri file khoa chan OptGuideOnDeviceModel 4GB
    $blocker = Join-Path $ChromeProfile "OptGuideOnDeviceModel"
    if (-not (Test-Path $blocker)) {
        New-Item -ItemType File -Path $blocker -Force | Out-Null
        Set-ItemProperty -Path $blocker -Name IsReadOnly -Value $true
    }
}
