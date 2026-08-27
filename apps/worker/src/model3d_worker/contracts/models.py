"""계약 모델 (pydantic v2) — ``packages/contracts/schemas/*.json`` 의 Python 대응물.

**JSON Schema 가 정본**이다. 여기 있는 검증기는 그 규칙을 파이썬 쪽에서도 강제해
"애매값을 추정으로 확정"하거나 "근거 없는 수치"가 파이프라인에 흘러드는 일을 막는다
(규칙 §2·§3·§4·§6).

두 표현이 어긋나지 않는다는 사실은 ``tests/test_contract_fixtures.py`` 가
같은 픽스처를 jsonschema 와 pydantic 양쪽으로 통과시켜 보장한다.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .member_name import MEMBER_CODE_PATTERN


def is_nfc(text: str) -> bool:
    """유니코드 NFC 로 정규화되어 있는가. 한글 파일명의 NFC/NFD 분기를 막는 관문."""
    return unicodedata.is_normalized("NFC", text)


Vec3 = tuple[float, float, float]
PassFail = Literal["PASS", "FAIL"]


class BaseContract(BaseModel):
    """모든 계약 모델의 베이스. 스키마에 없는 필드는 거부한다 —
    오타 난 키가 조용히 무시되면 근거 없는 값이 흘러든다."""

    model_config = ConfigDict(extra="forbid", frozen=False)


# ── 좌표계 (규칙 §1) ──────────────────────────────────────────────────────
class AxisDef(BaseContract):
    meaning: str = Field(min_length=1)
    positive_direction: str = Field(min_length=1)
    #: 도면으로 확정되지 않아 가정한 값인가
    assumed: bool


class CoordinateAssumption(BaseContract):
    item: str = Field(min_length=1)
    assumed_value: str = Field(min_length=1)
    #: 왜 확정하지 못했는가 — 도면 근거가 없다는 사실 자체를 남긴다
    reason: str = Field(min_length=1)
    #: 가정이 틀렸을 때 무엇이 달라지는지와 그 확인 절차 (규칙 §1)
    flip_test: str = Field(min_length=1)
    resolved: bool = False
    #: 확정 근거 — decision id 또는 도면번호
    resolved_by: str | None = None

    @model_validator(mode="after")
    def _resolved_needs_evidence(self) -> Self:
        if self.resolved and not self.resolved_by:
            raise ValueError("확정된 가정에는 근거(resolved_by)가 있어야 합니다 (규칙 §1).")
        return self


class Axes(BaseContract):
    x: AxisDef
    y: AxisDef
    z: AxisDef


class OriginReference(BaseContract):
    description: str = Field(min_length=1)
    station: str | None = None
    #: 도면은 EL 을 m 로 쓰므로 여기만 예외적으로 m 원문값이다.
    elevation_m: float | None = None
    offset_m: float | None = None
    #: 근거 도면번호 — 근거 없는 값은 반려 (규칙 §8)
    source_sheets: Annotated[list[str], Field(min_length=1)]


class CoordinateSystem(BaseContract):
    project_id: str = Field(min_length=1)
    #: 상방 축 — 도면 EL 이 대응하는 축. three.js/glTF 기본은 Y-up.
    up_axis: Literal["X", "Y", "Z"]
    #: right 고정 — glTF·three.js 규약이자 뷰 계약 법선(n = u×v)의 전제
    handedness: Literal["right"] = "right"
    model_unit: Literal["m"] = "m"
    drawing_unit: Literal["mm"] = "mm"
    #: 규칙 §1 — "변환은 한 곳에서만". 그 한 곳이 이 값이며 units 모듈이 구현이다.
    mm_per_model_unit: Literal[1000] = 1000
    axes: Axes
    origin_reference: OriginReference
    assumptions: list[CoordinateAssumption] = Field(default_factory=list)

    @model_validator(mode="after")
    def _assumed_axis_needs_flip_test(self) -> Self:
        """규칙 §1 — 방위가 미확정이면 가정임을 표기하고 뒤집기 검증 항목으로 등재한다."""
        pairs = (("x", self.axes.x), ("y", self.axes.y), ("z", self.axes.z))
        assumed = [name for name, axis in pairs if axis.assumed]
        if assumed and not self.assumptions:
            raise ValueError(
                f"가정된 축 {assumed} 이 있는데 assumptions 가 비어 있습니다 — "
                "뒤집기 검증 항목으로 등재해야 합니다 (규칙 §1)."
            )
        return self


# ── 뷰 계약 (규칙 §7) ─────────────────────────────────────────────────────
class BboxPx(BaseContract):
    """이미지 픽셀 좌표 박스. 좌상단 원점, x 우측·y 하측 증가.

    ``[x, y, w, h]`` 와 ``[x0, y0, x1, y1]`` 의 혼동이 Python(PIL)·TS(canvas) 경계에서
    실제로 사고를 내므로, 위치 배열이 아니라 **이름 있는 객체**로 둔다.
    """

    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class PixelFrame(BaseContract):
    """시트 이미지 픽셀 좌표와의 대응.

    뷰 직사각형은 이미지 **전체**가 아니라 ``view_bbox_px`` 영역에 대응한다 —
    스캔 시트는 여백·표제란을 포함하므로 전체 대응 가정은 틀린다.
    """

    #: 시트 페이지 이미지 전체 폭 (px)
    width_px: int = Field(gt=0)
    #: 시트 페이지 이미지 전체 높이 (px)
    height_px: int = Field(gt=0)
    #: 이미지 y축이 아래로 증가하는가 (일반적인 래스터 관례)
    v_down: bool
    #: 뷰 직사각형이 대응하는 이미지 영역
    view_bbox_px: BboxPx
    #: 이미지 해상도(있으면). 도면 척도와의 정합 검산용.
    dpi: float | None = None

    @model_validator(mode="after")
    def _bbox_inside_image(self) -> Self:
        b = self.view_bbox_px
        if b.x + b.width > self.width_px or b.y + b.height > self.height_px:
            raise ValueError(
                f"view_bbox_px 가 이미지 밖으로 나갑니다 "
                f"({b.x}+{b.width} > {self.width_px} 또는 {b.y}+{b.height} > {self.height_px})."
            )
        return self


class RoundtripCheck(BaseContract):
    """왕복 검산 결과 R1·R2·R3. 규칙 §7 — 검산 없는 뷰 계약은 싣지 않는다."""

    #: 표본 수. 격자 grid×grid, 최소 2×2 = 4.
    sample_count: int = Field(ge=4)
    tolerance_m: float = Field(gt=0)
    #: | |u_axis| − 1 |
    u_norm_error: float = Field(ge=0)
    #: | |v_axis| − 1 |
    v_norm_error: float = Field(ge=0)
    #: |u_axis · v_axis| — 0 이어야 한다
    orthogonality_error: float = Field(ge=0)
    #: R1 시트 왕복 최대 오차 (m)
    max_view_roundtrip_error_m: float = Field(ge=0)
    #: R2 모델 왕복 최대 오차 (m)
    max_world_roundtrip_error_m: float = Field(ge=0)
    #: R3 픽셀 왕복 최대 오차 (m). pixel_frame 이 없으면 None.
    max_pixel_roundtrip_error_m: float | None = Field(default=None, ge=0)
    result: PassFail


class ViewContract(BaseContract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    sheet_no: str | None = None
    origin: Vec3
    u_axis: Vec3
    v_axis: Vec3
    u_extent: float = Field(gt=0)
    v_extent: float = Field(gt=0)
    unit: Literal["m"] = "m"
    pixel_frame: PixelFrame | None = None
    roundtrip_check: RoundtripCheck | None = None


# ── 애매값·결정 (규칙 §3·§4) ──────────────────────────────────────────────
class SheetCrop(BaseContract):
    sheet_no: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    #: 원본 페이지 이미지의 크롭 영역 (규칙 §4 — 원본 픽셀 좌표에서 잘라 확대)
    bbox_px: BboxPx
    crop_path: str | None = None
    caption: str | None = None


class AmbiguityOption(BaseContract):
    label: str = Field(min_length=1)
    #: 이 해석의 근거 — 도면번호·좌표 없는 선택지는 반려 (규칙 §8)
    rationale: str = Field(min_length=1)
    source_sheets: list[str] = Field(default_factory=list)
    #: 이 선택지를 고르면 모델이 어떻게 달라지는가 (규칙 §4)
    model_impact: str = Field(min_length=1)
    recommended: bool


class Ambiguity(BaseContract):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    #: 한 질문 = 한 요소 (규칙 §4)
    item: str = Field(min_length=1)
    question: str = Field(min_length=1)
    #: 질문에는 반드시 도면 크롭을 동반한다 (규칙 §4)
    sheet_refs: Annotated[list[SheetCrop], Field(min_length=1)]
    options: Annotated[list[AmbiguityOption], Field(min_length=2, max_length=4)]
    model_impact: str = Field(min_length=1)
    #: "모르겠다 — 권장대로 진행" 은 항상 허용한다 (규칙 §4)
    allow_unknown: Literal[True] = True
    status: Literal["pending", "decided", "provisional"]
    conflicts_with: list[str] = Field(default_factory=list)
    #: 재확인은 1회로 제한 (규칙 §4)
    reconfirm_count: int = Field(default=0, ge=0, le=1)
    created_at: str | None = None

    @model_validator(mode="after")
    def _exactly_one_recommendation_first(self) -> Self:
        """규칙 §4 — 권장안을 첫 번째에 두며, 권장안은 하나뿐이다."""
        if not self.options[0].recommended:
            raise ValueError("권장안이 첫 번째 선택지가 아닙니다 (규칙 §4).")
        extra = [i for i, o in enumerate(self.options[1:], start=1) if o.recommended]
        if extra:
            raise ValueError(
                f"권장안이 둘 이상입니다 (options{extra} 도 recommended=true) — "
                "권장안은 options[0] 하나여야 합니다 (규칙 §4)."
            )
        return self


class Decision(BaseContract):
    id: str = Field(min_length=1)
    ambiguity_id: str = Field(min_length=1)
    #: 선택지 인덱스(0-based) 또는 "unknown"
    choice: int | Literal["unknown"]
    provisional: bool
    responder: str = Field(min_length=1)
    decided_at: str
    note: str | None = None

    @model_validator(mode="after")
    def _unknown_is_provisional(self) -> Self:
        """규칙 §4 — '모르겠다' 결정은 SSOT 에 잠정으로 기록된다."""
        if self.choice == "unknown" and not self.provisional:
            raise ValueError(
                "'모르겠다' 선택은 반드시 잠정(provisional)으로 기록해야 합니다 (규칙 §4)."
            )
        if isinstance(self.choice, int) and not 0 <= self.choice <= 3:
            raise ValueError("선택지 인덱스는 0~3 입니다 (선택지는 최대 4개).")
        return self


# ── SSOT 실측정리 (규칙 §2) ───────────────────────────────────────────────
class CrossCheck(BaseContract):
    formula: str = Field(min_length=1)
    expected: float
    actual: float
    tolerance: float = Field(ge=0)
    result: PassFail


class Derivation(BaseContract):
    formula: str = Field(min_length=1)
    inputs: Annotated[list[str], Field(min_length=1)]


class SsotRevision(BaseContract):
    version: str
    changed_at: str
    previous_value: float | str | None = None
    reason: str = Field(min_length=1)


class SsotItem(BaseContract):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    item: str = Field(min_length=1)
    value: float | str
    unit: Literal["mm", "m", "deg", "ea", "-"]
    #: 근거 도면번호 — 근거 없는 수치는 반려 (규칙 §8)
    source_sheets: Annotated[list[str], Field(min_length=1)]
    cross_source_confirmed: bool = False
    #: 확정 / 추정 / 미결 을 분리한다 (규칙 §2)
    status: Literal["confirmed", "estimated", "open"]
    provisional_from_decision: str | None = None
    derived: bool
    derivation: Derivation | None = None
    cross_check: CrossCheck | None = None
    revision: list[SsotRevision] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_ssot_rules(self) -> Self:
        if self.derived and (self.derivation is None or self.cross_check is None):
            raise ValueError(
                "파생 계산은 유도식(derivation)과 검산(cross_check)을 반드시 동반합니다 (규칙 §2)."
            )
        failed_check = self.cross_check is not None and self.cross_check.result == "FAIL"
        if failed_check and self.status == "confirmed":
            raise ValueError("검산 FAIL 인 수치는 확정될 수 없습니다 (규칙 §2).")
        if self.cross_source_confirmed and len(self.source_sheets) < 2:
            raise ValueError("교차 확인 표기는 근거 시트가 2개 이상일 때만 성립합니다 (규칙 §3).")
        return self


# ── 부재 (규칙 §5) ────────────────────────────────────────────────────────
class MemberZone(BaseContract):
    name: str = Field(min_length=1)
    spacing_mm: float = Field(gt=0)
    count: int = Field(ge=1)
    start_station: str | None = None
    #: 전이 구간은 유력안 채택 + 주석 (규칙 §5)
    transition_note: str | None = None


class Member(BaseContract):
    code: str = Field(pattern=MEMBER_CODE_PATTERN)
    project_id: str = Field(min_length=1)
    parent_code: str | None = None
    structure: str = Field(pattern=r"^[A-Z][A-Z0-9]{0,7}$")
    segment: str = Field(pattern=r"^S[0-9]{1,3}$")
    member_type: str = Field(pattern=r"^[A-Z]{2,4}$")
    index: int = Field(ge=0)
    side: Literal["L", "R", "C", "T", "B"] | None = None
    zone: MemberZone | None = None
    spec_refs: list[str] = Field(default_factory=list)


# ── 검증 (규칙 §6) ────────────────────────────────────────────────────────
class VerificationCheck(BaseContract):
    name: str = Field(min_length=1)
    kind: Literal["grid", "count", "elevation", "watertight", "dimension"]
    expected: float | bool
    measured: float | bool
    #: 허용오차 명시 필수 (규칙 §6)
    tolerance: float = Field(ge=0)
    unit: Literal["mm", "m", "ea", "-"]
    #: 독립 재실측의 기대값은 사양서에서 자체 유도해야 한다 (규칙 §6)
    expected_derived_from: Literal["spec", "builder_code", "drawing"]
    #: bbox 중심이 아닌 실면 슬라이스로 측정한다 (규칙 §6)
    method: Literal["slice", "bbox", "node_count", "mesh_query", "visual"]
    result: PassFail


class RenderRef(BaseContract):
    kind: Literal["orthographic", "context", "interior_cut"]
    path: str = Field(min_length=1)
    note: str | None = None


class VerificationReport(BaseContract):
    id: str = Field(min_length=1)
    build_id: str = Field(min_length=1)
    stage: Literal["self_check", "independent_remeasure", "render_review"]
    performed_by: str = Field(min_length=1)
    builder_agent: str | None = None
    performed_at: str
    checks: Annotated[list[VerificationCheck], Field(min_length=1)]
    renders: list[RenderRef] = Field(default_factory=list)
    overall: PassFail
    notes: str | None = None

    @model_validator(mode="after")
    def _independent_means_independent(self) -> Self:
        """규칙 §6·§8 — 빌더 코드에서 기대값을 가져오면 그것은 검증이 아니다."""
        if self.stage != "independent_remeasure":
            return self
        offenders = [c.name for c in self.checks if c.expected_derived_from == "builder_code"]
        if offenders:
            raise ValueError(
                f"독립 재실측의 기대값을 빌더 코드에서 가져왔습니다: {offenders} — "
                "기대값은 사양서에서 자체 유도해야 합니다 (규칙 §6)."
            )
        if self.builder_agent is not None and self.builder_agent == self.performed_by:
            raise ValueError(
                "독립 재실측을 빌더 자신이 수행했습니다 — 자기 검증은 검증이 아닙니다 (규칙 §8)."
            )
        return self


# ── 시트 (규칙 §3) ────────────────────────────────────────────────────────
class SheetCoverage(BaseContract):
    station_from: str | None = None
    station_to: str | None = None
    description: str | None = None
    #: 키플랜 라벨은 오탐 원인이라 허용하지 않는다 (규칙 §3)
    source: Literal["keyplan_hatch", "body_annotation"]


class Sheet(BaseContract):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    page: int = Field(ge=1)
    sheet_no_from_titleblock: str | None = None
    sheet_no_from_filename: str | None = None
    titleblock_match: Literal["match", "mismatch", "unreadable", "filename_only"]
    title: str | None = None
    scale: str | None = None
    classification: str | None = None
    coverage: SheetCoverage | None = None
    image_path: str | None = None
    text_path: str | None = None
    source_format: Literal["pdf", "dxf", "dwg", "image"] | None = None


# ── 샘플 세트 정의 / 매니페스트 ───────────────────────────────────────────
SampleRole = Literal["drawing", "photo", "answer", "doc", "other"]
#: 역할을 어떻게 정했는가 — 정답(answer)은 반드시 "declared" 여야 한다 (규칙 §3)
RoleSource = Literal["declared", "extension", "default"]

SET_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"


class SampleSetDef(BaseContract):
    """``samples/<set_id>/set.json`` — 머신에 독립적인 세트 정의. **커밋한다.**

    실제 경로는 여기 없다. 사용자마다 다르므로 `.env` 의
    ``M3D_SAMPLE_SOURCE_<SET_ID>`` 로만 주입한다 (CLAUDE.md §3).
    """

    set_id: str = Field(pattern=SET_ID_PATTERN)
    description: str = Field(min_length=1)
    #: 원본 위치 힌트 — 사용자가 `.env` 를 채울 때 보라고 남기는 참고값. 코드가 쓰지 않는다.
    source_hint: str = ""
    #: **정답 데이터를 고르는 유일한 근거.** 파일명 추측이 아니라 명시적 선언이다 (규칙 §3).
    answers: list[str] = Field(default_factory=list)
    #: 가져오지 않을 파일 (OS 부스러기 외 세트별 추가분)
    exclude: list[str] = Field(default_factory=list)
    notes: str | None = None


class SampleManifestEntry(BaseContract):
    #: 세트 루트 기준 POSIX+NFC 상대 경로. **식별자이지 열 수 있는 경로가 아니다** —
    #: NFD 파일시스템에서는 이 문자열로 원본이 열리지 않는다 (samples/paths.py 참고).
    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mtime: str | None = None
    role: SampleRole
    #: 역할을 **어떻게** 정했는가. 정답(answer)은 반드시 ``declared`` 여야 한다.
    role_source: RoleSource = "extension"
    #: ``declared`` 일 때 어떤 패턴에 걸렸는지 — 근거를 남긴다 (규칙 §8)
    matched_by: str | None = None


class SampleManifest(BaseContract):
    """``samples/<set_id>/manifest.json`` — 무엇이 있어야 하는가. **커밋한다.**

    원본 파일은 커밋하지 않으므로(용량·읽기 전용), 이 매니페스트가 원본 없는 환경에서
    세트 구성을 알고 무결성을 대조하는 유일한 근거다.
    """

    manifest_version: Literal[2] = 2
    set_id: str = Field(pattern=SET_ID_PATTERN)
    description: str = Field(min_length=1)
    source_hint: str = ""
    generated_at: str
    #: 매니페스트를 만든 호스트 OS — 파일명 정규화(NFC/NFD) 차이 추적용
    generated_on: str | None = None
    #: 정답 파일들의 봉인. 정답을 고쳐 M3 대조를 통과시키는 일을 막는다.
    answers_seal: str | None = None
    #: 빈 세트라도 키는 있어야 한다 (없으면 매니페스트가 아니다)
    entries: list[SampleManifestEntry]

    @model_validator(mode="after")
    def _paths_are_normalized_and_unique(self) -> Self:
        seen: set[str] = set()
        for e in self.entries:
            if "\\" in e.path:
                raise ValueError(
                    f"매니페스트 경로에 백슬래시가 있습니다: {e.path!r} (POSIX 표기여야 합니다)."
                )
            if e.path.startswith("/") or ".." in e.path.split("/"):
                raise ValueError(
                    f"매니페스트 경로는 세트 루트 기준 상대 경로여야 합니다: {e.path!r}"
                )
            if not is_nfc(e.path):
                raise ValueError(
                    f"매니페스트 경로가 NFC 로 정규화되어 있지 않습니다: {e.path!r} — "
                    "macOS(NFD)와 Windows/Linux(NFC)가 같은 파일을 다르게 부르게 됩니다."
                )
            if e.path in seen:
                raise ValueError(f"매니페스트에 중복 경로가 있습니다: {e.path!r}")
            seen.add(e.path)
        return self

    @model_validator(mode="after")
    def _answers_must_be_declared(self) -> Self:
        """규칙 §3 — 정답 데이터를 **추측으로 확정하지 않는다.**

        정답지는 M3 대조 기준이다. 파일명 추측으로 정답을 정하면, 오분류 한 번에
        정답이 판독 입력으로 새거나(자기 채점) 진짜 도면이 입력에서 빠진다.
        """
        guessed = [
            e.path for e in self.entries if e.role == "answer" and e.role_source != "declared"
        ]
        if guessed:
            raise ValueError(
                f"정답(answer)으로 분류됐지만 선언 근거가 없습니다: {guessed} — "
                "정답은 set.json 의 answers 글롭으로 **명시 선언**해야 합니다 (규칙 §3)."
            )
        undeclared = [
            e.path for e in self.entries if e.role_source == "declared" and not e.matched_by
        ]
        if undeclared:
            raise ValueError(
                f"선언 분류인데 근거 패턴(matched_by)이 없습니다: {undeclared} (규칙 §8)."
            )
        return self

    def answer_entries(self) -> list[SampleManifestEntry]:
        return [e for e in self.entries if e.role == "answer"]

    def input_entries(self) -> list[SampleManifestEntry]:
        """판독 파이프라인이 볼 수 있는 것 — 정답은 절대 포함되지 않는다."""
        return [e for e in self.entries if e.role != "answer"]

    def compute_answers_seal(self) -> str | None:
        """정답 파일 집합의 봉인값. 정답이 없으면 None."""
        answers = sorted(self.answer_entries(), key=lambda e: e.path)
        if not answers:
            return None
        payload = "\n".join(f"{e.path}\0{e.sha256}" for e in answers)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _seal_matches_entries(self) -> Self:
        expected = self.compute_answers_seal()
        if self.answers_seal is not None and self.answers_seal != expected:
            raise ValueError(
                "answers_seal 이 정답 항목과 맞지 않습니다 — 정답 파일이 바뀌었거나 "
                "봉인이 손으로 편집되었습니다 (M3 대조 기준의 무결성 §6)."
            )
        return self
