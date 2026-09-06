import { describe, expect, it } from 'vitest';
import { approvalPayload, CODES, latestApprovals, modelObjectKey, targetKey, type ApprovalRow } from './models';

const row = (over: Partial<ApprovalRow>): ApprovalRow => ({
  id: 'a', build_id: 'b', section_id: null, user_id: 'u', verdict: '승인', note: '', created_at: '2026-09-05T10:00:00+00:00', ...over,
});

describe('modelObjectKey', () => {
  it('워커 publish.object_key 와 같은 문자열', () => {
    expect(modelObjectKey('ab1-p4p5', 3, 'sections/P4P5/DIA.glb')).toBe('ab1-p4p5/b3/sections/P4P5/DIA.glb');
  });
  it('CODES 는 워커 sections.CODES 와 같은 순서', () => {
    expect(CODES).toEqual(['BOX', 'DIA', 'FRM', 'RIB', 'HST', 'WG', 'CS', 'SLAB', 'SP04', 'BRG']);
  });
});

describe('latestApprovals', () => {
  it('대상(섹션 id 또는 BUILD)별 created_at 최신 행, 입력 순서 무관', () => {
    const m = latestApprovals([
      row({ id: 'old', section_id: 's1', created_at: '2026-09-05T10:00:00+00:00' }),
      row({ id: 'new', section_id: 's1', verdict: '반려', created_at: '2026-09-05T11:00:00+00:00' }),
      row({ id: 'whole', section_id: null }),
    ]);
    expect(m.get('s1')?.id).toBe('new');
    expect(m.get(targetKey(null))?.id).toBe('whole');
    expect(m.size).toBe(2);
  });
});

describe('approvalPayload', () => {
  it('정상 페이로드 — 메모 trim, section_id null 허용', () => {
    expect(approvalPayload({ projectId: 'p', buildId: 'b', sectionId: null, verdict: '승인', note: ' ok ' }))
      .toEqual({ project_id: 'p', build_id: 'b', section_id: null, verdict: '승인', note: 'ok' });
  });
  it('verdict 범위 밖·메모 500자 초과는 RangeError', () => {
    expect(() => approvalPayload({ projectId: 'p', buildId: 'b', sectionId: 's', verdict: '보류' as never })).toThrow(RangeError);
    expect(() => approvalPayload({ projectId: 'p', buildId: 'b', sectionId: 's', verdict: '반려', note: 'x'.repeat(501) })).toThrow(RangeError);
  });
});
