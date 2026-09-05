// 질문 큐 — 좌: 목록(계열·상태 필터) / 우: 카드. 키보드 1~4 선택, 0 모르겠다, Enter 결정, ←/→ 이동.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert, Anchor, Badge, Box, Group, Loader, NavLink, Paper, ScrollArea, SegmentedControl, Select, Stack, Text, Title,
} from '@mantine/core';

import { QuestionCard } from '../components/QuestionCard';
import { choiceFromKey, type Choice, type DecisionRow } from '../lib/decisions';
import { fetchProject, fetchQuestions, type ProjectRef, type Question } from '../lib/questions';
import { supabase } from '../lib/supabase';

type StatusFilter = '전체' | '대기' | '결정' | '잠정';

export function Questions() {
  const { slug = '' } = useParams();
  const [project, setProject] = useState<ProjectRef | null>(null);
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>('전체');
  const [region, setRegion] = useState<string | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);

  const load = useCallback(async () => {
    if (supabase === null) return;
    try {
      const p = await fetchProject(supabase, slug);
      setProject(p);
      setQuestions(await fetchQuestions(supabase, p));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  const regions = useMemo(() => Array.from(new Set((questions ?? []).map((q) => q.region))).sort(), [questions]);
  const visible = useMemo(
    () => (questions ?? []).filter((q) => (status === '전체' || q.status === status) && (region === null || q.region === region)),
    [questions, status, region],
  );
  const currentQ = visible.find((q) => q.id === current) ?? visible[0] ?? null;

  const move = useCallback(
    (delta: number) => {
      if (!currentQ) return;
      const i = visible.findIndex((q) => q.id === currentQ.id);
      const next = visible[Math.min(Math.max(i + delta, 0), visible.length - 1)];
      if (next) {
        setCurrent(next.id);
        setChoice(null);
      }
    },
    [currentQ, visible],
  );

  function onDecided(row: DecisionRow) {
    setQuestions((prev) =>
      (prev ?? []).map((q) =>
        q.id === row.ambiguity_id
          ? { ...q, status: row.provisional ? '잠정' : '결정', latest: row, history: [row, ...q.history] }
          : q,
      ),
    );
    setChoice(null);
    // 다음 대기 항목으로
    const i = visible.findIndex((q) => q.id === row.ambiguity_id);
    const next = visible.slice(i + 1).find((q) => q.status === '대기');
    if (next) setCurrent(next.id);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
      if (!currentQ) return;
      if (e.key === 'ArrowLeft') { move(-1); return; }
      if (e.key === 'ArrowRight') { move(1); return; }
      if (e.key === 'Enter' && choice !== null) { document.getElementById('decide-button')?.click(); return; }
      const c = choiceFromKey(e.key, currentQ.options.length);
      if (c !== null) setChoice(c);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [currentQ, move, choice]);

  if (error) return <Alert m="xl" color="red">{error}</Alert>;
  if (!project || !questions) return <Loader m="xl" />;

  const counts = {
    대기: questions.filter((q) => q.status === '대기').length,
    결정: questions.filter((q) => q.status === '결정').length,
    잠정: questions.filter((q) => q.status === '잠정').length,
  };

  return (
    <Group align="stretch" gap={0} h="100vh" wrap="nowrap">
      <Paper w={360} p="md" withBorder radius={0} style={{ overflow: 'hidden' }}>
        <Stack gap="sm" h="100%">
          <Anchor component={Link} to="/" size="sm">← 프로젝트</Anchor>
          <Title order={5}>{project.name}</Title>
          <Text size="xs" c="dimmed">
            대기 {counts.대기} · 결정 {counts.결정} · 잠정 {counts.잠정} / 전체 {questions.length}
          </Text>
          <SegmentedControl size="xs" value={status} onChange={(v) => setStatus(v as StatusFilter)}
            data={['전체', '대기', '결정', '잠정']} />
          <Select size="xs" placeholder="계열 전체" clearable value={region} onChange={setRegion}
            data={regions.map((r) => ({ value: r, label: `${r} 계열` }))} />
          <ScrollArea style={{ flex: 1 }}>
            {visible.map((q) => (
              <NavLink
                key={q.id}
                active={currentQ?.id === q.id}
                onClick={() => { setCurrent(q.id); setChoice(null); }}
                label={<Text size="sm" lineClamp={2}>{q.item}</Text>}
                description={`${q.ord} p${q.pageNo ?? '?'}`}
                rightSection={
                  <Badge size="xs" color={q.status === '대기' ? 'gray' : q.status === '결정' ? 'green' : 'yellow'}>
                    {q.status}
                  </Badge>
                }
              />
            ))}
          </ScrollArea>
        </Stack>
      </Paper>
      <Box style={{ flex: 1, overflow: 'auto' }} p="xl">
        {currentQ ? (
          <QuestionCard key={currentQ.id} question={currentQ} slug={project.slug} projectId={project.id}
            choice={choice} onChoice={setChoice} onDecided={onDecided} />
        ) : (
          <Text c="dimmed">필터에 해당하는 질문이 없습니다.</Text>
        )}
      </Box>
    </Group>
  );
}
