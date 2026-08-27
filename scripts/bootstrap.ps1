# venv 생성·설치 — m3d CLI 를 쓸 수 있게 만드는 단계 (설계서 §1-3).
# make 가 없는 환경이므로 CLI 이전 단계만 여기서 처리한다.
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root 'worker\.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $venv)) {
    Write-Host "venv 생성: $venv"
    py -3.12 -m venv $venv
}

& $python -m pip install --upgrade pip
& $python -m pip install -e "$root\worker[dev]"

# 선택 의존성은 실패해도 진행한다 — doctor 표에 FAIL 로 남는다 (설계서 §6-1)
foreach ($extra in @('geom', 'agents')) {
    Write-Host "선택 의존성 설치 시도: $extra"
    & $python -m pip install -e "$root\worker[$extra]"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "선택 의존성 '$extra' 설치 실패 — doctor 표에 FAIL 로 기록됩니다."
    }
}

& (Join-Path $venv 'Scripts\m3d.exe') doctor
