// 인증 게이트 — 세션이 없으면 로그인 화면만 보인다 (참조 앱 web-app-v2 패턴 이식).
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { Alert, Center, Code, Loader } from '@mantine/core';

import { missingEnv, supabase } from '../lib/supabase';
import { LoginScreen } from './LoginScreen';

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession 은 AuthGate 하위에서만 사용할 수 있습니다');
  return session;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (supabase === null) return;
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setReady(true);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  if (supabase === null) {
    return (
      <Alert m="xl" color="yellow" title="환경변수 미설정">
        .env 에 <Code>{missingEnv.join(', ')}</Code> 가 필요합니다.
      </Alert>
    );
  }
  if (!ready) {
    return (
      <Center h="100vh">
        <Loader size="sm" />
      </Center>
    );
  }
  if (!session) return <LoginScreen />;
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}
