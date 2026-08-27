import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { readWebEnv } from './env.js';

let client: SupabaseClient | null = null;

/**
 * Supabase 클라이언트(싱글턴). 환경변수가 없으면 던진다 —
 * 잘못 설정된 채로 화면이 반쯤 동작하는 상태를 만들지 않는다.
 */
export function getSupabase(): SupabaseClient {
  if (client) return client;
  const env = readWebEnv(import.meta.env as unknown as Record<string, string | undefined>);
  client = createClient(env.supabaseUrl, env.supabasePublishableKey);
  return client;
}

/** 테스트용 — 싱글턴 초기화 */
export function resetSupabaseForTest(): void {
  client = null;
}
