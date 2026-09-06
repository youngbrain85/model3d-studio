// 빌드·섹션·승인 데이터 접근 + 순수 함수 (M4 설계서 §6). 로그인 세션의 RLS 아래에서만 동작한다.
import type { SupabaseClient } from '@supabase/supabase-js';

import type { BuildFiles, BuildStats, Database, SectionSelfcheck } from '../../../contracts/db.types';
import type { ProjectRef } from './questions';

export type Client = SupabaseClient<Database>;
export type Status = '대기' | '승인' | '반려';
export type Verdict = '승인' | '반려';
export const BUCKET = 'models';
/** 워커 sections.CODES 와 같은 순서 — 섹션 트리 정렬 */
export const CODES = ['BOX', 'DIA', 'FRM', 'RIB', 'HST', 'WG', 'CS', 'SLAB', 'SP04', 'BRG'];
export const BUILD_TARGET = 'BUILD';

export interface BuildRow {
  id: string; version: number; kind: 'pilot' | 'full'; segment: string; glb_path: string;
  files: BuildFiles; stats: BuildStats; status: Status; git_sha: string | null; created_at: string;
}
export interface SectionRow {
  id: string; section_key: string; code: string; label: string; glb_path: string; bytes: number;
  meshes: number; triangles: number; selfcheck: SectionSelfcheck; status: Status;
}
export interface ApprovalRow {
  id: string; build_id: string; section_id: string | null; user_id: string; verdict: Verdict; note: string; created_at: string;
}
export interface ApprovalInsert {
  project_id: string; build_id: string; section_id: string | null; verdict: Verdict; note: string;
}

export function modelObjectKey(slug: string, version: number, rel: string): string {
  // worker model/publish.object_key 와 같은 규칙
  return `${slug}/b${version}/${rel}`;
}

export function targetKey(sectionId: string | null): string {
  return sectionId ?? BUILD_TARGET;
}

/** 대상(섹션 또는 결합본)별 최신 승인 — created_at 최대. 입력 정렬에 의존하지 않는다. */
export function latestApprovals(rows: ApprovalRow[]): Map<string, ApprovalRow> {
  const latest = new Map<string, ApprovalRow>();
  for (const r of rows) {
    const k = targetKey(r.section_id);
    const cur = latest.get(k);
    if (!cur || r.created_at > cur.created_at) latest.set(k, r);
  }
  return latest;
}

export function approvalPayload(p: {
  projectId: string; buildId: string; sectionId: string | null; verdict: Verdict; note?: string;
}): ApprovalInsert {
  if (p.verdict !== '승인' && p.verdict !== '반려') throw new RangeError(`verdict 범위 밖: ${String(p.verdict)}`);
  const note = (p.note ?? '').trim();
  if (note.length > 500) throw new RangeError('메모는 500자 이내');
  return { project_id: p.projectId, build_id: p.buildId, section_id: p.sectionId, verdict: p.verdict, note };
}

const BUILD_COLS = 'id,version,kind,segment,glb_path,files,stats,status,git_sha,created_at';
const SECTION_COLS = 'id,section_key,code,label,glb_path,bytes,meshes,triangles,selfcheck,status';
const APPROVAL_COLS = 'id,build_id,section_id,user_id,verdict,note,created_at';

export async function fetchBuilds(client: Client, project: ProjectRef): Promise<BuildRow[]> {
  const { data, error } = await client.from('builds').select(BUILD_COLS).eq('project_id', project.id).order('version', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as BuildRow[];
}

export async function fetchSections(client: Client, buildId: string): Promise<SectionRow[]> {
  const { data, error } = await client.from('build_sections').select(SECTION_COLS).eq('build_id', buildId);
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as SectionRow[];
  return rows.sort((a, b) => CODES.indexOf(a.code) - CODES.indexOf(b.code));
}

export async function fetchApprovals(client: Client, buildId: string): Promise<ApprovalRow[]> {
  const { data, error } = await client.from('approvals').select(APPROVAL_COLS).eq('build_id', buildId).order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as ApprovalRow[];
}

/** 서명 URL 일괄 발급 — 실패한 키는 failed 로 돌려주고 나머지는 계속(설계서 §6 오류 처리). */
export async function signedUrls(client: Client, keys: string[]): Promise<{ urls: Map<string, string>; failed: string[] }> {
  if (keys.length === 0) return { urls: new Map(), failed: [] };
  const { data, error } = await client.storage.from(BUCKET).createSignedUrls(keys, 3600);
  if (error || !data) throw new Error(error?.message ?? '서명 URL 실패');
  const urls = new Map<string, string>();
  const failed: string[] = [];
  data.forEach((d, i) => {
    if (d.signedUrl && !d.error) urls.set(d.path ?? keys[i], d.signedUrl);
    else failed.push(d.path ?? keys[i]);
  });
  return { urls, failed };
}

export async function submitApproval(client: Client, payload: ApprovalInsert): Promise<ApprovalRow> {
  const { data, error } = await client
    .from('approvals')
    // 수기 작성 타입에는 Relationships 가 없어 supabase-js 가 Insert 를 never 로 접는다 — questions.ts 와 같은 캐스팅.
    .insert(payload as never)
    .select(APPROVAL_COLS)
    .single();
  if (error) throw new Error(error.message);
  return data as unknown as ApprovalRow;
}

export async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch ${r.status}`);
  return (await r.json()) as T;
}
