/**
 * 계약 타입 — packages/contracts/schemas/*.json 의 TS 대응물.
 *
 * JSON Schema 가 정본이다. 이 타입들은 편의를 위한 미러이며,
 * 실제 정합성은 packages/contracts/fixtures/ 를 TS·Python 양쪽에서
 * 같은 스키마로 검증하는 테스트가 보장한다.
 */

export type Vec3 = [number, number, number];

/** 이미지 픽셀 좌표 박스. 좌상단 원점, x 우측·y 하측 증가. */
export interface BboxPx {
  x: number;
  y: number;
  width: number;
  height: number;
}

// ── coordinate_system.schema.json ─────────────────────────────────────────
export interface AxisDef {
  meaning: string;
  positive_direction: string;
  /** 도면으로 확정되지 않아 가정한 값인가 (규칙 §1) */
  assumed: boolean;
}

export interface CoordinateAssumption {
  item: string;
  assumed_value: string;
  reason: string;
  /** 가정이 틀렸을 때의 뒤집기 검증 절차 (규칙 §1) */
  flip_test: string;
  resolved: boolean;
  /** resolved 이면 필수 — decision id 또는 도면번호 */
  resolved_by?: string | null;
}

export interface OriginReference {
  description: string;
  station?: string | null;
  /** 원점 표고 (m). 도면 EL 관례상 여기만 예외적으로 m 원문값이다. */
  elevation_m?: number | null;
  offset_m?: number | null;
  /** 근거 도면번호 — 최소 1개 (규칙 §8) */
  source_sheets: string[];
}

export interface CoordinateSystem {
  project_id: string;
  /** 도면 EL 이 대응하는 축 */
  up_axis: 'X' | 'Y' | 'Z';
  /** glTF·three.js 규약이자 뷰 계약 법선 n = u_axis × v_axis 의 전제 */
  handedness: 'right';
  model_unit: 'm';
  drawing_unit: 'mm';
  /** 규칙 §1 — mm↔m 환산이 존재하는 유일한 지점 */
  mm_per_model_unit: 1000;
  axes: { x: AxisDef; y: AxisDef; z: AxisDef };
  origin_reference: OriginReference;
  /** 어느 축이든 assumed 면 최소 1개 있어야 한다 (규칙 §1) */
  assumptions?: CoordinateAssumption[];
}

// ── view_contract.schema.json ─────────────────────────────────────────────
export interface PixelFrame {
  /** 시트 페이지 이미지 전체 폭 (px) */
  width_px: number;
  /** 시트 페이지 이미지 전체 높이 (px) */
  height_px: number;
  /** 이미지 y축이 아래로 증가하는가 (일반적인 래스터 관례) */
  v_down: boolean;
  /** 뷰 직사각형 [0,u_extent]×[0,v_extent] 가 대응하는 이미지 영역 — 이미지 전체가 아니다 */
  view_bbox_px: BboxPx;
  /** 이미지 해상도 (있으면). 도면 척도와의 정합 검산용. */
  dpi?: number | null;
}

/** 왕복 검산 결과 R1·R2·R3 (규칙 §7) */
export interface RoundtripCheck {
  sample_count: number;
  tolerance_m: number;
  /** | |u_axis| − 1 | */
  u_norm_error: number;
  /** | |v_axis| − 1 | */
  v_norm_error: number;
  /** |u_axis · v_axis| */
  orthogonality_error: number;
  /** R1 (u,v) → 3D → (u,v) 최대 오차 */
  max_view_roundtrip_error_m: number;
  /** R2 3D → (u,v,h) → 3D 최대 오차 */
  max_world_roundtrip_error_m: number;
  /** R3 (u,v) → 픽셀 → (u,v) 최대 오차. pixel_frame 이 없으면 null. */
  max_pixel_roundtrip_error_m?: number | null;
  result: 'PASS' | 'FAIL';
}

export interface ViewContract {
  id: string;
  name: string;
  sheet_no?: string | null;
  origin: Vec3;
  u_axis: Vec3;
  v_axis: Vec3;
  u_extent: number;
  v_extent: number;
  unit: 'm';
  pixel_frame?: PixelFrame | null;
  roundtrip_check?: RoundtripCheck | null;
}

// ── ambiguity.schema.json ─────────────────────────────────────────────────
export interface SheetCrop {
  sheet_no: string;
  page?: number | null;
  /** 원본 페이지 이미지의 크롭 영역. 위치 배열이 아닌 이름 있는 객체 — [x,y,w,h]/[x0,y0,x1,y1] 혼동 방지. */
  bbox_px: BboxPx;
  crop_path?: string | null;
  caption?: string | null;
}

export interface AmbiguityOption {
  label: string;
  rationale: string;
  source_sheets?: string[];
  model_impact: string;
  recommended: boolean;
}

export type AmbiguityStatus = 'pending' | 'decided' | 'provisional';

export interface Ambiguity {
  id: string;
  project_id: string;
  item: string;
  question: string;
  sheet_refs: SheetCrop[];
  /** 2~4개. [0] 은 반드시 권장안 (규칙 §4) */
  options: AmbiguityOption[];
  model_impact: string;
  allow_unknown?: true;
  status: AmbiguityStatus;
  conflicts_with?: string[];
  /** 재확인은 1회로 제한 (규칙 §4) */
  reconfirm_count?: number;
  created_at?: string;
}

// ── decision.schema.json ──────────────────────────────────────────────────
export type DecisionChoice = number | 'unknown';

export interface Decision {
  id: string;
  ambiguity_id: string;
  choice: DecisionChoice;
  /** choice === 'unknown' 이면 반드시 true (규칙 §4) */
  provisional: boolean;
  responder: string;
  decided_at: string;
  note?: string | null;
}

// ── ssot_item.schema.json ─────────────────────────────────────────────────
export type SsotStatus = 'confirmed' | 'estimated' | 'open';
export type SsotUnit = 'mm' | 'm' | 'deg' | 'ea' | '-';

export interface CrossCheck {
  formula: string;
  expected: number;
  actual: number;
  tolerance: number;
  result: 'PASS' | 'FAIL';
}

export interface SsotItem {
  id: string;
  project_id: string;
  item: string;
  value: number | string;
  unit: SsotUnit;
  /** 근거 도면번호 — 최소 1개 (규칙 §8) */
  source_sheets: string[];
  cross_source_confirmed?: boolean;
  status: SsotStatus;
  provisional_from_decision?: string | null;
  derived: boolean;
  derivation?: { formula: string; inputs: string[] } | null;
  cross_check?: CrossCheck | null;
  revision?: {
    version: string;
    changed_at: string;
    previous_value?: number | string | null;
    reason: string;
  }[];
}

// ── member.schema.json ────────────────────────────────────────────────────
export type MemberSide = 'L' | 'R' | 'C' | 'T' | 'B';

export interface MemberZone {
  name: string;
  spacing_mm: number;
  count: number;
  start_station?: string | null;
  transition_note?: string | null;
}

export interface Member {
  code: string;
  project_id: string;
  parent_code?: string | null;
  structure: string;
  segment: string;
  member_type: string;
  index: number;
  side?: MemberSide | null;
  zone?: MemberZone | null;
  spec_refs?: string[];
}

// ── verification_report.schema.json ───────────────────────────────────────
export type VerificationStage = 'self_check' | 'independent_remeasure' | 'render_review';

export interface VerificationCheck {
  name: string;
  kind: 'grid' | 'count' | 'elevation' | 'watertight' | 'dimension';
  expected: number | boolean;
  measured: number | boolean;
  tolerance: number;
  unit: 'mm' | 'm' | 'ea' | '-';
  /** 독립 재실측에서는 'builder_code' 가 금지된다 (규칙 §6) */
  expected_derived_from: 'spec' | 'builder_code' | 'drawing';
  method: 'slice' | 'bbox' | 'node_count' | 'mesh_query' | 'visual';
  result: 'PASS' | 'FAIL';
}

export interface VerificationReport {
  id: string;
  build_id: string;
  stage: VerificationStage;
  performed_by: string;
  builder_agent?: string | null;
  performed_at: string;
  checks: VerificationCheck[];
  renders?: {
    kind: 'orthographic' | 'context' | 'interior_cut';
    path: string;
    note?: string | null;
  }[];
  overall: 'PASS' | 'FAIL';
  notes?: string | null;
}

// ── sheet.schema.json ─────────────────────────────────────────────────────
export interface Sheet {
  id: string;
  project_id: string;
  file_name: string;
  page: number;
  sheet_no_from_titleblock?: string | null;
  sheet_no_from_filename?: string | null;
  titleblock_match: 'match' | 'mismatch' | 'unreadable' | 'filename_only';
  title?: string | null;
  scale?: string | null;
  classification?: string | null;
  coverage?: {
    station_from?: string | null;
    station_to?: string | null;
    description?: string | null;
    /** 키플랜 라벨은 오탐 원인이라 허용하지 않는다 (규칙 §3) */
    source: 'keyplan_hatch' | 'body_annotation';
  } | null;
  image_path?: string | null;
  text_path?: string | null;
  source_format?: 'pdf' | 'dxf' | 'dwg' | 'image';
}

// ── sample_manifest.schema.json ───────────────────────────────────────────
export interface SampleSetDef {
  set_id: string;
  description: string;
  /** 원본 위치 힌트 — 사용자가 .env 를 채울 때 보라고 남기는 참고값 */
  source_hint?: string;
  /** 정답 데이터를 고르는 유일한 근거 — 파일명 추측이 아닌 명시적 글롭 선언 (규칙 §3) */
  answers?: string[];
  exclude?: string[];
  notes?: string | null;
}

export type SampleRole = 'drawing' | 'photo' | 'answer' | 'doc' | 'other';

export interface SampleManifestEntry {
  /** POSIX+NFC 상대 경로. **식별자이지 열 수 있는 경로가 아니다** (NFD 파일시스템 주의) */
  path: string;
  size: number;
  sha256: string;
  mtime?: string | null;
  role: SampleRole;
  /** 역할을 어떻게 정했는가. role='answer' 는 반드시 'declared' 여야 한다 (규칙 §3) */
  role_source: 'declared' | 'extension' | 'default';
  /** declared 일 때 걸린 글롭 패턴 — 근거를 남긴다 (규칙 §8) */
  matched_by?: string | null;
}

export interface SampleManifest {
  manifest_version: 2;
  set_id: string;
  description: string;
  source_hint?: string;
  generated_at: string;
  /** 매니페스트를 만든 호스트 OS — 파일명 정규화(NFC/NFD) 차이 추적용 */
  generated_on?: string | null;
  /**
   * 정답 항목들의 봉인. sha256( '\n'.join('<path>\0<sha256>'), 경로 오름차순 ).
   * 정답 파일을 고쳐 M3 대조를 통과시키는 일을 막는다 (규칙 §6·§8). 정답이 없으면 null.
   */
  answers_seal?: string | null;
  entries: SampleManifestEntry[];
}
