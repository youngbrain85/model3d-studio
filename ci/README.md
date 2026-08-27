# CI 워크플로 (수동 설치 필요)

`ci/workflows/ci.yml` 을 `.github/workflows/ci.yml` 로 옮기면 CI 가 켜집니다.

```bash
mkdir -p .github/workflows && git mv ci/workflows/ci.yml .github/workflows/ci.yml
git rm -r --cached ci && rm -rf ci
git commit -m "ci: GitHub Actions 워크플로 활성화"
```

## 왜 바로 들어가 있지 않은가

이 리포에 커밋한 Claude Code GitHub App 에 `workflows` 권한이 없어서
`.github/workflows/` 아래 파일은 push 가 거부됩니다
(`refusing to allow a GitHub App to create or update workflow ... without workflows permission`).
git push 와 Contents API 양쪽에서 동일하게 막혔습니다.

권한을 부여하려면 GitHub App 설정에서 **Workflows: Read and write** 를 켜면 됩니다.
그 전에는 위 명령으로 사람이 직접 옮겨야 합니다.

## 이 워크플로가 하는 일

| job | 내용 |
|---|---|
| `web` | prettier·eslint·tsc·vitest·vite build |
| `worker` | ruff·mypy(strict)·pytest·`m3d contracts check` |
| `supabase` | PostgreSQL 16 컨테이너에 마이그레이션을 **실제 적용**하고 도메인 규칙 테스트 실행 |

각 job 의 명령은 전부 이 컨테이너에서 실행해 통과를 확인했습니다.
사용된 액션 버전(`actions/checkout@v7`, `actions/setup-node@v7`,
`pnpm/action-setup@v6`, `astral-sh/setup-uv@v10`)은 각 릴리스 페이지에서 확인했습니다.
