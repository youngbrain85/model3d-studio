// M0 헬스 화면 (설계서 §7·§9-8).
// 익명 키로 projects 를 조회해 "에러 없음 + 0행" 을 확인한다.
// 둘 중 하나만으로는 연결 실패와 구분되지 않는다.
import { useEffect, useState } from 'react';
import { Alert, Badge, Card, Code, Group, Stack, Text, Title } from '@mantine/core';

import { missingEnv, supabase } from '../lib/supabase';

type HealthState =
  | { kind: 'env-missing'; missing: string[] }
  | { kind: 'checking' }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; rowCount: number };

export function Health() {
  const [state, setState] = useState<HealthState>(
    missingEnv.length > 0 ? { kind: 'env-missing', missing: missingEnv } : { kind: 'checking' },
  );

  useEffect(() => {
    if (supabase === null) return;

    let cancelled = false;
    void supabase
      .from('projects')
      .select('id')
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          setState({ kind: 'error', message: error.message });
          return;
        }
        setState({ kind: 'ok', rowCount: data?.length ?? 0 });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card withBorder padding="lg" maw={640} m="xl">
      <Stack gap="md">
        <Title order={3}>model3d-studio — 연결 상태</Title>

        {state.kind === 'env-missing' && (
          <Alert color="yellow" title="환경변수 미설정">
            <Text size="sm">
              .env 에 다음 값이 필요합니다: <Code>{state.missing.join(', ')}</Code>
            </Text>
            <Text size="sm" mt="xs">
              설계서 §12 선행 작업(Supabase 프로젝트 생성·키 발급)을 마친 뒤 채워주세요.
            </Text>
          </Alert>
        )}

        {state.kind === 'checking' && <Text size="sm">확인 중…</Text>}

        {state.kind === 'error' && (
          <Alert color="red" title="연결 실패">
            <Code>{state.message}</Code>
          </Alert>
        )}

        {state.kind === 'ok' && (
          <Stack gap="xs">
            <Group gap="xs">
              <Badge color="green">도달 OK</Badge>
              <Badge color={state.rowCount === 0 ? 'green' : 'red'}>
                익명 조회 {state.rowCount}행
              </Badge>
            </Group>
            {state.rowCount === 0 ? (
              <Text size="sm">
                에러 없이 0행 — RLS 가 익명 접근을 정상 차단하고 있습니다.
                worker 가 service key 로 보는 행 수와 대조하면 RLS 작동이 증명됩니다.
              </Text>
            ) : (
              <Text size="sm" c="red">
                익명 키로 {state.rowCount}행이 보입니다 — RLS 정책을 확인하세요.
              </Text>
            )}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
