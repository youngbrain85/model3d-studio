/**
 * GLB 노드 트리 → 부재 인덱스.
 *
 * 규칙 §5 — "부재 = 독립 노드. 노드명이 곧 객체 DB·망도 연결 키다."
 * 뷰어는 노드명을 부재 코드로 해석해 선택·하이라이트·2D 연동에 쓴다.
 * 명명 규칙을 어긴 노드는 **조용히 넘기지 않고 별도로 보고**한다.
 */
import type { Object3D } from 'three';
import { parseMemberCode, type ParsedMemberCode } from '@model3d/contracts';

export interface MemberIndexEntry {
  code: string;
  parsed: ParsedMemberCode;
  object: Object3D;
}

export interface MemberIndex {
  /** 부재 코드 → 노드 */
  byCode: Map<string, MemberIndexEntry>;
  /** 세그먼트 코드 → 부재 코드 목록 */
  bySegment: Map<string, string[]>;
  /** 명명 규칙에 맞지 않는 노드명 (루트·중간 그룹 제외 대상 판단은 호출자 몫) */
  unnamed: string[];
  /** 중복된 부재 코드 — 노드명이 키이므로 중복은 곧 결함이다 */
  duplicates: string[];
}

/**
 * 씬 그래프를 훑어 부재 인덱스를 만든다.
 * @param root GLB 로 불러온 씬 루트
 * @param ignore 명명 규칙 검사에서 제외할 노드명 (씬 루트, 좌표 헬퍼 등)
 */
export function buildMemberIndex(root: Object3D, ignore: readonly string[] = []): MemberIndex {
  const ignoreSet = new Set(ignore);
  const byCode = new Map<string, MemberIndexEntry>();
  const bySegment = new Map<string, string[]>();
  const unnamed: string[] = [];
  const duplicates: string[] = [];

  root.traverse((obj) => {
    const name = obj.name;
    if (!name || ignoreSet.has(name)) return;
    const parsed = parseMemberCode(name);
    if (!parsed) {
      unnamed.push(name);
      return;
    }
    if (byCode.has(name)) {
      duplicates.push(name);
      return;
    }
    byCode.set(name, { code: name, parsed, object: obj });
    const segKey = `${parsed.structure}_${parsed.segment}`;
    const list = bySegment.get(segKey);
    if (list) list.push(name);
    else bySegment.set(segKey, [name]);
  });

  return { byCode, bySegment, unnamed, duplicates };
}
