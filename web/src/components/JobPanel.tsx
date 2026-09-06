// 잡 패널 — 최근 잡 상태·시도·비용, 펼치면 이벤트 로그 (M5 설계서 §6)
import { Badge, Button, Group, ScrollArea, Stack, Text } from '@mantine/core';

import { isActive, jobSummary, type JobEventRow, type JobRow } from '../lib/jobs';

export function JobPanel({ jobs, events, open, onToggle }: {
  jobs: JobRow[]; events: Record<string, JobEventRow[]>; open: string | null; onToggle(jobId: string): void;
}) {
  if (jobs.length === 0) return null;
  const color = (s: JobRow['status']) => (s === 'done' ? 'green' : s === 'failed' ? 'red' : s === 'running' ? 'blue' : 'gray');
  return (
    <Stack gap={4}>
      <Text size="xs" fw={600}>LLM 모델링 잡</Text>
      {jobs.map((j) => (
        <Stack key={j.id} gap={2}>
          <Group gap={6} wrap="nowrap">
            <Badge size="xs" color={color(j.status)}>{j.section_key}</Badge>
            <Text size="xs" style={{ flex: 1 }} id={`job-${j.id}`}>{jobSummary(j)}{isActive(j) ? ' …' : ''}</Text>
            <Button size="compact-xs" variant="subtle" onClick={() => onToggle(j.id)}>{open === j.id ? '접기' : '로그'}</Button>
          </Group>
          {open === j.id && (
            <ScrollArea h={140} p={4} style={{ background: 'var(--mantine-color-gray-0)', borderRadius: 4 }}>
              {(events[j.id] ?? []).map((e) => (
                <Text key={e.id} size="xs" c={e.level === 'error' ? 'red' : e.level === 'warn' ? 'orange' : undefined}>
                  {e.ts.slice(11, 19)} {e.message}
                </Text>
              ))}
            </ScrollArea>
          )}
        </Stack>
      ))}
    </Stack>
  );
}
