# M0 완료 기준 §9 의 1~7 을 일괄 실행한다. 8(웹 스크린샷)은 수동이다.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'

$root = Split-Path -Parent $PSScriptRoot
$m3d = Join-Path $root 'worker\.venv\Scripts\m3d.exe'
$python = Join-Path $root 'worker\.venv\Scripts\python.exe'
$failed = @()

function Invoke-Step {
    param([string]$Label, [scriptblock]$Body)
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) {
        $script:failed += $Label
        Write-Host "FAIL: $Label" -ForegroundColor Red
    }
}

Invoke-Step '1. doctor'         { & $m3d doctor }
Invoke-Step '2. samples collect' { & $m3d samples collect }
Invoke-Step '3. samples verify'  { & $m3d samples verify }
Invoke-Step '4. db apply'        { & $m3d db apply }
Invoke-Step '5-6. db check'      { & $m3d db check }
Invoke-Step '7. pytest'          { & $python -m pytest (Join-Path $root 'worker\tests') -q }

Write-Host "`n===== 요약 =====" -ForegroundColor Cyan
if ($failed.Count -eq 0) {
    Write-Host '1~7 전부 통과. 남은 것: 8(웹 헬스 화면 스크린샷).' -ForegroundColor Green
} else {
    Write-Host "실패 $($failed.Count)건: $($failed -join ', ')" -ForegroundColor Red
    Write-Host 'M0 를 완료로 선언하지 마세요.' -ForegroundColor Red
    exit 1
}
