# contracts — web·worker 공유 계약

빌드 도구가 없는 순수 파일 디렉터리다. npm 패키지가 아니다.

## 정본

`supabase/migrations/*.sql` 이 정본이다. 아래 둘은 그 미러다.

| 파일 | 소비자 |
|---|---|
| `db.types.ts` | web (`@supabase/supabase-js` 제네릭) |
| `worker/src/m3d/models.py` | worker (Pydantic 검증) |

스키마를 바꾸면 **셋을 함께** 고친다. `worker/tests/test_migration_sql.py` 가
SQL 쪽 제약이 사라지는 것을 막아준다.

## 타입 생성 상태

`supabase gen types` 자동 생성을 시도한 결과를 여기에 기록한다.

- 최초 시도(설계 시점): `npx --yes supabase@latest gen types typescript --db-url
  $env:SUPABASE_DB_URL` 실패 (exit code 1). 당시 `SUPABASE_DB_URL` 이 미설정이라
  (프로젝트 소유자가 Supabase 프로젝트를 아직 만들지 않음) `$env:SUPABASE_DB_URL` 이
  빈 값으로 치환되어 `--db-url` 플래그에 값이 전달되지 않았다. Supabase CLI
  (`supabase@latest`, npx로 즉시 내려받아 실행)가 다음 에러로 종료했다:

  ```json
  {"_tag":"Error","error":{"code":"InvalidValue","message":"Missing value for flag --db-url. Expected: string"}}
  ```

  (그 직전에는 flags 파서가 인식하지 못한 상태로 커맨드 전체의 `--help` 문서를
  stderr 에 먼저 토해냈다 — CLI 자체의 동작이며 우리 쪽 설정 문제는 아니다.)
- 현재 상태 (2026-08-29): `SUPABASE_DB_URL` 은 이제 설정되어 있어 위 실패의 원인은
  더 이상 유효하지 않다. 다만 이 절을 갱신하려고 명령을 다시 실행하지는 않았다 —
  `--db-url` 값이 커맨드라인에 그대로 펼쳐지며 비밀번호를 담고 있어, 쉘 히스토리·
  프로세스 목록에 비밀키를 남기는 경로이기 때문이다(비밀키 취급은 `CLAUDE.md` §3).
- `db.types.ts` 의 출처: 수기 작성 (`supabase/migrations/0001_init.sql` 을 손으로
  옮김). M0 최종 리뷰에서 `0001_init.sql` 과 컬럼 단위로 대조해 드리프트가 없음을
  확인했다 — 자동 생성으로 바꿔야 할 이유가 검증되지 않아, 지금은 이 상태를
  **M0의 의도적 채택(deliberate keep)** 으로 둔다.

`supabase gen types` 를 통한 재생성은 M1의 선택 작업(optional)이다 — 필수가 아니다.
재생성하게 되면 수기 파일을 생성물로 교체하고 이 절을 갱신한다.
