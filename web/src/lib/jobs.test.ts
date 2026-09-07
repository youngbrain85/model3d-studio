import { describe, expect, it } from 'vitest';
import { AGENT_SECTIONS, DEFAULT_BUDGET_USD, isActive, jobPayload, jobSummary, type JobRow } from './jobs';

const job = (over: Partial<JobRow>): JobRow => ({
  id: 'j', project_id: 'p', kind: 'model-section', section_key: 'P4P5/DIA', request: '', parent_job_id: null, status: 'queued',
  attempts: 0, cost_usd: 0, budget_usd: 5, result: null, build_id: null, user_id: 'u',
  created_at: '2026-09-06T10:00:00+00:00', updated_at: '2026-09-06T10:00:00+00:00', ...over,
});

describe('jobPayload', () => {
  it('정상 — request trim, parent 선택, 예산 기본 5', () => {
    expect(jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: ' 개구 1.4 ', parentJobId: null }))
      .toEqual({ project_id: 'p', kind: 'model-section', section_key: 'P4P5/DIA', request: '개구 1.4', parent_job_id: null, budget_usd: 5 });
    expect(jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: 'j0', budgetUsd: 9.39 }))
      .toMatchObject({ parent_job_id: 'j0', budget_usd: 9.39 });
  });
  it('예산 상한은 0.5~50 달러', () => {
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: null, budgetUsd: 0 })).toThrow(RangeError);
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: null, budgetUsd: 60 })).toThrow(RangeError);
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: '', parentJobId: null, budgetUsd: Number.NaN })).toThrow(RangeError);
  });
  it('섹션 키 형식·요청 길이 검증', () => {
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'dia', request: '', parentJobId: null })).toThrow(RangeError);
    expect(() => jobPayload({ projectId: 'p', sectionKey: 'P4P5/DIA', request: 'x'.repeat(2001), parentJobId: null })).toThrow(RangeError);
  });
  it('M5 는 격벽만', () => { expect(AGENT_SECTIONS).toEqual(['DIA']); });
  it('기본 예산 5', () => { expect(DEFAULT_BUDGET_USD).toBe(5); });
});

describe('jobSummary / isActive', () => {
  it('상태·시도·비용 문자열', () => {
    expect(jobSummary(job({ status: 'running', attempts: 2, cost_usd: 0.31 }))).toBe('실행 중 · 시도 2 · $0.31');
    expect(jobSummary(job({ status: 'done', attempts: 3, cost_usd: 0.4, result: { pass: true, attempts: 3, cost_usd: 0.4, build_version: 7 } })))
      .toBe('완료 · 시도 3 · $0.40 · PASS · b7');
    expect(jobSummary(job({ status: 'failed', result: { pass: false, reason: 'budget', attempts: 0, cost_usd: 0 } }))).toBe('실패 · 시도 0 · $0.00 · 예산 상한');
  });
  it('queued/running 만 활성', () => {
    expect(isActive(job({ status: 'queued' }))).toBe(true);
    expect(isActive(job({ status: 'done' }))).toBe(false);
  });
});
