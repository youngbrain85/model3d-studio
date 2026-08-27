# apps/worker — 파이프라인 워커

도면(CAD·PDF)과 사진을 읽어 판독·모델링·검증하는 Python 워커.
규칙 정본은 `docs/모델링규칙_지식베이스_v0.md` 이며, 이 패키지의 계약 모델과 검증기는
그 규칙의 구현이다.

## 실행

```bash
uv run --project apps/worker m3d doctor          # 환경 점검
uv run --project apps/worker m3d contracts check # 계약이 실제로 강제되는지 검증
uv run --project apps/worker m3d samples list
uv run --project apps/worker m3d samples ingest ab1_p4p5
uv run --project apps/worker m3d samples verify ab1_p4p5
```

## 구조

| 경로 | 내용 |
|---|---|
| `contracts/` | 공유 계약의 Python 대응물 (정본은 `packages/contracts/schemas/`) |
| `contracts/units.py` | mm↔m 변환의 **유일한** 장소 (규칙 §1) |
| `contracts/view_contract.py` | 뷰 계약 수학·왕복 검산 (규칙 §7) |
| `contracts/member_name.py` | 부재 명명 규칙 (규칙 §5) |
| `contracts/models.py` | pydantic 모델 — 규칙을 런타임에 강제 |
| `samples/` | 샘플 도면 세트 연결 (원본 읽기 전용, 매니페스트만 커밋) |
| `db.py` | Supabase REST 헬퍼 (`_db.py` 패턴) |

## 아직 없는 것

파이프라인 [2]~[8] (변환·카탈로그·판독·질문·모델링·검증·산출)은 M1 이후다.
