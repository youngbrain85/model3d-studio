#!/usr/bin/env bash
# SessionStart 훅 — Claude Code on the web 세션에서 의존성을 미리 깔아,
# 세션이 시작된 직후부터 린트·타입검사·테스트가 실제로 돌 수 있게 한다.
#
# 규칙 §6("검증 없이 완료 주장 금지")의 전제조건이다. 도구가 없으면 검증도 없다.
# 실패는 삼키지 않는다 — 설치가 안 되면 그 자리에서 크게 실패한다.
set -euo pipefail

# 로컬 개발 머신에서는 아무것도 하지 않는다. 웹 컨테이너 전용.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:?CLAUDE_PROJECT_DIR 가 없다}"

echo "▶ [1/2] Node 워크스페이스 (pnpm)"
if ! command -v pnpm >/dev/null 2>&1; then
  # package.json 의 packageManager 필드가 버전의 정본이다.
  corepack enable pnpm
fi
# --prefer-frozen-lockfile: 락파일이 package.json 과 맞으면 그대로 쓰고(재현성),
# 어긋나면 재해결한다(브랜치에서 의존성이 바뀌어도 세션이 벽돌이 되지 않는다).
pnpm install --prefer-frozen-lockfile

echo "▶ [2/2] Python 워커 (uv)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  # 세션의 나머지 턴에서도 uv 가 PATH 에 있어야 한다.
  [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
# uv 가 .python-version 을 보고 인터프리터까지 알아서 받아온다.
uv sync --project apps/worker --locked

echo "✓ 준비 완료 — pnpm run check / uv run --directory apps/worker pytest 가 바로 돈다"
