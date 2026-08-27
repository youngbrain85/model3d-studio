import { describe, expect, it } from 'vitest';
import { Group, Object3D } from 'three';
import { buildMemberIndex } from '../src/viewer/memberIndex.js';

function sceneWith(names: string[]): Object3D {
  const root = new Group();
  root.name = 'Scene';
  for (const n of names) {
    const o = new Object3D();
    o.name = n;
    root.add(o);
  }
  return root;
}

describe('부재 인덱스 (규칙 §5 — 노드명이 연결 키)', () => {
  it('부재 코드를 분해해 인덱싱한다', () => {
    const idx = buildMemberIndex(sceneWith(['AB1_S5_DIA07', 'AB1_S5_WG097L', 'AB1_S6_DIA01']), [
      'Scene',
    ]);
    expect([...idx.byCode.keys()].sort()).toEqual([
      'AB1_S5_DIA07',
      'AB1_S5_WG097L',
      'AB1_S6_DIA01',
    ]);
    expect(idx.byCode.get('AB1_S5_WG097L')!.parsed.side).toBe('L');
    expect(idx.bySegment.get('AB1_S5')).toHaveLength(2);
    expect(idx.bySegment.get('AB1_S6')).toHaveLength(1);
    expect(idx.unnamed).toEqual([]);
    expect(idx.duplicates).toEqual([]);
  });

  it('명명 규칙을 어긴 노드를 조용히 넘기지 않고 보고한다', () => {
    const idx = buildMemberIndex(sceneWith(['AB1_S5_DIA07', 'mesh_001', '다이아프램']), ['Scene']);
    expect(idx.unnamed.sort()).toEqual(['mesh_001', '다이아프램']);
    expect(idx.byCode.size).toBe(1);
  });

  it('중복 부재 코드를 결함으로 보고한다', () => {
    const idx = buildMemberIndex(sceneWith(['AB1_S5_DIA07', 'AB1_S5_DIA07']), ['Scene']);
    expect(idx.duplicates).toEqual(['AB1_S5_DIA07']);
    expect(idx.byCode.size).toBe(1);
  });

  it('ignore 목록의 노드는 검사하지 않는다', () => {
    const idx = buildMemberIndex(sceneWith(['AB1_S5_DIA07']), ['Scene']);
    expect(idx.unnamed).not.toContain('Scene');
  });
});
