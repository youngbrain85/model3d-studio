// Supabase 데이터 접근 — 로그인 세션의 RLS 아래에서만 동작한다 (M2b 설계서 §5).
import type { SupabaseClient } from '@supabase/supabase-js';

import type { Database } from '../../../contracts/db.types';
import { latestByAmbiguity, type DecisionInsert, type DecisionRow, type Option } from './decisions';

export type Client = SupabaseClient<Database>;
export type AmbiguityStatus = '대기' | '결정' | '잠정';

export interface ProjectRef {
  id: string;
  slug: string;
  name: string;
}

export interface Question {
  id: string;
  item: string;
  options: Option[];
  modelImpact: string;
  status: AmbiguityStatus;
  ord: string;
  pageNo: number | null;
  region: string;
  latest: DecisionRow | null;
  history: DecisionRow[];
}

interface AmbiguityJoined {
  id: string;
  item: string;
  options: Option[];
  model_impact: string;
  status: AmbiguityStatus;
  sheets: { ord: string } | null;
  sheet_pages: { page_no: number } | null;
}

export function cropObjectKey(slug: string, ambiguityId: string): string {
  // worker publish.object_key 와 같은 규칙
  return `${slug}/${ambiguityId}.png`;
}

export async function fetchProjects(client: Client): Promise<ProjectRef[]> {
  const { data, error } = await client.from('projects').select('id,slug,name').order('slug');
  if (error) throw new Error(error.message);
  return (data ?? []) as ProjectRef[];
}

export async function fetchProject(client: Client, slug: string): Promise<ProjectRef> {
  const { data, error } = await client.from('projects').select('id,slug,name').eq('slug', slug).maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) throw new Error(`프로젝트 없음: ${slug}`);
  return data as ProjectRef;
}

export async function fetchQuestions(client: Client, project: ProjectRef): Promise<Question[]> {
  const amb = await client
    .from('ambiguities')
    .select('id,item,options,model_impact,status,sheets(ord),sheet_pages(page_no)')
    .eq('project_id', project.id);
  if (amb.error) throw new Error(amb.error.message);
  const dec = await client
    .from('decisions')
    .select('id,ambiguity_id,choice_index,choice_label,provisional,note,decided_at')
    .eq('project_id', project.id)
    .order('decided_at', { ascending: false });
  if (dec.error) throw new Error(dec.error.message);

  const rows = (amb.data ?? []) as unknown as AmbiguityJoined[];
  const decisions = (dec.data ?? []) as unknown as DecisionRow[];
  const latest = latestByAmbiguity(decisions);
  const questions = rows.map<Question>((r) => ({
    id: r.id,
    item: r.item,
    options: r.options,
    modelImpact: r.model_impact,
    status: r.status,
    ord: r.sheets?.ord ?? '?',
    pageNo: r.sheet_pages?.page_no ?? null,
    region: (r.sheets?.ord ?? '?')[0],
    latest: latest.get(r.id) ?? null,
    history: decisions.filter((d) => d.ambiguity_id === r.id),
  }));
  return questions.sort(
    (a, b) => a.ord.localeCompare(b.ord) || (a.pageNo ?? 0) - (b.pageNo ?? 0) || a.item.localeCompare(b.item),
  );
}

export async function submitDecision(client: Client, payload: DecisionInsert): Promise<DecisionRow> {
  const { data, error } = await client
    .from('decisions')
    // 수기 작성 타입(contracts/db.types.ts)에는 Relationships 가 없어 supabase-js 가 Insert 를 never 로 접는다 —
    // 페이로드 형태는 decisionPayload 가 보장하므로 여기서만 캐스팅한다.
    .insert(payload as never)
    .select('id,ambiguity_id,choice_index,choice_label,provisional,note,decided_at')
    .single();
  if (error) throw new Error(error.message);
  return data as unknown as DecisionRow;
}

export async function cropSignedUrl(client: Client, slug: string, ambiguityId: string): Promise<string> {
  const { data, error } = await client.storage.from('crops').createSignedUrl(cropObjectKey(slug, ambiguityId), 3600);
  if (error || !data) throw new Error(error?.message ?? '서명 URL 실패');
  return data.signedUrl;
}
