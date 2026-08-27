"""샘플 세트 레지스트리 — 리포에 커밋된 ``samples/<set_id>/`` 를 읽는다.

리포에 있는 것(커밋)과 로컬에만 있는 것(커밋 금지)을 나누는 곳이다.

| 위치 | 커밋 | 내용 |
|---|---|---|
| ``samples/<set_id>/set.json`` | O | 세트 정의 — 설명·정답 글롭·제외 글롭 |
| ``samples/<set_id>/manifest.json`` | O | 무엇이 있어야 하는가 — 경로·크기·SHA256·역할 |
| ``work/samples/<set_id>/source/`` | X | 판독 파이프라인 입력 (도면·사진·문서) |
| ``work/samples/<set_id>/answers/`` | X | **M3 대조 기준** — 판독 입력과 물리적으로 분리 |
| `.env` 의 ``M3D_SAMPLE_SOURCE_*`` | X | 원본 위치 (사용자마다 다름) |
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..contracts.models import RoleSource, SampleManifest, SampleRole, SampleSetDef
from ..contracts.schemas import repo_root
from .paths import DEFAULT_EXCLUDE, GlobSet

MANIFEST_NAME = "manifest.json"
SET_META_NAME = "set.json"

#: 판독 파이프라인이 보는 곳 / M3 대조만 보는 곳. **물리적으로 분리한다.**
INPUT_SUBDIR = "source"
ANSWER_SUBDIR = "answers"

_DRAWING_EXT = frozenset({".pdf", ".dwg", ".dxf", ".dgn"})
_PHOTO_EXT = frozenset({".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff"})
_DOC_EXT = frozenset({".md", ".txt", ".csv", ".xlsx", ".xls", ".docx", ".hwp", ".hwpx", ".json"})

#: "정답처럼 보이지만 선언되지 않은" 파일을 **경고**하기 위한 힌트. 분류에는 쓰지 않는다.
#: 규칙 §3 — 애매한 것을 추정으로 확정하지 않는다. 사람에게 물어본다.
_ANSWER_SUSPECT_HINTS: tuple[str, ...] = ("spec_v2", "재실측", "실측정리", "정답", "ground_truth")


class SampleSetError(RuntimeError):
    """세트 정의를 읽을 수 없을 때."""


@dataclass(frozen=True)
class RoleDecision:
    """역할과 **그 근거**. 근거 없는 분류는 남기지 않는다 (규칙 §8)."""

    role: SampleRole
    source: RoleSource
    matched_by: str | None = None


@dataclass(frozen=True)
class SampleSet:
    """샘플 세트 하나. 매니페스트는 커밋되고, 실제 파일은 work_dir 아래에만 있다."""

    definition: SampleSetDef
    dir: Path
    """``samples/<set_id>/`` — 커밋되는 메타데이터 위치"""

    # ── 편의 접근자 ──
    @property
    def set_id(self) -> str:
        return self.definition.set_id

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def source_hint(self) -> str:
        return self.definition.source_hint

    @property
    def manifest_path(self) -> Path:
        return self.dir / MANIFEST_NAME

    def has_manifest(self) -> bool:
        return self.manifest_path.is_file()

    def load_manifest(self) -> SampleManifest:
        if not self.has_manifest():
            raise SampleSetError(
                f"{self.set_id}: 매니페스트가 없습니다 ({self.manifest_path}).\n"
                "  원본이 있는 머신에서 `m3d samples ingest` 를 먼저 실행하고 "
                "생성된 manifest.json 을 커밋하세요."
            )
        manifest = SampleManifest.model_validate_json(
            self.manifest_path.read_text(encoding="utf-8")
        )
        if manifest.set_id != self.set_id:
            raise SampleSetError(
                f"매니페스트의 set_id 가 디렉터리와 다릅니다: "
                f"{manifest.set_id!r} != {self.set_id!r} ({self.manifest_path})"
            )
        return manifest

    # ── 작업 디렉터리 레이아웃 ──
    def work_root(self, work_dir: Path) -> Path:
        """ingest 된 실제 파일이 놓이는 위치 (`.gitignore` 대상)."""
        return work_dir / "samples" / self.set_id

    def input_root(self, work_dir: Path) -> Path:
        """판독 파이프라인 입력 루트. **정답은 여기 없다.**"""
        return self.work_root(work_dir) / INPUT_SUBDIR

    def answers_root(self, work_dir: Path) -> Path:
        """M3 대조 기준 루트. 판독 에이전트에게 이 경로를 주면 자기 채점이 된다."""
        return self.work_root(work_dir) / ANSWER_SUBDIR

    def subdir_for(self, role: SampleRole) -> str:
        return ANSWER_SUBDIR if role == "answer" else INPUT_SUBDIR

    def destination_for(self, work_dir: Path, rel: str, role: SampleRole) -> Path:
        """매니페스트 항목이 놓일 실제 경로."""
        return self.work_root(work_dir) / self.subdir_for(role) / PurePosixPath(rel)

    # ── 글롭 ──
    def answers_glob(self) -> GlobSet:
        return GlobSet(self.definition.answers)

    def exclude_glob(self) -> GlobSet:
        return GlobSet(tuple(DEFAULT_EXCLUDE) + tuple(self.definition.exclude))

    # ── 역할 분류 ──
    def classify(self, rel: str) -> RoleDecision:
        """상대 경로의 역할을 정한다.

        **정답은 선언으로만 정해진다.** 확장자 추론은 도면/사진/문서만 가른다 —
        정답 여부를 파일명으로 추측하지 않는다 (규칙 §3).
        """
        matched = self.answers_glob().match(rel)
        if matched is not None:
            return RoleDecision(role="answer", source="declared", matched_by=matched)

        suffix = PurePosixPath(rel).suffix.lower()
        if suffix in _DRAWING_EXT:
            return RoleDecision(role="drawing", source="extension")
        if suffix in _PHOTO_EXT:
            return RoleDecision(role="photo", source="extension")
        if suffix in _DOC_EXT:
            return RoleDecision(role="doc", source="extension")
        return RoleDecision(role="other", source="default")

    def suspect_answers(self, rels: list[str]) -> list[str]:
        """정답처럼 보이는데 선언되지 않은 파일들.

        자동으로 정답 처리하지 **않는다** — 사용자에게 보고하고 set.json 을 고치게 한다.
        추정으로 확정하면 M3 대조가 자기 채점이 되거나 진짜 도면이 입력에서 빠진다.
        """
        answers = self.answers_glob()
        out = []
        for rel in rels:
            if answers.match(rel) is not None:
                continue
            lowered = rel.lower()
            if any(h in lowered for h in _ANSWER_SUSPECT_HINTS):
                out.append(rel)
        return sorted(out)


def samples_dir() -> Path:
    return repo_root() / "samples"


def load_sample_set(set_id: str) -> SampleSet:
    d = samples_dir() / set_id
    meta_path = d / SET_META_NAME
    if not meta_path.is_file():
        known = ", ".join(s.set_id for s in list_sample_sets()) or "(없음)"
        raise KeyError(f"알 수 없는 샘플 세트: {set_id}. 등록된 세트: {known}")
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    raw.setdefault("set_id", set_id)
    definition = SampleSetDef.model_validate(raw)
    if definition.set_id != set_id:
        raise SampleSetError(
            f"set.json 의 set_id 가 디렉터리 이름과 다릅니다: "
            f"{definition.set_id!r} != {set_id!r} ({meta_path})"
        )
    return SampleSet(definition=definition, dir=d)


def list_sample_sets() -> list[SampleSet]:
    base = samples_dir()
    if not base.is_dir():
        return []
    return [
        load_sample_set(d.name) for d in sorted(base.iterdir()) if (d / SET_META_NAME).is_file()
    ]
