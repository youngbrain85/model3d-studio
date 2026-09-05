import { describe, expect, it } from 'vitest';
import { choiceFromKey, decisionPayload, latestByAmbiguity, UNSURE_LABEL, type DecisionRow } from './decisions';

const OPTS = [{ label: '순두께', basis: '단면 C-C' }, { label: '포장 포함', basis: '표기 관례' }];
const row = (over: Partial<DecisionRow>): DecisionRow => ({
  id: 'd', ambiguity_id: 'a', choice_index: 0, choice_label: '순두께', provisional: false,
  note: '', decided_at: '2026-09-05T10:00:00+00:00', ...over,
});

describe('latestByAmbiguity', () => {
  it('입력 순서와 무관하게 decided_at 최신 행을 고른다', () => {
    const m = latestByAmbiguity([
      row({ id: 'old', decided_at: '2026-09-05T10:00:00+00:00' }),
      row({ id: 'new', decided_at: '2026-09-05T11:00:00+00:00' }),
      row({ id: 'other', ambiguity_id: 'b' }),
    ]);
    expect(m.get('a')?.id).toBe('new');
    expect(m.get('b')?.id).toBe('other');
  });
});

describe('decisionPayload', () => {
  it('선택지 인덱스 → label 스냅샷, provisional false', () => {
    const p = decisionPayload({ projectId: 'p', ambiguityId: 'a', options: OPTS, choice: 1, note: '메모' });
    expect(p).toEqual({ project_id: 'p', ambiguity_id: 'a', choice_index: 1, choice_label: '포장 포함', provisional: false, note: '메모' });
  });
  it('"모르겠다" 는 권장안(0번) + provisional true + 고정 label', () => {
    const p = decisionPayload({ projectId: 'p', ambiguityId: 'a', options: OPTS, choice: 'unsure' });
    expect(p.choice_index).toBe(0);
    expect(p.provisional).toBe(true);
    expect(p.choice_label).toBe(UNSURE_LABEL);
    expect(p.note).toBe('');
  });
  it('범위 밖 인덱스는 RangeError', () => {
    expect(() => decisionPayload({ projectId: 'p', ambiguityId: 'a', options: OPTS, choice: 2 })).toThrow(RangeError);
    expect(() => decisionPayload({ projectId: 'p', ambiguityId: 'a', options: [], choice: 0 })).toThrow(RangeError);
  });
});

describe('choiceFromKey', () => {
  it('1~4 → 인덱스, 0 → unsure, 범위 밖·기타 → null', () => {
    expect(choiceFromKey('1', 3)).toBe(0);
    expect(choiceFromKey('3', 3)).toBe(2);
    expect(choiceFromKey('4', 3)).toBeNull();
    expect(choiceFromKey('0', 3)).toBe('unsure');
    expect(choiceFromKey('a', 3)).toBeNull();
  });
});
