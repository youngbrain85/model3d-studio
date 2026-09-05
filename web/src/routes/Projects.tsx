import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Anchor, Button, Card, Group, Stack, Text, Title } from '@mantine/core';

import { supabase } from '../lib/supabase';
import { fetchProjects, type ProjectRef } from '../lib/questions';

export function Projects() {
  const [projects, setProjects] = useState<ProjectRef[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (supabase === null) return;
    fetchProjects(supabase).then(setProjects).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Stack m="xl" maw={720}>
      <Group justify="space-between">
        <Title order={3}>프로젝트</Title>
        <Button variant="subtle" onClick={() => void supabase?.auth.signOut()}>로그아웃</Button>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      {projects?.length === 0 && <Text c="dimmed">프로젝트가 없습니다 — worker 에서 `m3d seed` 를 실행하세요.</Text>}
      {projects?.map((p) => (
        <Card key={p.id} withBorder>
          <Text fw={600}>{p.name}</Text>
          <Anchor component={Link} to={`/p/${p.slug}/questions`}>질문 카드 열기 →</Anchor>
        </Card>
      ))}
    </Stack>
  );
}
