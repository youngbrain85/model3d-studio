# M1 변환·카탈로그 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DXF 50건을 페이지 단위 PNG 61장 + sheet_text JSON 61건으로 변환하고, 표제란 ATTRIB를 파일명과 기계 대조해 catalog_status(49 match / 0 mismatch / 1 unreadable)를 실증한다.

**Architecture:** 외관조사망도 프로젝트의 검증된 파이프라인(`render_pipeline.py`)을 `m3d` 모듈로 이식·분리. 도곽 감지→렌더→텍스트 추출은 `convert/`, 표제란 추출→대조는 `catalog/`. 추출은 전부 결정론, 검증은 기존 PNG 61장과의 지각 해시 회귀 대조.

**Tech Stack:** Python 3.12 · ezdxf · matplotlib(Agg) · PIL · numpy · psycopg (전부 M0 venv에 설치·검증 완료). 신규 의존성 없음.

**정본:** [설계서](../specs/2026-08-29-m1-convert-catalog-design.md). 본 계획의 §참조는 설계서 절 번호. 원 로직 참조원: `D:\Projects\Inspection\mbi_app_v2\assets\drawings_organized\_scripts\render_pipeline.py` (**읽기 전용**).

## Global Constraints

모든 태스크의 요구사항에 아래가 암묵적으로 포함된다.

- **venv Python**: `.\worker\.venv\Scripts\python.exe` (3.12.6). 기본 `python`(Anaconda 3.9) 금지.
- **`PYTHONUTF8=1`** 을 모든 파이썬 실행 전에 설정. 모든 텍스트 I/O에 `encoding="utf-8"` 명시.
- **참조 원본 읽기 전용**: `D:\Projects\Inspection\` 아래와 `data/samples/` 아래를 절대 쓰지 않는다. 산출물은 전부 `data/derived/`(gitignore).
- **고정 수량(실측 완료)**: DXF 50건 → 도곽 60 + 폴백 1 = **페이지 61** → PNG 61장·sheet_text 61건. catalog 기대값 **49 match / 0 mismatch / 1 unreadable** (unreadable = `C0050302-001`). 결과가 다르면 **기대값을 고치지 말고** 원인을 판독한다 — mismatch 발생은 실패가 아니라 편철 오류 검출의 실증으로 보고한다.
- **비밀키**: `SUPABASE_DB_URL` 값을 코드·보고서·출력에 절대 노출하지 않는다. `load_config()` 경유만.
- **DB 쓰기 범위**: `sheets`(*_from_content·catalog_status), `sheet_pages`(width/height_px), `assets`(derived 등재), migration 0002 적용까지만. seed 재실행·기존 행 삭제 금지.
- **`worker/src/m3d/cli.py`의 기존 구조 유지**: no-op `@app.callback()`(Task-1/M0), `samples`·`db` 서브앱, `seed` 명령을 지우지 않는다.
- **주석·CLI 출력·커밋 메시지는 한국어.** 커밋 트레일러: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- **테스트 개수**: 시작 기준 **91 passed**. 각 태스크의 기대 개수는 작성 시점 계산값 — 이전 태스크의 수정 루프로 ±될 수 있으므로 디스패치 시점의 실측이 우선한다(개수를 맞추려 테스트를 지우는 것 금지).
- **8000px 렌더는 느리다**(파일당 수십 초~수 분). 실렌더는 Task 6에서만, 그 외 태스크의 렌더 테스트는 `sheet_px=400` 축소로 한다.
- 실행 브랜치: 실행 시작 시 `feat/m1-convert-catalog` 를 main에서 분기(M0과 동일 방식 — 현재 폴더에서 feature 브랜치).

### 태스크 순서

| Task | 산출물 | 실DB/실렌더 |
|---|---|---|
| 1 | 인프라: derived_dir·gitignore·migration 0002 | DB 적용(0002) |
| 2 | `compare.py` — dHash 회귀 대조 | — |
| 3 | `convert/frames.py` — 도곽 감지·좌표 변환 | — |
| 4 | `convert/sheet_text.py` — 텍스트 추출·JSON | — |
| 5 | `convert/render.py` — ACI-7 가드 렌더 | — |
| 6 | `convert/run.py` + CLI — **실렌더 61장 + 회귀 대조 + 임계 확정** | 실렌더·DB |
| 7 | `catalog/titleblock.py`·`reconcile.py` | — |
| 8 | `catalog/run.py` + CLI + db check 확장 — **49/0/1 실증** | DB |

---

## Task 1: 인프라 — derived_dir·gitignore·migration 0002

**Files:**
- Modify: `.gitignore`
- Modify: `worker/src/m3d/config.py` (프로퍼티 1개 추가)
- Modify: `worker/tests/test_config.py` (테스트 1개 추가)
- Create: `supabase/migrations/0002_convert.sql`
- Test: `worker/tests/test_migration_0002.py`

**Interfaces:**
- Consumes: `m3d.config.Config`(M0), `m3d.db.discover_migrations`(M0)
- Produces:
  - `Config.derived_dir: Path` — `repo_root / "data" / "derived"`
  - migration `0002_convert` — `assets.kind`에 `'text'` 추가

- [ ] **Step 1: `.gitignore`에 derived 추가**

`data/samples/` 줄 다음에 한 줄 추가:

```gitignore
data/derived/
```

- [ ] **Step 2: 실패하는 config 테스트 추가**

`worker/tests/test_config.py`의 `test_repo_paths_are_under_repo_root` 바로 아래에 추가:

```python
def test_derived_dir_is_under_repo_root(tmp_path, absent_env, monkeypatch):
    """M1 산출물 루트 — 재생성 가능물이라 gitignore 대상이다."""
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    cfg = load_config(env_file=absent_env)
    assert cfg.derived_dir == cfg.repo_root / "data" / "derived"
```

- [ ] **Step 3: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_config.py -v
```

Expected: 1 failed (`AttributeError: 'Config' object has no attribute 'derived_dir'`), 나머지 passed.

- [ ] **Step 4: `config.py`에 프로퍼티 추가**

`Config`의 `fixtures_dir` 프로퍼티 바로 아래에:

```python
    @property
    def derived_dir(self) -> Path:
        return self.repo_root / "data" / "derived"
```

- [ ] **Step 5: config 테스트 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_config.py -v
```

Expected: 전부 passed (기존 8 + 신규 1 = 9).

- [ ] **Step 6: `supabase/migrations/0002_convert.sql` 작성**

```sql
-- M1: sheet_text JSON 을 assets 로 등재하기 위해 kind 에 'text' 추가 (설계서 §7).
-- 0001 의 inline check 는 assets_kind_check 로 자동 명명되었다.

alter table assets drop constraint assets_kind_check;
alter table assets add constraint assets_kind_check
  check (kind in ('dxf','pdf','png','photo','text'));
```

- [ ] **Step 7: 실패하는 migration 테스트 작성**

`worker/tests/test_migration_0002.py`:

```python
"""0002_convert — assets.kind 확장이 회귀로 사라지지 않게 고정한다."""

import re

import pytest

from m3d.config import REPO_ROOT
from m3d.db import discover_migrations


@pytest.fixture
def sql() -> str:
    path = REPO_ROOT / "supabase" / "migrations" / "0002_convert.sql"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def norm(sql) -> str:
    return re.sub(r"\s+", " ", sql)


def test_discovered_in_order():
    """마이그레이션 러너가 0001 다음에 0002 를 집는다."""
    versions = [m.version for m in discover_migrations(REPO_ROOT / "supabase" / "migrations")]
    assert versions == ["0001_init", "0002_convert"]


def test_drops_then_recreates_kind_check(norm):
    assert "drop constraint assets_kind_check" in norm
    assert "add constraint assets_kind_check" in norm


def test_new_kind_list_includes_text(norm):
    assert "check (kind in ('dxf','pdf','png','photo','text'))" in norm
```

- [ ] **Step 8: 실행해 통과 확인** (SQL을 Step 6에서 먼저 썼으므로 이 테스트는 바로 통과한다 — 3개 모두 green이면 정상)

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **95 passed** (91 + config 1 + migration_0002 3).

- [ ] **Step 9: 실DB에 0002 적용**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe db apply
```

Expected: `적용 1건: 0002_convert`. 재실행 시 `적용할 마이그레이션이 없습니다`.

- [ ] **Step 10: 적용 확인 (kind='text' 삽입이 통과하는지는 Task 6에서 실증 — 여기선 제약 존재만)**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -c "from m3d.config import load_config; import psycopg; cfg=load_config(); conn=psycopg.connect(cfg.require_db_url()); cur=conn.cursor(); cur.execute(\"select pg_get_constraintdef(oid) from pg_constraint where conname='assets_kind_check'\"); print(cur.fetchone()[0]); conn.close()"
```

Expected: 출력에 `'text'` 포함.

- [ ] **Step 11: 커밋**

```bash
git add .gitignore worker/src/m3d/config.py worker/tests/test_config.py supabase/migrations/0002_convert.sql worker/tests/test_migration_0002.py
git commit -m "feat(db): 0002_convert — assets.kind 에 'text' 추가 + derived_dir

- sheet_text JSON 등재 준비 (설계서 §7)
- Config.derived_dir = data/derived (gitignore — 재생성 가능물)
- 실DB 적용 완료, 멱등 재실행 확인

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: `compare.py` — dHash 회귀 대조

**Files:**
- Create: `worker/src/m3d/compare.py`
- Test: `worker/tests/test_compare.py`

**Interfaces:**
- Consumes: PIL, numpy (설치 완료)
- Produces:
  - `m3d.compare.HASH_SIZE: int` (= 16 → 256비트)
  - `m3d.compare.dhash(image: PIL.Image.Image, size: int = HASH_SIZE) -> int`
  - `m3d.compare.hamming(a: int, b: int) -> int`
  - `m3d.compare.compare_files(path_a: Path, path_b: Path) -> int` — 두 PNG의 dHash 해밍 거리 (0 = 지각적 동일)

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_compare.py`:

```python
"""dHash 회귀 대조 — 신규 렌더가 기존 PNG 와 지각적으로 같은지 재는 자."""

from PIL import Image, ImageDraw

from m3d.compare import compare_files, dhash, hamming


def _blank(w=400, h=300):
    return Image.new("RGB", (w, h), "white")


def _with_rect(x0, y0, x1, y1, w=400, h=300):
    img = _blank(w, h)
    ImageDraw.Draw(img).rectangle([x0, y0, x1, y1], fill="black")
    return img


def test_identical_images_distance_zero():
    a = _with_rect(50, 50, 200, 150)
    assert hamming(dhash(a), dhash(a.copy())) == 0


def test_tiny_change_small_distance():
    """3px 점 하나 추가 — 지각적으로 같은 시트로 판정돼야 한다."""
    a = _with_rect(50, 50, 200, 150)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([300, 250, 303, 253], fill="black")
    assert hamming(dhash(a), dhash(b)) <= 8


def test_different_layout_large_distance():
    """세로 줄무늬 vs 빈 화면 — 완전히 다른 시트."""
    a = _blank()
    b = _blank()
    d = ImageDraw.Draw(b)
    for x in range(0, 400, 20):
        d.rectangle([x, 0, x + 9, 300], fill="black")
    assert hamming(dhash(a), dhash(b)) >= 64


def test_resolution_invariance():
    """같은 그림의 2배 해상도 — dHash 는 리사이즈 기반이라 거리 0 근처여야 한다."""
    a = _with_rect(50, 50, 200, 150, 400, 300)
    b = _with_rect(100, 100, 400, 300, 800, 600)
    assert hamming(dhash(a), dhash(b)) <= 4


def test_compare_files_roundtrip(tmp_path):
    a = _with_rect(50, 50, 200, 150)
    pa = tmp_path / "a.png"
    pb = tmp_path / "b.png"
    a.save(pa)
    a.save(pb)
    assert compare_files(pa, pb) == 0
```

- [ ] **Step 2: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_compare.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'm3d.compare'`

- [ ] **Step 3: `worker/src/m3d/compare.py` 구현**

```python
"""지각 해시 회귀 대조 (설계서 §8-2).

신규 렌더 61장이 원 프로젝트 산출 PNG 61장과 지각적으로 같은지 잰다.
dHash: 그레이스케일 → (size+1)×size 축소 → 인접 픽셀 밝기 비교 비트열.
해밍 거리 0 = 지각 동일. 임계값은 Task 6 에서 실측으로 확정한다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # 8000px 렌더 (원 파이프라인 계승)

HASH_SIZE = 16  # 16×16 = 256비트


def dhash(image: Image.Image, size: int = HASH_SIZE) -> int:
    gray = image.convert("L").resize((size + 1, size), Image.LANCZOS)
    arr = np.asarray(gray, dtype=np.int16)
    bits = arr[:, 1:] > arr[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def compare_files(path_a: Path, path_b: Path) -> int:
    with Image.open(path_a) as ia, Image.open(path_b) as ib:
        return hamming(dhash(ia), dhash(ib))
```

- [ ] **Step 4: 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **100 passed** (95 + 5).

- [ ] **Step 5: 커밋**

```bash
git add worker/src/m3d/compare.py worker/tests/test_compare.py
git commit -m "feat(worker): dHash 지각 해시 회귀 대조

- 동일 0 / 미세 변화 소거리 / 다른 레이아웃 대거리 / 해상도 불변을 테스트로 고정
- 임계값은 Task 6 실측에서 확정 (설계서 §8-2)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: `convert/frames.py` — 도곽 감지·좌표 변환

**Files:**
- Create: `worker/src/m3d/convert/__init__.py`
- Create: `worker/src/m3d/convert/frames.py`
- Test: `worker/tests/test_frames.py`

**Interfaces:**
- Consumes: ezdxf
- Produces:
  - `m3d.convert.frames.MIN_FRAME_MM: float` (= 200.0)
  - `m3d.convert.frames.SheetFrame` — frozen dataclass: `page_no: int`, `x0: float`, `y0: float`, `x1: float`, `y1: float`, `scale: float | None`, `rot: int`(0..3, ×90° CCW), `paper_w: float | None`, `paper_h: float | None`, `fallback: bool = False`. 프로퍼티 `world_w`, `world_h`. 메서드 `contains(wx, wy, margin=1.0) -> bool`, `to_paper(wx, wy) -> tuple[float, float]`, `paper_to_world(px, py) -> tuple[float, float]`
  - `m3d.convert.frames.detect_frames(doc) -> list[SheetFrame]` — 도곽 감지, 미검출 시 **빈 리스트** (폴백 조립은 호출자)
  - `m3d.convert.frames.fallback_frame(doc) -> SheetFrame | None` — modelspace 전체 bbox 폴백 (빈 modelspace 면 None)

**이식 원본**: `render_pipeline.py`의 frames 블록 — 원 로직을 그대로 옮기되 `CXBLK*` 이름 필터 대신 **"BLK" 포함 + bbox ≥200mm** 휴리스틱 유지(설계서 §11 리스크: 이름 완전일치에 걸지 않는다).

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_frames.py`:

```python
"""도곽 감지 — 페이지 수·좌표 변환의 유일한 근원.

합성 DXF 로 검증한다: A0 도곽 블록(1189×841mm)을 스케일·회전 조합으로 삽입.
"""

import math

import ezdxf
import pytest

from m3d.convert.frames import SheetFrame, detect_frames, fallback_frame

PAPER_W, PAPER_H = 1189.0, 841.0


def _doc_with_frames(*inserts, block_name="CXBLKA1-구조"):
    """inserts: (insert_xy, scale, rotation_deg) 튜플들."""
    doc = ezdxf.new("R2018")
    blk = doc.blocks.new(block_name)
    blk.add_lwpolyline(
        [(0, 0), (PAPER_W, 0), (PAPER_W, PAPER_H), (0, PAPER_H)], close=True
    )
    # ATTDEF·TEXT 는 도곽 bbox 산정에서 제외돼야 한다 (원 로직 계승)
    blk.add_attdef("DI_DRWNO", insert=(2 * PAPER_W, 20))
    msp = doc.modelspace()
    for xy, scale, rot in inserts:
        msp.add_blockref(
            block_name, xy,
            dxfattribs={"xscale": scale, "yscale": scale, "rotation": rot},
        )
    return doc


def test_single_frame_world_rect():
    doc = _doc_with_frames(((1000.0, 2000.0), 200.0, 0.0))
    frames = detect_frames(doc)
    assert len(frames) == 1
    fr = frames[0]
    assert fr.page_no == 1 and not fr.fallback
    assert fr.scale == pytest.approx(200.0)
    assert (fr.x0, fr.y0) == pytest.approx((1000.0, 2000.0))
    assert fr.x1 == pytest.approx(1000.0 + PAPER_W * 200.0)
    assert fr.y1 == pytest.approx(2000.0 + PAPER_H * 200.0)
    assert (fr.paper_w, fr.paper_h) == pytest.approx((PAPER_W, PAPER_H))


def test_attdef_excluded_from_bbox():
    """ATTDEF 가 bbox 에 들어가면 도곽 폭이 2×PAPER_W 로 왜곡된다."""
    doc = _doc_with_frames(((0.0, 0.0), 1.0, 0.0))
    fr = detect_frames(doc)[0]
    assert fr.paper_w == pytest.approx(PAPER_W)


def test_two_frames_page_order_left_to_right():
    """같은 높이의 도곽 2개 — 왼쪽이 1페이지 (원 정렬: y 내림, x 오름)."""
    doc = _doc_with_frames(
        ((300000.0, 0.0), 200.0, 0.0),   # 오른쪽
        ((0.0, 0.0), 200.0, 0.0),        # 왼쪽
    )
    frames = detect_frames(doc)
    assert [f.page_no for f in frames] == [1, 2]
    assert frames[0].x0 < frames[1].x0


def test_rotated_90_frame():
    doc = _doc_with_frames(((5000.0, 1000.0), 100.0, 90.0))
    fr = detect_frames(doc)[0]
    assert fr.rot == 1
    # 90° CCW: world 폭 = paper 높이 × s, world 높이 = paper 폭 × s
    assert fr.world_w == pytest.approx(PAPER_H * 100.0)
    assert fr.world_h == pytest.approx(PAPER_W * 100.0)


def test_non_orthogonal_rotation_skipped():
    doc = _doc_with_frames(((0.0, 0.0), 100.0, 45.0))
    assert detect_frames(doc) == []


def test_small_block_not_a_frame():
    """200mm 미만 블록(범례 등)은 도곽이 아니다."""
    doc = ezdxf.new("R2018")
    blk = doc.blocks.new("CZBLK-LEGEND")
    blk.add_lwpolyline([(0, 0), (150, 0), (150, 100), (0, 100)], close=True)
    doc.modelspace().add_blockref("CZBLK-LEGEND", (0, 0))
    assert detect_frames(doc) == []


def test_to_paper_roundtrip_all_rotations():
    for rot in (0.0, 90.0, 180.0, 270.0):
        doc = _doc_with_frames(((1234.0, -777.0), 50.0, rot))
        fr = detect_frames(doc)[0]
        for pm in [(0.0, 0.0), (100.0, 200.0), (PAPER_W, PAPER_H), (600.5, 33.3)]:
            wx, wy = fr.paper_to_world(*pm)
            back = fr.to_paper(wx, wy)
            assert back == pytest.approx(pm, abs=1e-6), f"rot={rot} pm={pm}"


def test_to_paper_origin_is_frame_min_corner():
    doc = _doc_with_frames(((1000.0, 2000.0), 200.0, 0.0))
    fr = detect_frames(doc)[0]
    assert fr.to_paper(1000.0, 2000.0) == pytest.approx((0.0, 0.0))
    assert fr.to_paper(fr.x1, fr.y1) == pytest.approx((PAPER_W, PAPER_H))


def test_fallback_frame_from_extents():
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((10.0, 20.0), (510.0, 320.0))
    assert detect_frames(doc) == []
    fr = fallback_frame(doc)
    assert fr is not None and fr.fallback
    assert fr.scale is None and fr.paper_w is None
    assert (fr.x0, fr.y0) == pytest.approx((10.0, 20.0))
    assert (fr.x1, fr.y1) == pytest.approx((510.0, 320.0))
    # 폴백의 to_paper 는 world 오프셋 그대로
    assert fr.to_paper(110.0, 120.0) == pytest.approx((100.0, 100.0))


def test_fallback_empty_modelspace_is_none():
    doc = ezdxf.new("R2018")
    assert fallback_frame(doc) is None
```

- [ ] **Step 2: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_frames.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'm3d.convert'`

- [ ] **Step 3: `worker/src/m3d/convert/__init__.py` 작성**

```python
"""[2] 변환·정규화 — 도곽 감지·렌더·sheet_text (설계서 §4)."""
```

- [ ] **Step 4: `worker/src/m3d/convert/frames.py` 구현**

```python
"""도곽(시트 프레임) 감지와 world↔용지 mm 좌표 변환 (설계서 §1-2의 1).

원 로직: render_pipeline.py 의 frames 블록 이식. "BLK" 포함 블록명 + 정의 bbox
(ATTDEF/TEXT/MTEXT 제외) ≥200mm 휴리스틱 — 이름 완전일치에 걸지 않는다 (§11).
용지 좌표 원점은 도곽 world rect 의 최소 모서리다 (블록 정의 원점이 아님).
"""

from __future__ import annotations

from dataclasses import dataclass

from ezdxf import bbox as ezbbox

MIN_FRAME_MM = 200.0
_EXCLUDE_IN_BBOX = ("ATTDEF", "TEXT", "MTEXT")


@dataclass(frozen=True)
class SheetFrame:
    page_no: int
    x0: float
    y0: float
    x1: float
    y1: float
    scale: float | None      # world 단위 / 용지 mm. 폴백이면 None
    rot: int                 # 0..3 (×90° CCW)
    paper_w: float | None    # 용지 mm. 폴백이면 None
    paper_h: float | None
    fallback: bool = False

    @property
    def world_w(self) -> float:
        return self.x1 - self.x0

    @property
    def world_h(self) -> float:
        return self.y1 - self.y0

    def contains(self, wx: float, wy: float, margin: float = 1.0) -> bool:
        return (self.x0 - margin <= wx <= self.x1 + margin
                and self.y0 - margin <= wy <= self.y1 + margin)

    def to_paper(self, wx: float, wy: float) -> tuple[float, float]:
        """world → 용지 mm (원 로직 이식 — 회전 역변환 포함)."""
        rx, ry = wx - self.x0, wy - self.y0
        if self.scale is None:
            return rx, ry
        if self.rot == 0:
            px, py = rx, ry
        elif self.rot == 1:      # 90° CCW
            px, py = ry, self.world_w - rx
        elif self.rot == 2:
            px, py = self.world_w - rx, self.world_h - ry
        else:                    # 270°
            px, py = self.world_h - ry, rx
        return px / self.scale, py / self.scale

    def paper_to_world(self, px: float, py: float) -> tuple[float, float]:
        """용지 mm → world (M2 크롭이 같은 변환을 쓴다)."""
        if self.scale is None:
            return self.x0 + px, self.y0 + py
        s = self.scale
        if self.rot == 0:
            rx, ry = px * s, py * s
        elif self.rot == 1:
            rx, ry = self.world_w - py * s, px * s
        elif self.rot == 2:
            rx, ry = self.world_w - px * s, self.world_h - py * s
        else:
            rx, ry = py * s, self.world_h - px * s
        return self.x0 + rx, self.y0 + ry


def detect_frames(doc) -> list[SheetFrame]:
    msp = doc.modelspace()
    blkdef_cache: dict[str, tuple[float, float, float, float] | None] = {}
    raw: list[dict] = []

    for e in msp.query("INSERT"):
        name = e.dxf.name
        if "BLK" not in name.upper():
            continue
        if name not in blkdef_cache:
            try:
                bdef = doc.blocks.get(name)
                bb = ezbbox.extents(
                    (x for x in bdef if x.dxftype() not in _EXCLUDE_IN_BBOX),
                    fast=True,
                )
                blkdef_cache[name] = (
                    (bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y)
                    if bb.has_data else None
                )
            except Exception:
                blkdef_cache[name] = None
        pb = blkdef_cache[name]
        if pb is None:
            continue
        pw, ph = pb[2] - pb[0], pb[3] - pb[1]
        if pw < MIN_FRAME_MM or ph < MIN_FRAME_MM:
            continue

        sx = abs(e.dxf.xscale)
        rot = e.dxf.rotation % 360.0
        if min(abs(rot - a) for a in (0, 90, 180, 270, 360)) > 0.5:
            continue  # 직교 회전만 도곽으로 인정 (원 로직)
        r = round(rot / 90.0) % 4

        ins = e.dxf.insert
        corners = []
        for cx, cy in ((pb[0], pb[1]), (pb[2], pb[1]), (pb[2], pb[3]), (pb[0], pb[3])):
            x, y = cx * sx, cy * sx
            for _ in range(r):
                x, y = -y, x
            corners.append((ins.x + x, ins.y + y))
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        raw.append(dict(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys),
                        scale=sx, rot=r, pw=pw, ph=ph))

    raw.sort(key=lambda f: (round(f["y0"], 1) * -1, f["x0"]))
    return [
        SheetFrame(page_no=i, x0=f["x0"], y0=f["y0"], x1=f["x1"], y1=f["y1"],
                   scale=f["scale"], rot=f["rot"],
                   paper_w=f["pw"], paper_h=f["ph"])
        for i, f in enumerate(raw, start=1)
    ]


def fallback_frame(doc) -> SheetFrame | None:
    """도곽 미검출 시 modelspace 전체 bbox 로 1페이지 (원 로직의 폴백)."""
    bb = ezbbox.extents(doc.modelspace(), fast=True)
    if not bb.has_data:
        return None
    return SheetFrame(page_no=1,
                      x0=bb.extmin.x, y0=bb.extmin.y,
                      x1=bb.extmax.x, y1=bb.extmax.y,
                      scale=None, rot=0, paper_w=None, paper_h=None,
                      fallback=True)
```

- [ ] **Step 5: 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **110 passed** (100 + 10).

- [ ] **Step 6: 실 DXF 대조 (커밋 전 확인용 — 테스트 아님)**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -c "import ezdxf; from m3d.convert.frames import detect_frames, fallback_frame; d=ezdxf.readfile(r'data\samples\ab1-p4p5\dxf\C0050301-001.dxf'); print('2p 시트 도곽:', len(detect_frames(d))); d2=ezdxf.readfile(r'data\samples\ab1-p4p5\dxf\C0050302-001.dxf'); print('도곽부재:', len(detect_frames(d2)), '폴백:', fallback_frame(d2) is not None)"
```

Expected: `2p 시트 도곽: 2` / `도곽부재: 0 폴백: True`

- [ ] **Step 7: 커밋**

```bash
git add worker/src/m3d/convert worker/tests/test_frames.py
git commit -m "feat(worker): 도곽 감지·world↔용지mm 변환 (원 파이프라인 이식)

- BLK 포함 + bbox ≥200mm 휴리스틱, ATTDEF/TEXT 제외, 직교 회전만 인정
- 4회전 전부 to_paper↔paper_to_world 왕복 검증, 폴백 프레임 포함
- 실 DXF 대조: 2p 시트 도곽 2 / C0050302-001 도곽 0·폴백 성립

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: `convert/sheet_text.py` — 텍스트 추출·JSON

**Files:**
- Create: `worker/src/m3d/convert/sheet_text.py`
- Test: `worker/tests/test_sheet_text.py`

**Interfaces:**
- Consumes: `m3d.convert.frames.SheetFrame`
- Produces:
  - `m3d.convert.sheet_text.SCHEMA_VERSION: int` (= 1)
  - `m3d.convert.sheet_text.WorldText` — frozen dataclass: `x: float`, `y: float`, `h: float`, `text: str`, `kind: str`("TEXT"|"DIM")
  - `m3d.convert.sheet_text.collect_texts(doc) -> list[WorldText]` — modelspace TEXT/MTEXT + DIMENSION 지오메트리 블록
  - `m3d.convert.sheet_text.build_sheet_text(frame: SheetFrame, texts: list[WorldText], drawing_no: str) -> dict` — 설계서 §5 스키마의 JSON 직렬화 가능 dict
  - `m3d.convert.sheet_text.write_sheet_text(payload: dict, path: Path) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_sheet_text.py`:

```python
"""sheet_text — M2 판독의 입력 계약 (설계서 §5)."""

import json

import ezdxf
import pytest

from m3d.convert.frames import detect_frames, fallback_frame
from m3d.convert.sheet_text import (
    SCHEMA_VERSION,
    build_sheet_text,
    collect_texts,
    write_sheet_text,
)

PAPER_W, PAPER_H = 1189.0, 841.0


@pytest.fixture
def doc():
    d = ezdxf.new("R2018")
    blk = d.blocks.new("CXBLKA1-구조")
    blk.add_lwpolyline([(0, 0), (PAPER_W, 0), (PAPER_W, PAPER_H), (0, PAPER_H)], close=True)
    msp = d.modelspace()
    msp.add_blockref("CXBLKA1-구조", (0, 0), dxfattribs={"xscale": 200.0, "yscale": 200.0})
    # 도곽 내부: 용지 (100, 400)mm 위치, 높이 5mm → world (20000, 80000), h=1000
    msp.add_text("S=1:100", height=1000.0, dxfattribs={"insert": (20000.0, 80000.0)})
    # %%c 제어코드 — 제거돼야 한다
    msp.add_text("%%c2,800", height=700.0, dxfattribs={"insert": (40000.0, 40000.0)})
    # 도곽 밖 텍스트 — 페이지에서 제외돼야 한다
    msp.add_text("범위밖", height=1000.0, dxfattribs={"insert": (999999.0, 0.0)})
    return d


def test_collect_texts_kinds_and_control_codes(doc):
    texts = collect_texts(doc)
    strings = {t.text for t in texts}
    assert "S=1:100" in strings
    assert "2,800" in strings          # %%c 제거
    assert all(t.kind == "TEXT" for t in texts)


def test_build_filters_to_frame_and_converts_mm(doc):
    frame = detect_frames(doc)[0]
    payload = build_sheet_text(frame, collect_texts(doc), "C0050304-030")
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["drawing_no"] == "C0050304-030"
    assert payload["page_no"] == 1
    assert payload["paper_mm"] == pytest.approx([PAPER_W, PAPER_H])
    assert payload["scale"] == pytest.approx(200.0)
    assert payload["fallback"] is False
    strings = [t["text"] for t in payload["texts"]]
    assert "범위밖" not in strings
    row = next(t for t in payload["texts"] if t["text"] == "S=1:100")
    assert (row["x_mm"], row["y_mm"]) == pytest.approx((100.0, 400.0))
    assert row["h_mm"] == pytest.approx(5.0)


def test_texts_sorted_top_to_bottom(doc):
    frame = detect_frames(doc)[0]
    payload = build_sheet_text(frame, collect_texts(doc), "X")
    ys = [t["y_mm"] for t in payload["texts"]]
    assert ys == sorted(ys, reverse=True)


def test_fallback_payload_has_null_scale():
    d = ezdxf.new("R2018")
    d.modelspace().add_text("본문", height=300.0, dxfattribs={"insert": (100.0, 100.0)})
    fr = fallback_frame(d)
    payload = build_sheet_text(fr, collect_texts(d), "C0050302-001")
    assert payload["fallback"] is True
    assert payload["scale"] is None
    # 폴백은 world 크기·world 오프셋 그대로
    assert payload["paper_mm"][0] == pytest.approx(fr.world_w)
    row = payload["texts"][0]
    assert row["h_mm"] == pytest.approx(300.0)


def test_write_roundtrip_utf8(tmp_path, doc):
    frame = detect_frames(doc)[0]
    payload = build_sheet_text(frame, collect_texts(doc), "C0050304-030")
    path = tmp_path / "t.json"
    write_sheet_text(payload, path)
    raw = path.read_text(encoding="utf-8")
    assert json.loads(raw) == payload
```

- [ ] **Step 2: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_sheet_text.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.convert.sheet_text'`

- [ ] **Step 3: `worker/src/m3d/convert/sheet_text.py` 구현**

```python
"""sheet_text 추출 (설계서 §1-2의 4·§5) — 원 파이프라인의 텍스트 인벤토리 이식.

원 교훈: "치수 판독의 기준 소스는 항상 sheet.png + sheet_text".
TEXT/MTEXT + DIMENSION 지오메트리 블록 내 텍스트를 용지 mm 좌표로 덤프한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from m3d.convert.frames import SheetFrame

SCHEMA_VERSION = 1
_CONTROL_CODES = re.compile(r"%%[cdpu]", re.I)


@dataclass(frozen=True)
class WorldText:
    x: float
    y: float
    h: float
    text: str
    kind: str  # "TEXT" | "DIM"


def _clean(s: str) -> str:
    return _CONTROL_CODES.sub("", s).strip()


def collect_texts(doc) -> list[WorldText]:
    msp = doc.modelspace()
    out: list[WorldText] = []

    for e in msp.query("TEXT MTEXT"):
        try:
            if e.dxftype() == "TEXT":
                s, h, p = e.dxf.text, e.dxf.height, e.dxf.insert
            else:
                s, h, p = e.plain_text(), e.dxf.char_height, e.dxf.insert
            s = _clean(s)
            if s:
                out.append(WorldText(p.x, p.y, h, s, "TEXT"))
        except Exception:
            pass  # 손상 엔티티는 건너뛴다 (원 로직 — 텍스트 하나에 전체를 죽이지 않음)

    for e in msp.query("DIMENSION"):
        try:
            bdef = doc.blocks.get(e.dxf.geometry)
            for t in bdef.query("TEXT MTEXT"):
                if t.dxftype() == "TEXT":
                    s, h, p = t.dxf.text, t.dxf.height, t.dxf.insert
                else:
                    s, h, p = t.plain_text(), t.dxf.char_height, t.dxf.insert
                s = _clean(s)
                if s:
                    out.append(WorldText(p.x, p.y, h, s, "DIM"))
        except Exception:
            pass

    return out


def build_sheet_text(frame: SheetFrame, texts: list[WorldText], drawing_no: str) -> dict:
    rows = []
    for t in texts:
        if not frame.contains(t.x, t.y):
            continue
        px, py = frame.to_paper(t.x, t.y)
        h_mm = t.h / frame.scale if frame.scale else t.h
        rows.append({"x_mm": round(px, 2), "y_mm": round(py, 2),
                     "h_mm": round(h_mm, 3), "kind": t.kind, "text": t.text})
    rows.sort(key=lambda r: (-r["y_mm"], r["x_mm"]))

    if frame.scale is not None:
        paper_mm = [frame.paper_w, frame.paper_h]
    else:
        paper_mm = [frame.world_w, frame.world_h]

    return {
        "schema": SCHEMA_VERSION,
        "drawing_no": drawing_no,
        "page_no": frame.page_no,
        "paper_mm": paper_mm,
        "scale": frame.scale,
        "rotation_deg": frame.rot * 90,
        "fallback": frame.fallback,
        "texts": rows,
    }


def write_sheet_text(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **115 passed** (110 + 5).

- [ ] **Step 5: 커밋**

```bash
git add worker/src/m3d/convert/sheet_text.py worker/tests/test_sheet_text.py
git commit -m "feat(worker): sheet_text 추출 — 용지 mm 좌표 JSON (M2 판독 입력 계약)

- TEXT/MTEXT + DIMENSION 블록 텍스트, %%c 제어코드 제거, 프레임 필터
- 좌표 변환·정렬(-y,x)·폴백 null scale 을 테스트로 고정 (설계서 §5)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: `convert/render.py` — ACI-7 가드 렌더

**Files:**
- Create: `worker/src/m3d/convert/render.py`
- Test: `worker/tests/test_render.py`

**Interfaces:**
- Consumes: `m3d.convert.frames.SheetFrame`
- Produces:
  - `m3d.convert.render.SHEET_PX: int` (= 8000)
  - `m3d.convert.render.DARKEN: dict[int, tuple[int, int, int]]` — 원 파이프라인 맵 그대로
  - `m3d.convert.render.prepare_doc(doc) -> None` — 폰트 강제·style 수리·밝은 색 어둡게 (제자리 변형)
  - `m3d.convert.render.render_frame(doc, frame: SheetFrame, out_png: Path, sheet_px: int = SHEET_PX) -> tuple[int, int]` — 렌더 후 실제 PNG (W, H) 반환
- **matplotlib import는 함수 내부에서만** — 부모 프로세스(오케스트레이터)가 이 모듈을 import해도 matplotlib이 로드되지 않아야 한다(멀티프로세싱 워커 격리, 원 파이프라인 방식).

- [ ] **Step 1: 실패하는 테스트 작성**

`worker/tests/test_render.py`:

```python
"""렌더 — ACI-7 가드가 살아있는지를 픽셀로 검증한다.

원 프로젝트 실사고: 배경 미지정 시 ACI-7(흑백 자동) 엔티티가 흰색으로 그려져
238파일에서 텍스트가 비가시화됐다. 여기서는 ACI-7 선을 그려 넣고
'어두운 픽셀이 실제로 존재하는가'를 단언한다 — 가드가 죽으면 전백 이미지가 된다.
"""

import ezdxf
import numpy as np
import pytest
from PIL import Image

from m3d.convert.frames import detect_frames
from m3d.convert.render import prepare_doc, render_frame

PAPER_W, PAPER_H = 1189.0, 841.0


@pytest.fixture
def doc():
    d = ezdxf.new("R2018")
    blk = d.blocks.new("CXBLKA1-구조")
    blk.add_lwpolyline([(0, 0), (PAPER_W, 0), (PAPER_W, PAPER_H), (0, PAPER_H)], close=True)
    msp = d.modelspace()
    msp.add_blockref("CXBLKA1-구조", (0, 0), dxfattribs={"xscale": 1.0, "yscale": 1.0})
    # ACI-7 (흑백 자동) 대각선 — 가드의 검증 대상
    msp.add_line((100, 100), (1000, 700), dxfattribs={"color": 7})
    return d


def test_render_size_and_aspect(tmp_path, doc):
    frame = detect_frames(doc)[0]
    out = tmp_path / "sheet.png"
    w, h = render_frame(doc, frame, out, sheet_px=400)
    assert out.is_file()
    with Image.open(out) as img:
        assert (img.width, img.height) == (w, h)
    assert max(w, h) == 400
    # 종횡비 ≈ 1189:841 (savefig 반올림 ±2px 허용)
    assert h == pytest.approx(400 * PAPER_H / PAPER_W, abs=2)


def test_aci7_renders_dark_on_white(tmp_path, doc):
    """ACI-7 선이 흰 배경 위에 '어둡게' 그려져야 한다 — 전백이면 가드 회귀."""
    frame = detect_frames(doc)[0]
    out = tmp_path / "sheet.png"
    render_frame(doc, frame, out, sheet_px=400)
    arr = np.asarray(Image.open(out).convert("L"))
    assert arr.min() < 100, "어두운 픽셀 없음 — ACI-7 가드가 죽었다"
    assert (arr > 240).mean() > 0.9, "배경이 흰색이 아니다"


def test_prepare_doc_darkens_bright_colors(doc):
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 10), dxfattribs={"color": 2})  # yellow
    prepare_doc(doc)
    line = [e for e in msp.query("LINE") if e.dxf.color == 2][0]
    assert line.rgb == (140, 115, 0)  # DARKEN 맵 (원 파이프라인)


def test_fills_drawn_before_lines(tmp_path, doc):
    """SOLID 가 선·텍스트를 덮지 않도록 선행 드로우 — 순서 로직만 픽셀로 확인.

    프레임 중앙에 SOLID 를 깔고 그 위 ACI-7 선을 긋는다. 선행 드로우가 맞으면
    선(어두움)이 SOLID(연회색) 위에 보인다 → 최암 픽셀이 SOLID 색보다 어둡다.
    """
    msp = doc.modelspace()
    solid = msp.add_solid([(80, 80), (1100, 80), (80, 760), (1100, 760)])
    solid.rgb = (200, 200, 200)
    frame = detect_frames(doc)[0]
    out = tmp_path / "sheet.png"
    render_frame(doc, frame, out, sheet_px=400)
    arr = np.asarray(Image.open(out).convert("L"))
    assert arr.min() < 100, "선이 SOLID 에 덮였다 — 선행 드로우 회귀"
```

- [ ] **Step 2: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_render.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.convert.render'`

- [ ] **Step 3: `worker/src/m3d/convert/render.py` 구현**

```python
"""시트 렌더 (설계서 §1-2의 2·3) — 원 파이프라인 이식.

계승한 실사고 해법 (원 _검증보고서.md):
  - ACI-7 가드: 배경 WHITE + set_colors("#FFFFFF") — 흑백 자동색이 검정으로 해석
  - HATCH/SOLID/WIPEOUT 선행 드로우 — 텍스트·선이 채움에 덮이지 않게
  - malgun.ttf 강제 + 깨진 style 참조 수리 — 한글 렌더
  - 드로우 실패 시 엔티티 개별 재시도 (PARTIAL — 하나 때문에 시트를 버리지 않음)

matplotlib 은 함수 내부에서만 import 한다 — 부모 프로세스 오염 방지 (멀티프로세싱).
"""

from __future__ import annotations

from pathlib import Path

from m3d.convert.frames import SheetFrame

SHEET_PX = 8000
DARKEN = {          # ACI → 흰 배경 가독 RGB (원 파이프라인 맵 그대로)
    2: (140, 115, 0),
    3: (0, 130, 0),
    4: (0, 120, 145),
    6: (170, 0, 170),
    8: (95, 95, 95),
    9: (110, 110, 110),
}
_FILL_FIRST = ("HATCH", "SOLID", "WIPEOUT")


def prepare_doc(doc) -> None:
    """폰트 강제·style 수리·밝은 색 어둡게 — 렌더 전 1회, 제자리 변형."""
    for style in doc.styles:
        try:
            style.dxf.font = "malgun.ttf"
            if style.dxf.hasattr("bigfont"):
                style.dxf.bigfont = ""
        except Exception:
            pass

    def _fix_styles(space):
        for e in space:
            try:
                if e.dxftype() in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
                    if e.dxf.hasattr("style") and e.dxf.style not in doc.styles:
                        e.dxf.style = "Standard"
            except Exception:
                pass

    def _darken(space):
        for e in space:
            try:
                c = e.dxf.color
                if c in DARKEN:
                    e.rgb = DARKEN[c]
            except Exception:
                pass

    msp = doc.modelspace()
    _fix_styles(msp)
    _darken(msp)
    for blk in doc.blocks:
        _fix_styles(blk)
        _darken(blk)
    for layer in doc.layers:
        if layer.color in DARKEN:
            layer.rgb = DARKEN[layer.color]


def render_frame(doc, frame: SheetFrame, out_png: Path,
                 sheet_px: int = SHEET_PX) -> tuple[int, int]:
    """프레임 하나를 PNG 로 렌더하고 실제 (W, H) 를 반환한다."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    try:
        font_manager.fontManager.addfont(r"C:\Windows\Fonts\malgun.ttf")
    except Exception:
        pass
    plt.rcParams["font.family"] = "Malgun Gothic"
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    from ezdxf import bbox as ezbbox
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing import matplotlib as ezmpl
    from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration

    msp = doc.modelspace()
    w, h = frame.world_w, frame.world_h
    margin = 0.005 * max(w, h)

    # 프레임과 겹치는 엔티티만 선별 (원 로직 — bbox 사전 계산)
    sel = []
    for e in msp:
        try:
            bb = ezbbox.extents([e], fast=True)
            if not bb.has_data:
                continue
            if (bb.extmax.x < frame.x0 - margin or bb.extmin.x > frame.x1 + margin
                    or bb.extmax.y < frame.y0 - margin or bb.extmin.y > frame.y1 + margin):
                continue
            sel.append(e)
        except Exception:
            continue

    # 채움 선행 드로우 — 텍스트·선이 SOLID/HATCH 배너에 덮이지 않게 (원 실사고 해법)
    sel.sort(key=lambda e: 0 if e.dxftype() in _FILL_FIRST else 1)

    def _draw(entities):
        fig = plt.figure(dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("#ffffff")
        cfg = Configuration(background_policy=BackgroundPolicy.WHITE)
        ctx = RenderContext(doc)
        backend = ezmpl.MatplotlibBackend(ax)
        fe = Frontend(ctx, backend, config=cfg)
        try:
            ctx.set_current_layout(msp)
        except Exception:
            pass
        try:
            # ACI-7 가드: 용지를 흰색으로 선언해 흑백 자동색이 검정으로 해석되게
            ctx.current_layout_properties.set_colors("#FFFFFF")
        except Exception:
            pass
        return fig, ax, backend, fe

    fig, ax, backend, fe = _draw(sel)
    skipped = 0
    try:
        fe.draw_entities(sel)
    except Exception:
        # 나쁜 엔티티 격리: 개별 재시도, 실패만 건너뜀 (원 PARTIAL 로직)
        plt.close(fig)
        fig, ax, backend, fe = _draw(sel)
        for e in sel:
            try:
                fe.draw_entities([e])
            except Exception:
                skipped += 1
    backend.finalize()

    ax.set_xlim(frame.x0, frame.x1)
    ax.set_ylim(frame.y0, frame.y1)
    ax.set_aspect("equal")
    if w >= h:
        fig.set_size_inches(sheet_px / 100.0, sheet_px / 100.0 * h / w)
    else:
        fig.set_size_inches(sheet_px / 100.0 * w / h, sheet_px / 100.0)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=100, facecolor="white")
    plt.close(fig)

    with Image.open(out_png) as img:
        return img.width, img.height
```

- [ ] **Step 4: 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **119 passed** (115 + 4).

- [ ] **Step 5: 실 DXF 저해상 스모크 (확인용 — 8000px는 Task 6에서)**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -c "import ezdxf, pathlib; from m3d.convert.frames import detect_frames; from m3d.convert.render import prepare_doc, render_frame; d=ezdxf.readfile(r'data\samples\ab1-p4p5\dxf\C0050304-030.dxf'); prepare_doc(d); fr=detect_frames(d)[0]; out=pathlib.Path(r'D:\Codex\Temp\claude\D--Projects-model3d-studio\17239b6f-413a-4eb6-befe-e9f80ec596a2\scratchpad\smoke_030.png'); print('size:', render_frame(d, fr, out, sheet_px=800))"
```

Expected: `size: (800, 5xx)` 부근 — 예외 없이 완주.

- [ ] **Step 6: 커밋**

```bash
git add worker/src/m3d/convert/render.py worker/tests/test_render.py
git commit -m "feat(worker): 시트 렌더 — ACI-7 가드·채움 선행·폰트 수리 (원 파이프라인 이식)

- ACI-7 가드를 픽셀 단언으로 고정 (전백이면 가드 회귀 — 원 238파일 실사고의 재발 방지)
- SOLID 위 선 가시성·DARKEN 맵·크기/종횡비 테스트
- matplotlib 은 함수 내부 import — 부모 프로세스 오염 방지

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: `convert/run.py` + CLI — 실렌더 61장·회귀 대조·임계 확정

> **가장 오래 걸리는 태스크.** 8000px 렌더 61장 — 4워커 병렬로도 수십 분. 멱등이므로 중단돼도 재실행하면 이어간다.

**Files:**
- Create: `worker/src/m3d/convert/run.py`
- Modify: `worker/src/m3d/cli.py` (`convert` 명령 추가)
- Test: `worker/tests/test_convert_run.py`

**Interfaces:**
- Consumes: Task 1~5 전부 + `m3d.samples.manifest.sha256_file` + `m3d.samples.source_manifest.SourceSheet, png_filenames` + psycopg
- Produces:
  - `m3d.convert.run.DHASH_WARN: int | None` — 회귀 대조 경고 임계 (초기 None → Step 9에서 실측값으로 확정)
  - `m3d.convert.run.PageJob` — frozen dataclass: `ord: str`, `drawing_no: str`, `title: str`, `page_count: int`, `dxf_path: str`, `out_png: str`, `out_text: str`(페이지별 리스트는 워커가 프레임 감지 후 확정)
  - `m3d.convert.run.plan_jobs(cfg, sheets_rows) -> list[PageJob]` — 순수: DB 행 → 파일 단위 작업
  - `m3d.convert.run.derived_paths(cfg, dataset, ord, drawing_no, page_no) -> tuple[Path, Path]` — 순수: (png, text json) 경로. 명명 `{ord}_{drawing_no}_p{n}.png/.json` (**1페이지도 `_p1`** — 파생물은 균일 명명)
  - `m3d.convert.run.worker_process(job_dict) -> dict` — 모듈 최상위(피클 가능): 1 DXF 처리 → `{"ord", "pages": [{page_no, png, png_sha, w, h, text, text_sha, fallback}], "error": str|None, "skipped_entities": int}`
  - `m3d.convert.run.run_convert(cfg, dataset, *, force=False, workers=4, compare=True) -> int` — 종료 코드
- CLI: `m3d convert <dataset> [--force] [--workers N] [--compare/--no-compare]`

- [ ] **Step 1: 실패하는 순수 로직 테스트 작성**

`worker/tests/test_convert_run.py`:

```python
"""convert 오케스트레이션의 순수 부분 — 경로 명명·작업 계획·회귀 쌍 매핑."""

import pytest

from m3d.config import load_config
from m3d.convert.run import derived_paths, plan_jobs, regression_pairs


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for key in ("SAMPLE_SOURCE_DIR", "REFERENCE_MODELS_DIR", "SUPABASE_DB_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SAMPLE_SOURCE_DIR", str(tmp_path))
    return load_config(env_file=tmp_path / "absent.env")


ROWS = [
    # (ord, drawing_no, title, page_count) — DB sheets 행 형태
    ("A02", "C0050301-002", "교량제원및특기사항(2)(접속1교)", 1),
    ("A01", "C0050301-001", "교량제원및특기사항(1)(접속1교)_(6차변경)", 2),
]


def test_derived_paths_uniform_p_suffix(cfg):
    png, text = derived_paths(cfg, "ab1-p4p5", "A02", "C0050301-002", 1)
    assert png.name == "A02_C0050301-002_p1.png"      # 1페이지도 _p1 (파생물 균일 명명)
    assert text.name == "A02_C0050301-002_p1.json"
    assert "data" in png.parts and "derived" in png.parts


def test_plan_jobs_one_per_dxf(cfg):
    jobs = plan_jobs(cfg, ROWS, "ab1-p4p5")
    assert len(jobs) == 2
    by_ord = {j.ord: j for j in jobs}
    assert by_ord["A01"].page_count == 2
    assert by_ord["A01"].dxf_path.endswith("C0050301-001.dxf")


def test_regression_pairs_maps_to_sample_names(cfg):
    """파생 p{n} ↔ 샘플 파일명 규칙(1p 접미 없음 / Np _pN) 매핑."""
    pairs = regression_pairs(cfg, "ab1-p4p5", ROWS)
    names = {(d.name, s.name) for d, s in pairs}
    assert ("A02_C0050301-002_p1.png",
            "A02_C0050301-002_교량제원및특기사항(2)(접속1교).png") in names
    assert ("A01_C0050301-001_p2.png",
            "A01_C0050301-001_교량제원및특기사항(1)(접속1교)_(6차변경)_p2.png") in names
    assert len(pairs) == 3  # 1 + 2 페이지
```

- [ ] **Step 2: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_convert_run.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.convert.run'`

- [ ] **Step 3: `worker/src/m3d/convert/run.py` 구현**

```python
"""convert 오케스트레이션 (설계서 §3) — DXF 50건 → 페이지 61건, 병렬·멱등·DB 반영.

워커(별도 프로세스)가 렌더·텍스트 추출을 하고, DB 쓰기는 부모가 한다.
멱등: 산출물 파일이 존재하고 sha256 이 DB 등재값과 같으면 그 파일 전체를 스킵.
실패는 수집해 마지막에 보고 — 한 파일 때문에 전체를 멈추지 않는다 (원 PARTIAL 정신).
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from m3d.compare import compare_files
from m3d.config import Config
from m3d.samples.manifest import sha256_file
from m3d.samples.source_manifest import SourceSheet, png_filenames

# 회귀 대조 경고 임계 (dHash 해밍 거리, 256비트 기준).
# Task 6 Step 9 에서 61쌍 실측 분포로 확정한다 — None 이면 분포만 보고.
DHASH_WARN: int | None = None


@dataclass(frozen=True)
class PageJob:
    ord: str
    drawing_no: str
    title: str
    page_count: int
    dxf_path: str
    dataset: str
    out_dir_png: str
    out_dir_text: str
    force: bool = False
    expected: dict | None = None   # rel_path → sha256 (DB 등재값, 스킵 판단용)


def derived_paths(cfg: Config, dataset: str, ord_: str, drawing_no: str,
                  page_no: int) -> tuple[Path, Path]:
    base = cfg.derived_dir / dataset
    stem = f"{ord_}_{drawing_no}_p{page_no}"
    return base / "png" / f"{stem}.png", base / "text" / f"{stem}.json"


def plan_jobs(cfg: Config, rows, dataset: str = "ab1-p4p5",
              force: bool = False, expected: dict | None = None) -> list[PageJob]:
    """rows: (ord, drawing_no, title, page_count) 반복 — DB sheets 조회 결과."""
    jobs = []
    base = cfg.derived_dir / dataset
    for ord_, drawing_no, title, page_count in rows:
        jobs.append(PageJob(
            ord=ord_, drawing_no=drawing_no, title=title, page_count=page_count,
            dxf_path=str(cfg.samples_dir / dataset / "dxf" / f"{drawing_no}.dxf"),
            dataset=dataset,
            out_dir_png=str(base / "png"),
            out_dir_text=str(base / "text"),
            force=force,
            expected=expected,
        ))
    return sorted(jobs, key=lambda j: j.ord)


def regression_pairs(cfg: Config, dataset: str, rows) -> list[tuple[Path, Path]]:
    """(파생 PNG, 샘플 PNG) 쌍 — 샘플명은 M0 파일명 규칙(1p 접미 없음)을 따른다."""
    pairs = []
    sample_png = cfg.samples_dir / dataset / "png"
    for ord_, drawing_no, title, page_count in rows:
        sheet = SourceSheet(ord=ord_, grade="핵심", drawing_no=drawing_no,
                            title=title, page_count=page_count)
        names = png_filenames(sheet)
        for page_no in range(1, page_count + 1):
            derived, _ = derived_paths(cfg, dataset, ord_, drawing_no, page_no)
            pairs.append((derived, sample_png / names[page_no - 1]))
    return pairs


def worker_process(job: dict) -> dict:
    """1 DXF 전체 처리 — 별도 프로세스에서 실행 (모듈 최상위, 피클 가능)."""
    import ezdxf
    from ezdxf import recover

    from m3d.convert.frames import detect_frames, fallback_frame
    from m3d.convert.render import prepare_doc, render_frame
    from m3d.convert.sheet_text import build_sheet_text, collect_texts, write_sheet_text
    from m3d.samples.manifest import sha256_file as _sha

    out = {"ord": job["ord"], "pages": [], "error": None, "skipped_entities": 0}
    try:
        # ── 멱등 스킵: 모든 산출물이 존재하고 DB 등재 sha 와 같으면 렌더 생략 ──
        expected = job.get("expected") or {}
        if not job["force"] and expected:
            reuse = []
            for page_no in range(1, job["page_count"] + 1):
                stem = f"{job['ord']}_{job['drawing_no']}_p{page_no}"
                png = Path(job["out_dir_png"]) / f"{stem}.png"
                txt = Path(job["out_dir_text"]) / f"{stem}.json"
                ok = (png.is_file() and txt.is_file()
                      and expected.get(f"png/{png.name}") == _sha(png)
                      and expected.get(f"text/{txt.name}") == _sha(txt))
                if not ok:
                    reuse = None
                    break
                from PIL import Image
                Image.MAX_IMAGE_PIXELS = None
                with Image.open(png) as img:
                    w, h = img.width, img.height
                reuse.append(dict(page_no=page_no, png=str(png), png_sha=_sha(png),
                                  w=w, h=h, text=str(txt), text_sha=_sha(txt),
                                  fallback=False, reused=True))
            if reuse is not None:
                out["pages"] = reuse
                return out

        # ── 실제 처리 ────────────────────────────────────────────────
        try:
            doc = ezdxf.readfile(job["dxf_path"])
        except Exception:
            doc, _aud = recover.readfile(job["dxf_path"])

        frames = detect_frames(doc)
        if not frames:
            fb = fallback_frame(doc)
            if fb is None:
                out["error"] = "빈 modelspace"
                return out
            frames = [fb]

        if len(frames) != job["page_count"]:
            out["error"] = (f"도곽 {len(frames)}개 ≠ page_count {job['page_count']} "
                            "(편철·페이지 구조 확인 필요)")
            return out

        prepare_doc(doc)
        texts = collect_texts(doc)

        for frame in frames:
            stem = f"{job['ord']}_{job['drawing_no']}_p{frame.page_no}"
            png = Path(job["out_dir_png"]) / f"{stem}.png"
            txt = Path(job["out_dir_text"]) / f"{stem}.json"
            w, h = render_frame(doc, frame, png)
            payload = build_sheet_text(frame, texts, job["drawing_no"])
            write_sheet_text(payload, txt)
            out["pages"].append(dict(
                page_no=frame.page_no, png=str(png), png_sha=_sha(png),
                w=w, h=h, text=str(txt), text_sha=_sha(txt),
                fallback=frame.fallback, reused=False))
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def _load_sheet_rows(conn, dataset: str):
    with conn.cursor() as cur:
        cur.execute(
            "select s.id, s.ord, s.drawing_no_from_filename, s.title_from_filename, "
            "s.page_count, s.project_id "
            "from sheets s join projects p on p.id = s.project_id "
            "where p.slug = %s order by s.ord",
            (dataset,),
        )
        return cur.fetchall()


def run_convert(cfg: Config, dataset: str, *, force: bool = False,
                workers: int = 4, compare: bool = True) -> int:
    import psycopg

    with psycopg.connect(cfg.require_db_url()) as conn:
        sheet_rows = _load_sheet_rows(conn, dataset)
        if not sheet_rows:
            typer.echo(f"프로젝트 '{dataset}' 의 sheets 가 없습니다 — seed 먼저.")
            return 1
        project_id = sheet_rows[0][5]

        # DB 등재 sha 맵 (멱등 스킵 판단) — derived 자산만
        with conn.cursor() as cur:
            cur.execute(
                "select rel_path, sha256 from assets "
                "where project_id = %s and rel_path like %s",
                (project_id, f"data/derived/{dataset}/%"),
            )
            expected = {}
            prefix = f"data/derived/{dataset}/"
            for rel, sha in cur.fetchall():
                expected[rel.removeprefix(prefix)] = sha

        # (ord, page_no) → sheet_page_id / ord → sheet_id
        with conn.cursor() as cur:
            cur.execute(
                "select sp.id, s.ord, sp.page_no from sheet_pages sp "
                "join sheets s on s.id = sp.sheet_id where s.project_id = %s",
                (project_id,),
            )
            page_ids = {(o, n): i for i, o, n in cur.fetchall()}
        sheet_ids = {r[1]: r[0] for r in sheet_rows}

        rows = [(r[1], r[2], r[3], r[4]) for r in sheet_rows]
        jobs = plan_jobs(cfg, rows, dataset, force=force, expected=expected)

        results, failures = [], []
        typer.echo(f"convert 시작: DXF {len(jobs)}건, 워커 {workers}")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(worker_process, asdict(j)): j for j in jobs}
            done = 0
            for fut in as_completed(futures):
                job = futures[fut]
                res = fut.result()
                done += 1
                if res["error"]:
                    failures.append((job.ord, res["error"]))
                    typer.echo(f"[{done}/{len(jobs)}] {job.ord} 실패: {res['error']}")
                    continue
                reused = all(p.get("reused") for p in res["pages"])
                label = "스킵(동일)" if reused else f"페이지 {len(res['pages'])}건"
                typer.echo(f"[{done}/{len(jobs)}] {job.ord} {label}")
                results.append((job, res))

        # ── DB 반영 (부모 프로세스) ──────────────────────────────────
        n_assets = 0
        with conn.cursor() as cur:
            for job, res in results:
                for p in res["pages"]:
                    sheet_id = sheet_ids[job.ord]
                    page_id = page_ids.get((job.ord, p["page_no"]))
                    cur.execute(
                        "update sheet_pages set width_px=%s, height_px=%s where id=%s",
                        (p["w"], p["h"], page_id),
                    )
                    for kind, path_key, sha_key in (("png", "png", "png_sha"),
                                                    ("text", "text", "text_sha")):
                        fpath = Path(p[path_key])
                        rel = fpath.relative_to(cfg.repo_root).as_posix()
                        cur.execute(
                            "insert into assets (project_id, sheet_id, sheet_page_id, "
                            "kind, role, rel_path, bytes, sha256) "
                            "values (%s,%s,%s,%s,'derived',%s,%s,%s) "
                            "on conflict (project_id, rel_path) do update set "
                            "bytes=excluded.bytes, sha256=excluded.sha256, "
                            "sheet_id=excluded.sheet_id, sheet_page_id=excluded.sheet_page_id",
                            (project_id, sheet_id, page_id, kind, rel,
                             fpath.stat().st_size, p[sha_key]),
                        )
                        n_assets += 1
        conn.commit()

    total_pages = sum(len(r["pages"]) for _, r in results)
    typer.echo(f"\n페이지 {total_pages}건 / assets 반영 {n_assets}건 / 실패 {len(failures)}건")
    for ord_, err in failures:
        typer.echo(f"  실패 {ord_}: {err}")

    # ── 회귀 대조 (설계서 §8-2) ─────────────────────────────────────
    if compare and not failures:
        pairs = regression_pairs(cfg, dataset, rows)
        report = []
        for derived, sample in pairs:
            if not (derived.is_file() and sample.is_file()):
                report.append({"derived": derived.name, "sample": sample.name,
                               "distance": None})
                continue
            report.append({"derived": derived.name, "sample": sample.name,
                           "distance": compare_files(derived, sample)})
        dists = [r["distance"] for r in report if r["distance"] is not None]
        rp = cfg.derived_dir / dataset / "compare_report.json"
        rp.write_text(json.dumps(
            {"pairs": report, "max": max(dists) if dists else None,
             "threshold": DHASH_WARN}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        typer.echo(f"\n회귀 대조 {len(dists)}쌍: 최대 {max(dists) if dists else '-'} / "
                   f"평균 {sum(dists)/len(dists):.1f}" if dists else "회귀 대조 쌍 없음")
        if DHASH_WARN is None:
            typer.echo("임계 미확정(DHASH_WARN=None) — 분포만 보고. 상위 5쌍:")
            for r in sorted(report, key=lambda r: -(r["distance"] or 0))[:5]:
                typer.echo(f"  {r['distance']:>4}  {r['derived']}")
        else:
            over = [r for r in report
                    if r["distance"] is None or r["distance"] > DHASH_WARN]
            for r in over:
                typer.echo(f"  임계 초과 {r['distance']}: {r['derived']} — 육안 확인 필요")
            typer.echo(f"임계 {DHASH_WARN} 초과: {len(over)}건")

    return 1 if failures else 0
```

- [ ] **Step 4: 순수 테스트 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **122 passed** (119 + 3).

- [ ] **Step 5: CLI에 convert 명령 추가**

`worker/src/m3d/cli.py` import에 추가:

```python
from m3d.convert import run as convert_run
```

`seed` 명령 아래에 추가:

```python
@app.command()
def convert(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그 (예: ab1-p4p5)"),
    force: bool = typer.Option(False, "--force", help="산출물이 있어도 재렌더"),
    workers: int = typer.Option(4, "--workers", help="병렬 워커 수"),
    compare: bool = typer.Option(True, "--compare/--no-compare",
                                 help="기존 샘플 PNG 와 지각 해시 회귀 대조"),
) -> None:
    """[2] DXF → 페이지 PNG + sheet_text JSON, DB 반영 (설계서 §3)."""
    cfg = load_config()
    raise typer.Exit(code=convert_run.run_convert(
        cfg, dataset, force=force, workers=workers, compare=compare))
```

- [ ] **Step 6: 실행 — 실렌더 61장 (수십 분, 중단돼도 재실행이 이어감)**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe convert ab1-p4p5
```

Expected: `페이지 61건 / assets 반영 122건 / 실패 0건` + 회귀 대조 61쌍 분포 출력(임계 미확정 모드). `C0050302-001`(A03)은 폴백 렌더로 포함.

- [ ] **Step 7: 멱등 재실행 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe convert ab1-p4p5
```

Expected: 50건 전부 `스킵(동일)`, 수 분 내 완료.

- [ ] **Step 8: DB 반영 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -c "from m3d.config import load_config; import psycopg; cfg=load_config(); conn=psycopg.connect(cfg.require_db_url()); cur=conn.cursor(); cur.execute(\"select count(*) from sheet_pages where width_px is not null\"); print('sheet_pages 크기 채움:', cur.fetchone()[0]); cur.execute(\"select kind, count(*) from assets where rel_path like 'data/derived/%' group by kind order by 1\"); print('derived assets:', cur.fetchall()); conn.close()"
```

Expected: `sheet_pages 크기 채움: 61` / `derived assets: [('png', 61), ('text', 61)]`

- [ ] **Step 9: 회귀 대조 임계 확정 (실측 → 상수 기입)**

`data/derived/ab1-p4p5/compare_report.json`의 분포를 읽고 판단한다:
- 최대 거리가 낮게(예: ≤24) 몰려 있으면 `DHASH_WARN = max + 여유(8)` 로 확정
- 넓게 흩어져 있으면 이상 쌍을 열어 육안 확인 후(나란히 저장) 사유와 함께 임계 결정
- `worker/src/m3d/convert/run.py`의 `DHASH_WARN` 을 실측값으로 바꾸고 주석에 근거를 남긴다:

```python
# 2026-08-29 실측: 61쌍 분포 최대 <M>·평균 <A> (compare_report.json)
# → 경고 임계 = 최대 + 8. 렌더러 계열이 같아 분포가 낮게 몰린다.
DHASH_WARN: int | None = <실측 최대 + 8>
```

그 후 `--no-compare` 없이 convert 재실행(스킵 경로) → `임계 N 초과: 0건` 확인.

- [ ] **Step 10: 커밋**

```bash
git add worker/src/m3d/convert/run.py worker/src/m3d/cli.py worker/tests/test_convert_run.py
git commit -m "feat(worker): m3d convert — 병렬 렌더·DB 반영·회귀 대조 (실측 61페이지)

- ProcessPoolExecutor 4워커, 렌더는 워커·DB 쓰기는 부모 (원 파이프라인 구조)
- 멱등: 산출물 sha == DB 등재값이면 파일 단위 스킵, --force 재렌더
- 도곽 수 ≠ page_count 를 실패로 수집 (페이지 구조 불일치 검출)
- 회귀 대조 61쌍 실측 분포로 DHASH_WARN 확정: <값> (근거 주석)
- 실측: 페이지 61 / assets 122 / 실패 0 / sheet_pages 크기 61 채움

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: `catalog/titleblock.py` + `reconcile.py` — 표제란 추출·대조 판정

**Files:**
- Create: `worker/src/m3d/catalog/__init__.py`
- Create: `worker/src/m3d/catalog/titleblock.py`
- Create: `worker/src/m3d/catalog/reconcile.py`
- Test: `worker/tests/test_titleblock.py`
- Test: `worker/tests/test_reconcile.py`

**Interfaces:**
- Consumes: ezdxf
- Produces:
  - `m3d.catalog.titleblock.TitleBlock` — frozen dataclass: `drawing_no: str`, `title: str`, `subtitle: str`, `scale: str`
  - `m3d.catalog.titleblock.extract_titleblocks(doc) -> list[TitleBlock]` — `DI_DRWNO` ATTRIB를 가진 INSERT 전부, 페이지 순서(y 내림, x 오름) 정렬
  - `m3d.catalog.reconcile.Verdict` — frozen dataclass: `status: str`("match"|"mismatch"|"unreadable"), `drawing_no: str | None`, `title: str | None`, `scale: str | None`, `notes: tuple[str, ...]`
  - `m3d.catalog.reconcile.normalize_title(s: str) -> str` — 공백(전각 `　` 포함) 전부 제거
  - `m3d.catalog.reconcile.reconcile(blocks: list[TitleBlock], drawing_no_filename: str, title_filename: str) -> Verdict`

**주의**: 추출은 블록 이름이 아니라 **`DI_DRWNO` ATTRIB 보유 여부**로 판정한다(설계서 §11 — 이름 완전일치에 걸지 않는다).

- [ ] **Step 1: 실패하는 titleblock 테스트 작성**

`worker/tests/test_titleblock.py`:

```python
"""표제란 ATTRIB 추출 — DI_DRWNO 보유 INSERT 가 곧 표제란이다."""

from pathlib import Path

import ezdxf
import pytest

from m3d.catalog.titleblock import TitleBlock, extract_titleblocks

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples" / "ab1-p4p5" / "dxf"


def _doc_with_titleblocks(*specs, block_name="CXBLKA1-구조"):
    """specs: (insert_xy, {tag: value}) — INSERT + ATTRIB 합성."""
    doc = ezdxf.new("R2018")
    doc.blocks.new(block_name)
    msp = doc.modelspace()
    for xy, tags in specs:
        ins = msp.add_blockref(block_name, xy)
        for tag, value in tags.items():
            ins.add_attrib(tag, value, insert=xy)
    return doc


def test_extracts_di_attribs():
    doc = _doc_with_titleblocks(
        ((0, 0), {"DI_DRWNO": "C0050304-030", "DI_TITLE": "강상형일반도(5)",
                  "DI_SUBTITLE": "(접속1교)", "DA_HSCALE": "H=1:100"}),
    )
    blocks = extract_titleblocks(doc)
    assert blocks == [TitleBlock("C0050304-030", "강상형일반도(5)", "(접속1교)", "H=1:100")]


def test_insert_without_di_drwno_ignored():
    doc = _doc_with_titleblocks(
        ((0, 0), {"NO": "P4"}),                       # 교각 번호 블록 — 표제란 아님
        ((10, 10), {"DI_DRWNO": "C0000000-001"}),
    )
    blocks = extract_titleblocks(doc)
    assert len(blocks) == 1
    assert blocks[0].drawing_no == "C0000000-001"
    assert blocks[0].title == ""                       # 태그 없으면 빈 문자열


def test_page_order_left_to_right():
    doc = _doc_with_titleblocks(
        ((500000, 0), {"DI_DRWNO": "P2"}),
        ((0, 0), {"DI_DRWNO": "P1"}),
    )
    assert [b.drawing_no for b in extract_titleblocks(doc)] == ["P1", "P2"]


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="샘플 세트 없음")
def test_real_normal_sheet():
    doc = ezdxf.readfile(SAMPLES / "C0050304-030.dxf")
    blocks = extract_titleblocks(doc)
    assert len(blocks) == 1
    assert blocks[0].drawing_no == "C0050304-030"
    assert "강상형일반도" in blocks[0].title.replace(" ", "").replace("　", "")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="샘플 세트 없음")
def test_real_frameless_sheet_has_no_titleblock():
    doc = ezdxf.readfile(SAMPLES / "C0050302-001.dxf")
    assert extract_titleblocks(doc) == []
```

- [ ] **Step 2: 실패하는 reconcile 테스트 작성**

`worker/tests/test_reconcile.py`:

```python
"""대조 판정 — 지식베이스 §3 '기계 대조' 의 구현 (설계서 §6)."""

from m3d.catalog.reconcile import Verdict, normalize_title, reconcile
from m3d.catalog.titleblock import TitleBlock


def _tb(drwno, title="제 목", subtitle="(부 제)", scale="H=1:100"):
    return TitleBlock(drwno, title, subtitle, scale)


def test_normalize_strips_all_whitespace_including_fullwidth():
    assert normalize_title("슬 래 브 일 반 도 (4)") == "슬래브일반도(4)"
    assert normalize_title("(접　속 1 교)") == "(접속1교)"


def test_no_blocks_is_unreadable():
    v = reconcile([], "C0050302-001", "접속1교종평면도(8차준공)(7차변경)")
    assert v.status == "unreadable"
    assert v.drawing_no is None and v.title is None and v.scale is None
    assert any("표제란 부재" in n for n in v.notes)


def test_single_match():
    v = reconcile([_tb("C0050304-030", "강상형일반도(5)", "(접속1교)")],
                  "C0050304-030", "강상형일반도(5)(접속1교)")
    assert v.status == "match"
    assert v.drawing_no == "C0050304-030"
    assert v.title == "강상형일반도(5) (접속1교)"   # 원문 결합 (정규화본 아님)
    assert v.notes == ()                            # 제목 포함 관계 성립 → 노트 없음


def test_mismatch_detected():
    """편철 오류 — 파일명과 내용의 도면번호가 다르다."""
    v = reconcile([_tb("C0050405-010")], "C0050305-040", "P10Tiedown상세도")
    assert v.status == "mismatch"
    assert v.drawing_no == "C0050405-010"           # 내용 유래 값을 저장
    assert any("C0050405-010" in n for n in v.notes)


def test_multipage_all_must_match():
    """다페이지 — 하나라도 다르면 mismatch (설계서 §6)."""
    v = reconcile([_tb("C0050301-001"), _tb("C0050301-999")],
                  "C0050301-001", "교량제원및특기사항(1)")
    assert v.status == "mismatch"


def test_multipage_consistent_match():
    v = reconcile([_tb("C0050301-001"), _tb("C0050301-001")],
                  "C0050301-001", "교량제원및특기사항(1)(접속1교)_(6차변경)")
    assert v.status == "match"


def test_title_not_contained_becomes_note_only():
    """제목 불일치는 판정에 영향 없음 — 노트만 (D4)."""
    v = reconcile([_tb("C0050304-030", "전혀다른제목", "")],
                  "C0050304-030", "강상형일반도(5)(접속1교)")
    assert v.status == "match"
    assert any("제목" in n for n in v.notes)


def test_filename_extra_suffix_is_ok():
    """파일명의 차수 접미 '(7차변경)' 은 정상 — 포함 관계로 흡수."""
    v = reconcile([_tb("C0050304-005", "슬 래 브 일 반 도 (5)", "(접 속 1 교)")],
                  "C0050304-005", "슬래브일반도(5)(접속1교)_(7차변경)")
    assert v.status == "match"
    assert not any("제목" in n for n in v.notes)


def test_empty_scale_stored_as_none():
    v = reconcile([_tb("X", scale="")], "X", "제목")
    assert v.scale is None
```

- [ ] **Step 3: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_titleblock.py worker\tests\test_reconcile.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.catalog'`

- [ ] **Step 4: `worker/src/m3d/catalog/__init__.py` 작성**

```python
"""[3] 카탈로그 — 표제란 추출·기계 대조 (설계서 §6)."""
```

- [ ] **Step 5: `worker/src/m3d/catalog/titleblock.py` 구현**

```python
"""표제란 ATTRIB 추출 (설계서 §1-1).

표준 도곽 블록(CXBLKA1 계열)의 속성에서 도면번호·제목·척도를 읽는다.
블록 이름이 아니라 DI_DRWNO ATTRIB 보유 여부로 판정한다 — 이름 변형에 안전 (§11).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TitleBlock:
    drawing_no: str
    title: str
    subtitle: str
    scale: str


def extract_titleblocks(doc) -> list[TitleBlock]:
    found = []
    for e in doc.modelspace().query("INSERT"):
        try:
            tags = {a.dxf.tag: (a.dxf.text or "").strip() for a in e.attribs}
        except Exception:
            continue
        if "DI_DRWNO" not in tags or not tags["DI_DRWNO"]:
            continue
        ins = e.dxf.insert
        found.append((round(-ins.y, 1), ins.x, TitleBlock(
            drawing_no=tags["DI_DRWNO"],
            title=tags.get("DI_TITLE", ""),
            subtitle=tags.get("DI_SUBTITLE", ""),
            scale=tags.get("DA_HSCALE", ""),
        )))
    found.sort(key=lambda t: (t[0], t[1]))   # 페이지 순서: y 내림, x 오름 (frames 와 동일)
    return [t[2] for t in found]
```

- [ ] **Step 6: `worker/src/m3d/catalog/reconcile.py` 구현**

```python
"""기계 대조 판정 (설계서 §6) — 지식베이스 §3 의 구현.

판정 기준은 도면번호 하나다. 제목·척도는 원문 저장 + 노트(D4).
다페이지는 전 도곽 검사 — 페이지 간 번호 불일치도 편철 오류다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from m3d.catalog.titleblock import TitleBlock

_WS = re.compile(r"[\s　]+")


@dataclass(frozen=True)
class Verdict:
    status: str                    # match | mismatch | unreadable
    drawing_no: str | None
    title: str | None
    scale: str | None
    notes: tuple[str, ...]


def normalize_title(s: str) -> str:
    return _WS.sub("", s)


def reconcile(blocks: list[TitleBlock], drawing_no_filename: str,
              title_filename: str) -> Verdict:
    if not blocks:
        return Verdict("unreadable", None, None, None,
                       ("표제란 부재 — 도곽 블록 또는 DI_DRWNO 없음",))

    notes: list[str] = []
    first = blocks[0]

    content_nos = [b.drawing_no for b in blocks]
    if all(no == drawing_no_filename for no in content_nos):
        status = "match"
    else:
        status = "mismatch"
        distinct = sorted(set(no for no in content_nos if no != drawing_no_filename))
        notes.append(
            f"도면번호 불일치: 파일명 {drawing_no_filename} vs 내용 {', '.join(distinct)}"
        )

    title_raw = f"{first.title} {first.subtitle}".strip()
    content_norm = normalize_title(title_raw)
    if content_norm and content_norm not in normalize_title(title_filename):
        notes.append(f"제목 불일치(참고): 내용 '{title_raw}'")
    if len(blocks) > 1:
        others = {normalize_title(f"{b.title} {b.subtitle}".strip()) for b in blocks[1:]}
        if others - {content_norm}:
            notes.append("페이지 간 제목 상이(참고)")

    return Verdict(
        status=status,
        drawing_no=first.drawing_no,
        title=title_raw or None,
        scale=first.scale or None,
        notes=tuple(notes),
    )
```

- [ ] **Step 7: 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **136 passed** (122 + titleblock 5 + reconcile 9).

- [ ] **Step 8: 커밋**

```bash
git add worker/src/m3d/catalog worker/tests/test_titleblock.py worker/tests/test_reconcile.py
git commit -m "feat(worker): 표제란 추출·기계 대조 판정 (지식베이스 §3 구현)

- DI_DRWNO ATTRIB 보유 = 표제란 (블록 이름 비의존 — 설계서 §11)
- 판정은 도면번호 하나, 다페이지는 전 도곽 검사, 제목·척도는 원문 저장+노트
- 실 DXF 2장(정상·도곽부재) skipif 픽스처 포함

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 8: `catalog/run.py` + CLI + db check 확장 — 49/0/1 실증

**Files:**
- Create: `worker/src/m3d/catalog/run.py`
- Modify: `worker/src/m3d/cli.py` (`catalog` 명령 추가, `db check` 출력 확장)
- Modify: `worker/src/m3d/db.py` (`check()` 확장)
- Test: `worker/tests/test_catalog_run.py`

**Interfaces:**
- Consumes: Task 7 + psycopg + `m3d.config.Config`
- Produces:
  - `m3d.catalog.run.SheetVerdict` — frozen dataclass: `ord: str`, `drawing_no_filename: str`, `verdict: Verdict`, `changed: bool`
  - `m3d.catalog.run.build_report(results: list[SheetVerdict]) -> dict` — 순수: 카운트·비매치 목록·노트
  - `m3d.catalog.run.run_catalog(cfg, dataset, *, force=False) -> int`
  - `m3d.db.check()` 반환 dict에 키 추가: `catalog_status_counts: dict[str, int]`, `from_content_filled: int`, `pages_sized: int`
- CLI: `m3d catalog <dataset> [--force]`

- [ ] **Step 1: 실패하는 report 테스트 작성**

`worker/tests/test_catalog_run.py`:

```python
"""catalog 리포트 빌더 — 순수 부분만. DB 왕복은 §9 실행으로 검증."""

from m3d.catalog.reconcile import Verdict
from m3d.catalog.run import SheetVerdict, build_report


def _sv(ord_, drwno, status, notes=(), changed=True):
    return SheetVerdict(
        ord=ord_, drawing_no_filename=drwno,
        verdict=Verdict(status, drwno if status != "unreadable" else None,
                        "제목" if status != "unreadable" else None,
                        None, tuple(notes)),
        changed=changed,
    )


def test_counts_by_status():
    results = [
        _sv("A01", "C1", "match"),
        _sv("A02", "C2", "match"),
        _sv("A03", "C3", "unreadable", notes=("표제란 부재",)),
        _sv("B01", "C4", "mismatch", notes=("도면번호 불일치: ...",)),
    ]
    report = build_report(results)
    assert report["counts"] == {"match": 2, "mismatch": 1, "unreadable": 1}
    assert report["total"] == 4


def test_non_match_rows_listed_with_notes():
    results = [_sv("A03", "C3", "unreadable", notes=("표제란 부재",))]
    report = build_report(results)
    assert len(report["attention"]) == 1
    row = report["attention"][0]
    assert row["ord"] == "A03" and row["status"] == "unreadable"
    assert "표제란 부재" in row["notes"][0]


def test_notes_on_match_rows_are_kept():
    """match 라도 제목 노트는 리포트에 남는다 (참고 정보 유실 금지)."""
    results = [_sv("B02", "C9", "match", notes=("제목 불일치(참고): ...",))]
    report = build_report(results)
    assert len(report["attention"]) == 1


def test_changed_count():
    results = [_sv("A01", "C1", "match", changed=False),
               _sv("A02", "C2", "match", changed=True)]
    assert build_report(results)["changed"] == 1
```

- [ ] **Step 2: 실행해 실패 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests\test_catalog_run.py -v
```

Expected: `ModuleNotFoundError: No module named 'm3d.catalog.run'`

- [ ] **Step 3: `worker/src/m3d/catalog/run.py` 구현**

```python
"""catalog 오케스트레이션 (설계서 §3·§6) — 표제란 대조 실행·DB 갱신·리포트.

멱등: 산출 값이 DB 현재 값과 같으면 갱신하지 않는다 (changed=False).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import typer

from m3d.catalog.reconcile import Verdict, reconcile
from m3d.catalog.titleblock import extract_titleblocks
from m3d.config import Config


@dataclass(frozen=True)
class SheetVerdict:
    ord: str
    drawing_no_filename: str
    verdict: Verdict
    changed: bool


def build_report(results: list["SheetVerdict"]) -> dict:
    counts: dict[str, int] = {}
    attention = []
    for r in results:
        counts[r.verdict.status] = counts.get(r.verdict.status, 0) + 1
        if r.verdict.status != "match" or r.verdict.notes:
            attention.append({
                "ord": r.ord,
                "drawing_no_filename": r.drawing_no_filename,
                "status": r.verdict.status,
                "drawing_no_content": r.verdict.drawing_no,
                "notes": list(r.verdict.notes),
            })
    return {
        "total": len(results),
        "counts": counts,
        "changed": sum(1 for r in results if r.changed),
        "attention": attention,
    }


def run_catalog(cfg: Config, dataset: str, *, force: bool = False) -> int:
    import ezdxf
    import psycopg
    from ezdxf import recover

    results: list[SheetVerdict] = []
    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select s.id, s.ord, s.drawing_no_from_filename, s.title_from_filename, "
                "s.drawing_no_from_content, s.title_from_content, s.scale_from_content, "
                "s.catalog_status "
                "from sheets s join projects p on p.id = s.project_id "
                "where p.slug = %s order by s.ord",
                (dataset,),
            )
            rows = cur.fetchall()
        if not rows:
            typer.echo(f"프로젝트 '{dataset}' 의 sheets 가 없습니다 — seed 먼저.")
            return 1

        with conn.cursor() as cur:
            for (sheet_id, ord_, drwno_file, title_file,
                 cur_drwno, cur_title, cur_scale, cur_status) in rows:
                dxf = cfg.samples_dir / dataset / "dxf" / f"{drwno_file}.dxf"
                try:
                    try:
                        doc = ezdxf.readfile(dxf)
                    except Exception:
                        doc, _aud = recover.readfile(dxf)
                    blocks = extract_titleblocks(doc)
                except Exception as exc:
                    typer.echo(f"{ord_}: DXF 읽기 실패 — {type(exc).__name__}: {exc}")
                    return 1

                v = reconcile(blocks, drwno_file, title_file)
                same = (cur_status == v.status and cur_drwno == v.drawing_no
                        and cur_title == v.title and cur_scale == v.scale)
                if same and not force:
                    results.append(SheetVerdict(ord_, drwno_file, v, changed=False))
                    continue
                cur.execute(
                    "update sheets set drawing_no_from_content=%s, "
                    "title_from_content=%s, scale_from_content=%s, catalog_status=%s "
                    "where id=%s",
                    (v.drawing_no, v.title, v.scale, v.status, sheet_id),
                )
                results.append(SheetVerdict(ord_, drwno_file, v, changed=True))
        conn.commit()

    report = build_report(results)
    out = cfg.derived_dir / dataset / "catalog_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    counts = report["counts"]
    typer.echo(f"대조 {report['total']}건 — "
               f"match {counts.get('match', 0)} / "
               f"mismatch {counts.get('mismatch', 0)} / "
               f"unreadable {counts.get('unreadable', 0)} "
               f"(갱신 {report['changed']}건)")
    for row in report["attention"]:
        typer.echo(f"  [{row['status']}] {row['ord']} {row['drawing_no_filename']}")
        for note in row["notes"]:
            typer.echo(f"      {note}")
    typer.echo(f"리포트: {out}")
    return 1 if counts.get("mismatch", 0) > 0 else 0
    # mismatch 는 파이프라인 실패가 아니라 '검출 성공' 이지만, 사람이 봐야 하므로
    # 종료 코드 1 로 주의를 끈다 (지식베이스 §3: 불일치만 사람이 본다)
```

- [ ] **Step 4: `db.py` `check()` 확장**

`check()` 함수의 `projects` 조회 앞에 추가:

```python
        cur.execute(
            "select catalog_status, count(*) from sheets group by catalog_status"
        )
        catalog_status_counts = dict(cur.fetchall())

        cur.execute(
            "select count(*) from sheets where drawing_no_from_content is not null"
        )
        from_content_filled = cur.fetchone()[0]

        cur.execute(
            "select count(*) from sheet_pages "
            "where width_px is not null and height_px is not null"
        )
        pages_sized = cur.fetchone()[0]
```

반환 dict에 세 키 추가:

```python
    return {"counts": counts, "rls": rls, "projects": projects,
            "catalog_status_counts": catalog_status_counts,
            "from_content_filled": from_content_filled,
            "pages_sized": pages_sized}
```

- [ ] **Step 5: CLI 확장 — `catalog` 명령 + `db check` 출력**

`cli.py` import에 추가:

```python
from m3d.catalog import run as catalog_run
```

`convert` 명령 아래에 추가:

```python
@app.command()
def catalog(
    dataset: str = typer.Argument(..., help="데이터셋 슬러그 (예: ab1-p4p5)"),
    force: bool = typer.Option(False, "--force", help="값이 같아도 재기록"),
) -> None:
    """[3] 표제란 추출 → 파일명과 기계 대조 → catalog_status (설계서 §6)."""
    cfg = load_config()
    raise typer.Exit(code=catalog_run.run_catalog(cfg, dataset, force=force))
```

`db_check` 명령의 프로젝트 출력 앞에 추가:

```python
    if result["catalog_status_counts"]:
        dist = " / ".join(f"{k} {v}" for k, v in
                          sorted(result["catalog_status_counts"].items()))
        typer.echo(f"\ncatalog_status: {dist}")
        typer.echo(f"from_content 채움: {result['from_content_filled']} · "
                   f"페이지 크기 채움: {result['pages_sized']}")
```

- [ ] **Step 6: 테스트 통과 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **140 passed** (136 + 4).

- [ ] **Step 7: 실행 — 표제란 대조 50건**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe catalog ab1-p4p5; Write-Host "exit=$LASTEXITCODE"
```

Expected: `대조 50건 — match 49 / mismatch 0 / unreadable 1 (갱신 50건)`, attention에 `[unreadable] A03 C0050302-001` + `표제란 부재` 노트, `exit=0`.
결과가 49/0/1이 아니면 **기대값을 고치지 말고** attention 목록을 근거로 원인을 보고한다.

- [ ] **Step 8: 멱등 재실행**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe catalog ab1-p4p5
```

Expected: `... (갱신 0건)` — 두 번째는 DB를 건드리지 않는다.

- [ ] **Step 9: db check 최종 확인**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\m3d.exe db check
```

Expected: 기존 표(1/50/61/112+122 assets, RLS on ×4)에 더해
`catalog_status: match 49 / unreadable 1` · `from_content 채움: 49` · `페이지 크기 채움: 61`.
unreadable 1건의 `*_from_content` NULL 유지 확인:

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -c "from m3d.config import load_config; import psycopg; cfg=load_config(); conn=psycopg.connect(cfg.require_db_url()); cur=conn.cursor(); cur.execute(\"select drawing_no_from_content, title_from_content, scale_from_content from sheets where catalog_status='unreadable'\"); print('unreadable NULL 유지:', cur.fetchall()); conn.close()"
```

Expected: `[(None, None, None)]`

- [ ] **Step 10: 전체 스위트 최종 실행**

```powershell
$env:PYTHONUTF8='1'; .\worker\.venv\Scripts\python.exe -m pytest worker\tests -q
```

Expected: **140 passed** (M1 완료 기준 §9-5).

- [ ] **Step 11: 커밋**

```bash
git add worker/src/m3d/catalog/run.py worker/src/m3d/cli.py worker/src/m3d/db.py worker/tests/test_catalog_run.py
git commit -m "feat(worker): m3d catalog — 표제란 기계 대조 실증 49/0/1

- 50건 대조: match 49 / mismatch 0 / unreadable 1 (C0050302-001, 표제란 부재)
- 멱등: 값 동일 시 무갱신 (2회차 갱신 0건 확인)
- unreadable 의 *_from_content NULL 유지 — M2 비전 판독의 입력으로 남김
- db check 확장: catalog_status 분포·from_content 채움·페이지 크기 채움
- mismatch 발생 시 종료 코드 1 — 불일치만 사람이 본다 (지식베이스 §3)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 계획 자체 검토 결과

### 1. 스펙 커버리지

| 설계서 절 | 담당 태스크 |
|---|---|
| §3 CLI 2명령·멱등·--force·실패 수집 | 6 (convert) · 8 (catalog) |
| §4 모듈 구조 7파일 | 1~8 전부 — compare.py(2), frames(3), sheet_text(4), render(5), convert/run(6), titleblock·reconcile(7), catalog/run(8) |
| §5 sheet_text JSON 스키마 | 4 (필드 전부 테스트로 고정) |
| §6 대조 규칙 (도면번호 판정·전 도곽·원문 저장·노트) | 7 (판정) · 8 (DB 반영) |
| §7 migration 0002·assets 등재·sheet_pages 갱신 | 1 (SQL·적용) · 6 (등재·갱신) |
| §8-1 단위테스트 5종 | 2·3·4·5·7 (+ 합성 DXF·실 DXF skipif) |
| §8-2 회귀 대조·임계 실측 | 6 (Step 6·9) |
| §8-3 db check 확장 | 8 (Step 4·5) |
| §9 완료 기준 6항 | 6 (1·2·6멱등convert) · 8 (3·4·6멱등catalog) · 10 (5 pytest) |
| §10 범위 밖 | 어느 태스크에도 뷰 크롭·분류·LLM·PDF·Storage 없음 — 확인함 |
| §11 리스크 4건 | 렌더 시간→6 병렬·멱등 / 버전 편차→6 임계 실측 / 블록명 변형→3·7 휴리스틱 / ATTRIB 결측→7 빈 문자열·NULL |

**빠진 것 없음.**

### 2. 플레이스홀더 스캔

Task 6 Step 9의 `<실측 최대 + 8>`은 의도된 실측 기입 지점(측정 전에 확정할 수 없는 값)이며, 기입 절차·근거 형식까지 명시했다. 그 외 TBD·TODO 없음.

### 3. 타입 일관성 (교차 확인)

- `SheetFrame` 필드·메서드가 Task 3 정의 ↔ Task 4(`to_paper`·`contains`·`paper_w`) ↔ Task 5(`world_w/h`·`x0..y1`) ↔ Task 6 워커에서 일치.
- `WorldText`/`build_sheet_text` 시그니처 Task 4 정의 ↔ Task 6 워커 호출 일치 (`drawing_no` 인자).
- `TitleBlock`·`Verdict`·`reconcile` Task 7 정의 ↔ Task 8 소비 일치.
- `derived_paths` 명명(`_p{n}` 균일)과 `regression_pairs`의 샘플명(M0 규칙: 1p 접미 없음) — **서로 다른 규칙임을 테스트가 명시적으로 구분**(test_regression_pairs_maps_to_sample_names).
- 테스트 누적: 91 → 95 → 100 → 110 → 115 → 119 → 122 → 136 → 140 (각 태스크에 명시, 디스패치 시점 실측 우선 원칙은 Global Constraints에).

### 4. 검산

- 페이지 수: 도곽 60 + 폴백 1 = 61 = `page_count` 합 (설계서 §1-1 실측).
- assets 등재: 61 png + 61 text = **122** (Task 6 Step 6 기대값과 일치).
- Task 6 워커의 `도곽 수 ≠ page_count` 실패 분기: C0050302-001은 도곽 0 → 폴백 1페이지 == page_count 1 → 통과. 2p 시트는 도곽 2 == 2 → 통과. 설계와 정합.
