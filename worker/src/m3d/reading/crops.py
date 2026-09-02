"""ambiguity 크롭 생성 (설계서 §6) — 질문 카드의 이미지.

지식베이스 §4: 질문에는 반드시 해당 도면의 크롭 이미지를 동반한다. 좌표는 용지 mm
로 받아 M1 렌더 PNG 픽셀로 변환한다 — M1 이 sheet_pages 에 width_px/height_px 를
채워둔 이유가 여기서 회수된다.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
from PIL import Image

from m3d.config import Config
from m3d.samples.manifest import sha256_file

Image.MAX_IMAGE_PIXELS = None

CONTEXT_MM = 40.0     # 주변 맥락 — 값만 잘라내면 무엇의 치수인지 알 수 없다
MIN_CROP_PX = 400     # 너무 작은 크롭은 확대해서 읽히게 한다
MIN_SIDE_PX = 8       # 이보다 얇으면 확대해도 스트립이라 실패로 본다


def mm_bbox_to_px(bbox_mm, paper_mm, png_size, context_mm: float = CONTEXT_MM):
    """용지 mm bbox → 픽셀 box (좌상단 원점). y 축은 뒤집는다.

    rot=0 전제다(현 데이터셋 61/61 이 rotation_deg=0). 회전 도곽은 run_crops 가
    먼저 걸러 명시적으로 실패시킨다 — 회전 시 sheet_text 좌표와 렌더 PNG 축이 달라진다.
    """
    x0m, y0m, x1m, y1m = bbox_mm
    pw, ph = paper_mm
    # 여백을 붙이기 전에 원 bbox 가 용지 안인지 본다 (밖이면 조용히 clamp 하지 않는다)
    if not (0.0 <= min(x0m, x1m) and max(x0m, x1m) <= pw
            and 0.0 <= min(y0m, y1m) and max(y0m, y1m) <= ph):
        raise ValueError(f"bbox 용지 범위 밖: {bbox_mm} / paper {paper_mm}")

    x0m, x1m = min(x0m, x1m) - context_mm, max(x0m, x1m) + context_mm
    y0m, y1m = min(y0m, y1m) - context_mm, max(y0m, y1m) + context_mm

    iw, ih = png_size
    sx, sy = iw / pw, ih / ph

    left = int(round(x0m * sx))
    right = int(round(x1m * sx))
    top = int(round((ph - y1m) * sy))      # y 뒤집기
    bottom = int(round((ph - y0m) * sy))

    left, top = max(0, left), max(0, top)
    right, bottom = min(iw, right), min(ih, bottom)
    if right <= left:
        right = min(iw, left + 1)
    if bottom <= top:
        bottom = min(ih, top + 1)
    return left, top, right, bottom


def render_crop(png: Path, box_px, out: Path, min_px: int = MIN_CROP_PX) -> tuple[int, int]:
    with Image.open(png) as im:
        crop = im.crop(box_px).convert("RGB")
        w, h = crop.size
        if min(w, h) < MIN_SIDE_PX:
            raise ValueError(f"크롭 영역 퇴화: {box_px}")
        if min(w, h) < min_px:
            scale = min_px / min(w, h)
            w, h = int(round(w * scale)), int(round(h * scale))
            crop = crop.resize((w, h), Image.LANCZOS)
        out.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out)
        return w, h


def run_crops(cfg: Config, dataset: str, *, force: bool = False) -> dict:
    """ambiguity 전건에 크롭을 만들고 crop_rel_path·assets 를 채운다(+고아 정리).

    per-row try 는 "렌더 단계"(PNG 탐색·회전 확인·mm→px 변환·크롭 저장)만 감싼다 —
    이 구간의 실패는 데이터 문제(용지 밖 bbox·회전 도곽·렌더 PNG 없음)라 해당 행만
    failures 에 쌓고 다음 행으로 넘어간다. DB 반영(update ambiguities·insert assets)
    은 try 밖: psycopg3 는 SQL 오류 후 트랜잭션이 aborted 상태가 되어 이후 모든 행이
    원인과 무관하게 오염되므로, 실패 시 즉시 rollback 하고 RuntimeError 로 올려
    호출자가 멈추게 한다(부분 커밋 없음 — PNG 파일이 남아도 다음 실행에서
    crop_rel_path 가 NULL 이라 재생성·멱등이라 안전).
    """
    made = skipped = purged = 0
    failures: list[tuple[str, str]] = []
    crops_dir = cfg.derived_dir / dataset / "crops"
    prefix = f"data/derived/{dataset}/crops/"

    with psycopg.connect(cfg.require_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from projects where slug = %s", (dataset,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"프로젝트 '{dataset}' 없음 — seed 먼저")
            project_id = row[0]
            cur.execute(
                "select a.id, a.mm_bbox, a.crop_rel_path, s.ord, s.id, sp.page_no, sp.id, "
                "       sp.width_px, sp.height_px, x.sha256 "
                "from ambiguities a "
                "join sheets s on s.id = a.basis_sheet_id "
                "left join sheet_pages sp on sp.id = a.sheet_page_id "
                "left join assets x on x.project_id = a.project_id "
                "                  and x.rel_path = a.crop_rel_path "
                "where a.project_id = %s order by s.ord, sp.page_no",
                (project_id,))
            rows = cur.fetchall()

        # ── 고아 스윕: 현재 ambiguity 집합 밖의 크롭 파일·assets 행 제거 ──
        keep_rel = [f"{prefix}{r[0]}.png" for r in rows]
        keep_stems = {str(r[0]) for r in rows}
        if crops_dir.is_dir():
            for png in sorted(crops_dir.glob("*.png")):
                if png.stem not in keep_stems:
                    png.unlink()
                    purged += 1
        with conn.cursor() as cur:
            cur.execute(
                "delete from assets where project_id = %s and rel_path like %s "
                "and rel_path <> all(%s)", (project_id, prefix + "%", keep_rel))

        for (amb_id, bbox, existing, ord_, sheet_id, page_no, page_id,
             wpx, hpx, sha) in rows:
            if existing and not force:
                cur_path = cfg.repo_root / existing
                if cur_path.is_file() and sha and sha256_file(cur_path) == sha:
                    skipped += 1
                    continue
            if page_no is None or wpx is None or hpx is None:
                failures.append((str(amb_id), "sheet_page 미해석/크기 미기록"))
                continue

            try:
                pngs = sorted((cfg.derived_dir / dataset / "png")
                              .glob(f"{ord_}_*_p{page_no}.png"))
                if not pngs:
                    failures.append((str(amb_id), "렌더 PNG 없음 — convert 먼저"))
                    continue
                src = pngs[0]
                meta = json.loads((cfg.derived_dir / dataset / "text" /
                                   f"{src.stem}.json").read_text(encoding="utf-8"))
                rot = int(meta.get("rotation_deg") or 0)
                if rot != 0:
                    failures.append((str(amb_id), f"회전 도곽(rot={rot}) 미지원"))
                    continue

                rel = f"{prefix}{amb_id}.png"
                out = cfg.repo_root / rel
                render_crop(src, mm_bbox_to_px(bbox, meta["paper_mm"], (wpx, hpx)), out)
            except Exception as exc:
                failures.append((str(amb_id), f"{type(exc).__name__}: {exc}"))
                continue

            try:
                with conn.cursor() as cur:
                    cur.execute("update ambiguities set crop_rel_path = %s where id = %s",
                                (rel, amb_id))
                    cur.execute(
                        "insert into assets (project_id, sheet_id, sheet_page_id, "
                        "kind, role, rel_path, bytes, sha256) "
                        "values (%s,%s,%s,'png','derived',%s,%s,%s) "
                        "on conflict (project_id, rel_path) do update set "
                        "bytes=excluded.bytes, sha256=excluded.sha256, "
                        "sheet_id=excluded.sheet_id, sheet_page_id=excluded.sheet_page_id",
                        (project_id, sheet_id, page_id, rel,
                         out.stat().st_size, sha256_file(out)))
            except Exception as exc:
                conn.rollback()
                raise RuntimeError(f"크롭 DB 반영 실패 ({amb_id}): {exc}") from exc
            made += 1
        conn.commit()

    return {"made": made, "skipped": skipped, "purged": purged,
            "failures": failures, "total": len(rows)}
