# M0 완료 기준 §9 의 1~7 을 일괄 실행한다. 8(웹 스크린샷)은 수동이다.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'

$root = Split-Path -Parent $PSScriptRoot
$m3d = Join-Path $root 'worker\.venv\Scripts\m3d.exe'
$python = Join-Path $root 'worker\.venv\Scripts\python.exe'
$failed = @()

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Body,
        # doctor 는 설계상 항상 종료코드 0 을 유지한다(표 + 마지막 줄이 판정을 담는다 —
        # 이 설계는 바꾸지 않는다). $LASTEXITCODE 만 보면 필수 패키지 FAIL 을 놓친다.
        # 그래서 이 스텝만 출력을 캡처해 그대로 화면에 찍고, 실패 마커 문자열도 검사한다.
        [string]$FailPattern = $null
    )
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    # 네이티브 exe 가 아예 실행되지 못하면 $LASTEXITCODE 는 갱신되지 않고 이전 스텝의
    # 값을 그대로 들고 있어 이 스텝이 거짓으로 통과할 수 있다 — 실행 직전에 초기화한다.
    $global:LASTEXITCODE = 0
    if ($FailPattern) {
        $out = & $Body
        $out | ForEach-Object { Write-Host $_ }
        if (($out | Out-String) -match $FailPattern) {
            $script:failed += $Label
            Write-Host "FAIL: $Label" -ForegroundColor Red
            return
        }
    } else {
        & $Body
    }
    if ($LASTEXITCODE -ne 0 -or -not $?) {
        $script:failed += $Label
        Write-Host "FAIL: $Label" -ForegroundColor Red
    }
}

Invoke-Step '1. doctor'          { & $m3d doctor } -FailPattern '필수 \d+종 FAIL'
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
