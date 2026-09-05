// 결정 페이로드·축약 — 순수 로직 (M2b 설계서 §5, 지식베이스 §4).
// 권장안은 항상 options[0] 이다(판독 프롬프트가 그렇게 낸다). "모르겠다" 는 권장안을 잠정 채택한다.

export interface Option {
  label: string;
  basis: string;
}

export type Choice = number | 'unsure';

export const UNSURE_LABEL = '모르겠다 — 권장대로 진행, 나중에 확인';

export interface DecisionRow {
  id: string;
  ambiguity_id: string;
  choice_index: number;
  choice_label: string;
  provisional: boolean;
  note: string;
  decided_at: string;
}

export interface DecisionInsert {
  project_id: string;
  ambiguity_id: string;
  choice_index: number;
  choice_label: string;
  provisional: boolean;
  note: string;
}

/** ambiguity 별 최신 결정 (decided_at 최대). 입력 정렬에 의존하지 않는다. */
export function latestByAmbiguity(rows: DecisionRow[]): Map<string, DecisionRow> {
  const latest = new Map<string, DecisionRow>();
  for (const r of rows) {
    const cur = latest.get(r.ambiguity_id);
    if (!cur || r.decided_at > cur.decided_at) latest.set(r.ambiguity_id, r);
  }
  return latest;
}

export function decisionPayload(p: {
  projectId: string;
  ambiguityId: string;
  options: Option[];
  choice: Choice;
  note?: string;
}): DecisionInsert {
  if (p.options.length === 0) throw new RangeError('선택지가 없습니다');
  const base = { project_id: p.projectId, ambiguity_id: p.ambiguityId, note: p.note ?? '' };
  if (p.choice === 'unsure') {
    return { ...base, choice_index: 0, choice_label: UNSURE_LABEL, provisional: true };
  }
  if (!Number.isInteger(p.choice) || p.choice < 0 || p.choice >= p.options.length) {
    throw new RangeError(`choice_index ${String(p.choice)} 범위 밖 (선택지 ${p.options.length}개)`);
  }
  return { ...base, choice_index: p.choice, choice_label: p.options[p.choice].label, provisional: false };
}

/** 키보드: '1'~'4' → 선택지 인덱스, '0' → 모르겠다, 그 외 null. */
export function choiceFromKey(key: string, optionCount: number): Choice | null {
  if (key === '0') return 'unsure';
  const n = Number(key);
  if (Number.isInteger(n) && n >= 1 && n <= Math.min(optionCount, 4)) return n - 1;
  return null;
}
