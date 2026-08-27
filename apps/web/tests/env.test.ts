import { describe, expect, it } from 'vitest';
import { EnvError, describeEnv, readWebEnv } from '../src/lib/env.js';

const OK = {
  VITE_SUPABASE_URL: 'https://example.supabase.co',
  VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_abc123',
};

function jwtWithRole(role: string): string {
  const b64 = (o: unknown): string => btoa(JSON.stringify(o)).replace(/=+$/, '');
  return `${b64({ alg: 'HS256' })}.${b64({ role })}.sig`;
}

describe('브라우저 환경변수 (CLAUDE.md §3 — service key 는 번들 금지)', () => {
  it('정상 설정을 읽는다', () => {
    expect(readWebEnv(OK).supabaseUrl).toBe(OK.VITE_SUPABASE_URL);
  });

  it('누락되면 어떤 키가 없는지 말하고 던진다', () => {
    expect(() => readWebEnv({})).toThrow(EnvError);
    expect(() => readWebEnv({})).toThrow(/VITE_SUPABASE_URL/);
    expect(describeEnv({}).missing).toEqual(['VITE_SUPABASE_URL', 'VITE_SUPABASE_PUBLISHABLE_KEY']);
  });

  it('sb_secret_ 접두사 키를 거부한다', () => {
    expect(() => readWebEnv({ ...OK, VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_secret_abc123' })).toThrow(
      /service key/,
    );
  });

  it('role=service_role 인 레거시 JWT 를 거부한다', () => {
    expect(() =>
      readWebEnv({ ...OK, VITE_SUPABASE_PUBLISHABLE_KEY: jwtWithRole('service_role') }),
    ).toThrow(/service key/);
  });

  it('role=anon 인 레거시 JWT 는 통과시킨다', () => {
    expect(() =>
      readWebEnv({ ...OK, VITE_SUPABASE_PUBLISHABLE_KEY: jwtWithRole('anon') }),
    ).not.toThrow();
  });

  it('에러 메시지에 키 값을 넣지 않는다', () => {
    const secret = 'sb_secret_supersecretvalue';
    try {
      readWebEnv({ ...OK, VITE_SUPABASE_PUBLISHABLE_KEY: secret });
      expect.unreachable('던져야 한다');
    } catch (err) {
      expect((err as Error).message).not.toContain('supersecretvalue');
    }
  });

  it('공백만 있는 값은 미설정으로 본다', () => {
    expect(describeEnv({ ...OK, VITE_SUPABASE_URL: '   ' }).configured).toBe(false);
  });
});
