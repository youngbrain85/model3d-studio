// 모델링 에이전트 잡 — 생성·조회·요약 (M5 설계서 §6). 로그인 세션의 RLS 아래에서만.
import type { Database, JobResult } from '../../../contracts/db.types';
import type { Client } from './models';

export const AGENT_SECTIONS = ['DIA'];                       // M5: 격벽만
export type JobStatus = 'queued' | 'running' | 'done' | 'failed';
export type JobRow = Database['public']['Tables']['jobs']['Row'];
export type JobEventRow = Database['public']['Tables']['job_events']['Row'];
export type JobInsert = Database['public']['Tables']['jobs']['Insert'];

const SECTION_RE = /^[A-Z0-9]+\/[A-Z0-9]+$/;
const REASON_LABEL: Record<string, string> = {
  budget: '예산 상한', no_run: '실행 실패', unsupported_section: '지원 안 함', no_reference: '정답 빌드 없음', error: '오류',
};
const STATUS_LABEL: Record<JobStatus, string> = { queued: '대기', running: '실행 중', done: '완료', failed: '실패' };

export function jobPayload(p: { projectId: string; sectionKey: string; request: string; parentJobId: string | null }): JobInsert {
  if (!SECTION_RE.test(p.sectionKey)) throw new RangeError(`섹션 키 형식 오류: ${p.sectionKey}`);
  const request = p.request.trim();
  if (request.length > 2000) throw new RangeError('요청은 2,000자 이내');
  return { project_id: p.projectId, kind: 'model-section', section_key: p.sectionKey, request, parent_job_id: p.parentJobId };
}

export function isActive(job: JobRow): boolean {
  return job.status === 'queued' || job.status === 'running';
}

export function jobSummary(job: JobRow): string {
  const parts = [STATUS_LABEL[job.status], `시도 ${job.attempts}`, `$${Number(job.cost_usd).toFixed(2)}`];
  const r: JobResult | null = job.result;
  if (job.status === 'done' && r) parts.push(r.pass ? 'PASS' : 'FAIL', r.build_version ? `b${r.build_version}` : '');
  if (job.status === 'failed' && r?.reason) parts.push(REASON_LABEL[r.reason] ?? r.reason);
  return parts.filter(Boolean).join(' · ');
}

export async function createJob(client: Client, payload: JobInsert): Promise<JobRow> {
  const { data, error } = await client.from('jobs').insert(payload as never).select('*').single();
  if (error) throw new Error(error.message);
  return data as unknown as JobRow;
}

export async function fetchJobs(client: Client, projectId: string, limit = 5): Promise<JobRow[]> {
  const { data, error } = await client.from('jobs').select('*').eq('project_id', projectId).order('created_at', { ascending: false }).limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as JobRow[];
}

export async function fetchEvents(client: Client, jobId: string): Promise<JobEventRow[]> {
  const { data, error } = await client.from('job_events').select('*').eq('job_id', jobId).order('id', { ascending: true });
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as JobEventRow[];
}
