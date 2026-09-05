// 로그인 화면 — 이메일/비밀번호 (Supabase Auth). 성공 시 AuthGate 가 세션을 받아 자동 전환된다.
import { useState, type FormEvent } from 'react';
import { Button, Center, Paper, PasswordInput, Stack, Text, TextInput } from '@mantine/core';

import { supabase } from '../lib/supabase';

function toKoreanError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes('invalid login credentials')) return '이메일 또는 비밀번호가 올바르지 않습니다';
  if (m.includes('email not confirmed')) return '이메일 인증이 완료되지 않은 계정입니다';
  if (m.includes('rate limit')) return '로그인 시도가 너무 잦습니다. 잠시 후 다시 시도해 주세요';
  if (m.includes('failed to fetch') || m.includes('network')) return '네트워크 오류 — 연결 상태를 확인해 주세요';
  return `로그인에 실패했습니다 (${message})`;
}

export function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (supabase === null) return;
    if (!email.trim() || !password) {
      setError('이메일과 비밀번호를 입력해 주세요');
      return;
    }
    setBusy(true);
    setError(null);
    const { error: err } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (err) setError(toKoreanError(err.message));
  }

  return (
    <Center h="100vh">
      <Paper w={360} p="lg" withBorder>
        <Text fw={700}>model3d-studio</Text>
        <Text size="xs" c="dimmed" mb="md">도면 판독 질문 카드 — 승인된 계정만 접근할 수 있습니다</Text>
        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput label="이메일" type="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.currentTarget.value)} data-autofocus />
            <PasswordInput label="비밀번호" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.currentTarget.value)} />
            {error ? <Text size="xs" c="red" role="alert">{error}</Text> : null}
            <Button type="submit" fullWidth loading={busy}>로그인</Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
