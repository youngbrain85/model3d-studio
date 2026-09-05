# M2a 검증 — 이 스크립트는 LLM 실호출을 하지 않는다.
# 멱등 스텝은 --cache-only 라 캐시 미스 시 API 를 부르지 않고 비0 종료한다.
# 전제: 로컬 캐시 data/derived/ab1-p4p5/llm-cache (gitignore) 가 있어야 한다.
# 실호출은 계획 Task 8 Step 2 의 수동 명령에서만 한다.
# 실패 목록에는 스텝 번호 외에 '3-4. usage.jsonl 과금 행 증가' 가 섞일 수 있다.
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'

# 콘솔 출력 인코딩을 UTF-8 로 바꾼다 — 이 머신 기본(CP949/ks_c_5601-1987)에서는 캡처된
# 한글 출력이 깨져 '실패 [1-9]' 같은 패턴이 조용히 매치되지 않는다(실측). finally 에서
# 원복해 호출 세션에 전역 설정을 남기지 않는다. exit 1 도 finally 를 거친다.
$prevEnc = [Console]::OutputEncoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    $root = Split-Path -Parent $PSScriptRoot
    $m3d = Join-Path $root 'worker\.venv\Scripts\m3d.exe'
    $python = Join-Path $root 'worker\.venv\Scripts\python.exe'
    $failed = @()

    function Invoke-Step {
        param(
            [string]$Label,
            [scriptblock]$Body,
            [string]$FailPattern = $null
        )
        Write-Host "`n=== $Label ===" -ForegroundColor Cyan
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

    # 과금 감지: 합계/개별 비용이 $0.0000 이 아니거나 실패가 1건 이상이면 FAIL.
    # ASCII 부분($x.xxxx)이 판정의 주축이다 — CP949 콘솔에서도 동작한다.
    $billed = '\$(?!0\.0000\b)\d+\.\d{4}|실패 [1-9]'

    # 세 번째 판정 근거: usage.jsonl 의 과금 행("cached": false) 이 3·4 스텝 전후로 늘지 않아야 한다.
    # 캐시 히트도 "cached": true 행을 적재하므로 총 행 수가 아니라 과금 행만 센다.
    # log_usage 는 json.dumps 기본 구분자라 문자열이 정확히 '"cached": false' 다.
    $usagePath = Join-Path $root 'data\derived\ab1-p4p5\usage.jsonl'
    function Count-Billed {
        param([string]$Path)
        if (-not (Test-Path $Path)) { return 0 }
        return @(Select-String -Path $Path -SimpleMatch '"cached": false').Count
    }

    Invoke-Step '1. pytest'              { & $python -m pytest (Join-Path $root 'worker\tests') -q }
    Invoke-Step '2. db check'            { & $m3d db check }

    $billedBefore = Count-Billed $usagePath
    Invoke-Step '3. read (cache-only)'   { & $m3d read ab1-p4p5 --cache-only }   -FailPattern $billed
    Invoke-Step '4. review (cache-only)' { & $m3d review ab1-p4p5 --cache-only } -FailPattern $billed
    $billedAfter = Count-Billed $usagePath
    Write-Host "usage.jsonl 과금 행: $billedBefore -> $billedAfter"
    if ($billedAfter -ne $billedBefore) {
        $failed += '3-4. usage.jsonl 과금 행 증가'
        Write-Host "FAIL: usage.jsonl 에 새 과금 행 $($billedAfter - $billedBefore)건" -ForegroundColor Red
    }

    # 1차 판정은 CLI 의 ASCII 줄(made=… skipped=… purged=… failures=… total=…)로 한다 —
    # purged>0 은 종료 코드에 반영되지 않고, 한글 패턴은 CP949 콘솔에서 조용히 빗나간다.
    Invoke-Step '5. crops'               { & $m3d crops ab1-p4p5 } -FailPattern 'purged=[1-9]|failures=[1-9]'

    Write-Host "`n=== 6. 크롭 3자 일치 판정 ===" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    $checkOut = (& $m3d db check) | Out-String
    Write-Host $checkOut
    if ($checkOut -match 'crops_ready=(\d+) crop_missing=(\d+) crops_assets=(\d+)') {
        $ready = [int]$Matches[1]
        $missing = [int]$Matches[2]
        $assets = [int]$Matches[3]
        $dir = Join-Path $root 'data\derived\ab1-p4p5\crops'
        $files = @(Get-ChildItem $dir -Filter *.png -ErrorAction SilentlyContinue).Count
        Write-Host "ready=$ready missing=$missing assets=$assets files=$files"
        if ($missing -ne 0 -or $ready -ne $files -or $ready -ne $assets) {
            $failed += '6. 크롭 3자 일치'
            Write-Host 'FAIL: crop_rel_path / assets / 파일 수가 어긋납니다.' -ForegroundColor Red
        }
    } else {
        $failed += '6. db check 판정 줄 없음'
        Write-Host 'FAIL: crops_ready=... 줄을 찾지 못했습니다.' -ForegroundColor Red
    }

    Write-Host "`n===== 요약 =====" -ForegroundColor Cyan
    if ($failed.Count -eq 0) {
        Write-Host '1~6 전부 통과 (무과금).' -ForegroundColor Green
    } else {
        Write-Host "실패 $($failed.Count)건: $($failed -join ', ')" -ForegroundColor Red
        Write-Host 'M2a 를 완료로 선언하지 마세요.' -ForegroundColor Red
        exit 1
    }
}
finally {
    [Console]::OutputEncoding = $prevEnc
}
