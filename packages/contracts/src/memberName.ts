/**
 * 부재 명명 규칙 — 규칙 §5: "부재 = 독립 노드. 명명 규칙을 정하고 전 부재에 일관 적용한다.
 * 노드명이 곧 객체 DB·망도 연결 키다."
 *
 * 패턴: <구조물>_<세그먼트>_<부재종류><번호>[<측면>]
 *   AB1_S5_DIA07   → structure=AB1, segment=S5, member_type=DIA, index=7,  side=null
 *   AB1_S5_WG097L  → structure=AB1, segment=S5, member_type=WG,  index=97, side=L
 *
 * Python 쪽 대응: apps/worker/src/model3d_worker/contracts/member_name.py
 */
import type { Member, MemberSide } from './types.js';

/** member.schema.json 의 code 패턴과 **문자열이 일치해야 한다**. 테스트가 이를 강제한다. */
export const MEMBER_CODE_PATTERN = '^[A-Z][A-Z0-9]{0,7}_S[0-9]{1,3}_[A-Z]{2,4}[0-9]{1,4}[LRCTB]?$';

const MEMBER_CODE_RE = new RegExp(
  '^(?<structure>[A-Z][A-Z0-9]{0,7})_(?<segment>S[0-9]{1,3})_' +
    '(?<memberType>[A-Z]{2,4})(?<index>[0-9]{1,4})(?<side>[LRCTB])?$',
);

const SIDES: readonly MemberSide[] = ['L', 'R', 'C', 'T', 'B'];

export interface ParsedMemberCode {
  structure: string;
  segment: string;
  member_type: string;
  index: number;
  side: MemberSide | null;
  /** 원본 코드의 번호 자리수 (0 패딩 폭). 재조립 시 같은 폭을 유지한다. */
  indexWidth: number;
}

export function isValidMemberCode(code: string): boolean {
  return MEMBER_CODE_RE.test(code);
}

/** 부재 코드를 성분으로 분해한다. 규칙에 맞지 않으면 null. */
export function parseMemberCode(code: string): ParsedMemberCode | null {
  const m = MEMBER_CODE_RE.exec(code);
  if (!m?.groups) return null;
  const g = m.groups;
  const rawIndex = g.index ?? '';
  const side = g.side as MemberSide | undefined;
  return {
    structure: g.structure ?? '',
    segment: g.segment ?? '',
    member_type: g.memberType ?? '',
    index: Number.parseInt(rawIndex, 10),
    side: side && SIDES.includes(side) ? side : null,
    indexWidth: rawIndex.length,
  };
}

export interface FormatMemberCodeInput {
  structure: string;
  segment: string;
  member_type: string;
  index: number;
  side?: MemberSide | null;
  /** 번호 0 패딩 폭 (기본 2) */
  indexWidth?: number;
}

/**
 * 성분에서 부재 코드를 조립한다.
 * 조립 결과가 명명 규칙에 맞지 않으면 던진다 — 잘못된 노드명이 조용히 퍼지면 안 된다.
 */
export function formatMemberCode(input: FormatMemberCodeInput): string {
  const width = input.indexWidth ?? 2;
  const code =
    `${input.structure}_${input.segment}_${input.member_type}` +
    `${String(input.index).padStart(width, '0')}${input.side ?? ''}`;
  if (!isValidMemberCode(code)) {
    throw new Error(`부재 명명 규칙 위반: ${code} (패턴 ${MEMBER_CODE_PATTERN})`);
  }
  return code;
}

/** 부재 레코드의 code 와 분해 성분이 서로 모순되지 않는지 검사한다. */
export function memberCodeMatchesFields(member: Member): boolean {
  const parsed = parseMemberCode(member.code);
  if (!parsed) return false;
  return (
    parsed.structure === member.structure &&
    parsed.segment === member.segment &&
    parsed.member_type === member.member_type &&
    parsed.index === member.index &&
    parsed.side === (member.side ?? null)
  );
}
