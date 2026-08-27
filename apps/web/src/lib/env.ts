/**
 * 브라우저 환경변수 접근 지점.
 *
 * CLAUDE.md §3 / 아키텍처 §3: **앱은 publishable key 만 쓴다.**
 * service key 는 로컬 `.env` 전용이며 번들에 들어가면 안 된다 —
 * 여기서 형태를 검사해 빌드된 앱이 조용히 비밀키를 실어 나르는 일을 막는다.
 */

export interface WebEnv {
  supabaseUrl: string;
  supabasePublishableKey: string;
}

/** service key 로 보이는 값의 형태들. 하나라도 걸리면 거부한다. */
function looksLikeSecretKey(key: string): boolean {
  if (key.startsWith('sb_secret_')) return true;
  if (key.includes('service_role')) return true;
  // 레거시 JWT 형태: payload 에 role=service_role
  const parts = key.split('.');
  if (parts.length === 3) {
    try {
      const payload = JSON.parse(atob(parts[1]!.replace(/-/g, '+').replace(/_/g, '/'))) as {
        role?: string;
      };
      if (payload.role === 'service_role') return true;
    } catch {
      // JWT 가 아니면 이 검사는 해당 없음
    }
  }
  return false;
}

export class EnvError extends Error {}

/**
 * 필수 환경변수를 읽는다. 없으면 던진다 — 조용히 빈 문자열로 진행하지 않는다.
 * 값을 절대 에러 메시지에 넣지 않는다.
 */
export function readWebEnv(source: Record<string, string | undefined>): WebEnv {
  const supabaseUrl = source.VITE_SUPABASE_URL?.trim();
  const supabasePublishableKey = source.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();

  const missing: string[] = [];
  if (!supabaseUrl) missing.push('VITE_SUPABASE_URL');
  if (!supabasePublishableKey) missing.push('VITE_SUPABASE_PUBLISHABLE_KEY');
  if (missing.length > 0) {
    throw new EnvError(
      `환경변수 누락: ${missing.join(', ')} — .env.example 을 참고해 .env 를 채우세요.`,
    );
  }

  if (looksLikeSecretKey(supabasePublishableKey!)) {
    throw new EnvError(
      'VITE_SUPABASE_PUBLISHABLE_KEY 에 service key 로 보이는 값이 들어 있습니다. ' +
        'service key 는 로컬 워커 전용이며 브라우저 번들에 넣으면 안 됩니다 (CLAUDE.md §3).',
    );
  }

  return { supabaseUrl: supabaseUrl!, supabasePublishableKey: supabasePublishableKey! };
}

export interface EnvStatus {
  configured: boolean;
  missing: string[];
  message: string;
}

/** 화면에 띄울 헬스체크용 — 던지지 않고 상태만 돌려준다. 키 값은 노출하지 않는다. */
export function describeEnv(source: Record<string, string | undefined>): EnvStatus {
  try {
    readWebEnv(source);
    return { configured: true, missing: [], message: 'Supabase 설정 확인됨' };
  } catch (err) {
    const message = err instanceof EnvError ? err.message : '환경변수 확인 실패';
    const missing = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_PUBLISHABLE_KEY'].filter(
      (k) => !source[k]?.trim(),
    );
    return { configured: false, missing, message };
  }
}
