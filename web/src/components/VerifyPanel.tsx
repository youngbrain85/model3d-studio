// 우측 패널 — 섹션 self-check 표, 결합본 집계, 렌더 썸네일(모달 확대), 다운로드, 승인/반려 기록·이력,
// 에이전트 빌드면 채점·가정·질문·수정 요청 (M4 §6, M5 §6)
import { useState } from 'react';
import { Anchor, Badge, Button, Group, Image, Modal, ScrollArea, SegmentedControl, Stack, Table, Text, Textarea, Title } from '@mantine/core';

import type { JobResult } from '../../../contracts/db.types';
import {
  approvalPayload, latestApprovals, submitApproval, targetKey,
  type ApprovalRow, type BuildRow, type SectionRow, type Verdict,
} from '../lib/models';
import type { ProjectRef } from '../lib/questions';
import { supabase } from '../lib/supabase';

export interface VerifyPanelProps {
  project: ProjectRef;
  build: BuildRow;
  sections: SectionRow[];
  selected: SectionRow | null;
  renderUrls: Map<string, string>;
  downloadUrls: Map<string, string>;
  approvals: ApprovalRow[];
  onApproved(row: ApprovalRow): void;
  agentResult?: JobResult | null;
  onRevise?(request: string): void;
}

function okBadge(ok: boolean | null) {
  return <Badge size="xs" color={ok === true ? 'green' : ok === false ? 'red' : 'gray'}>{ok === true ? 'PASS' : ok === false ? 'FAIL' : 'SKIP'}</Badge>;
}

export function VerifyPanel({ project, build, sections, selected, renderUrls, downloadUrls, approvals, onApproved, agentResult, onRevise }: VerifyPanelProps) {
  const [verdict, setVerdict] = useState<Verdict>('승인');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [zoom, setZoom] = useState<string | null>(null);
  const [revise, setRevise] = useState('');
  const latest = latestApprovals(approvals);
  const target = selected ? selected.id : null;
  const history = approvals.filter((a) => targetKey(a.section_id) === targetKey(target));
  const st = build.stats;
  const agent = st.agent ?? null;

  async function record() {
    if (supabase === null) return;
    setBusy(true);
    setErr(null);
    try {
      const row = await submitApproval(
        supabase,
        approvalPayload({ projectId: project.id, buildId: build.id, sectionId: target, verdict, note }),
      );
      onApproved(row);
      setNote('');
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack gap="sm" h="100%">
      <Title order={6}>{selected ? `${selected.label} (${selected.section_key})` : `결합본 b${build.version}`}{build.kind === 'agent' ? ' · LLM' : ''}</Title>
      <ScrollArea style={{ flex: 1 }}>
        <Stack gap="sm">
          {build.kind === 'agent' && (
            <Stack gap={4} p={6} style={{ background: 'var(--mantine-color-violet-light)', borderRadius: 4 }} id="agent-score">
              <Group gap={6}>
                <Text size="xs" fw={600}>LLM 채점</Text>
                {agent && <Badge size="xs" color={agent.pass ? 'green' : 'red'}>{agent.pass ? 'PASS' : 'FAIL'}</Badge>}
              </Group>
              {agent ? (
                <Stack gap={2}>
                  <Text size="xs">
                    정답 무관 판정 — 건전성 fail {agent.sanity_fail} · 섹션 fail {agent.section_fail}
                    {' '}· 결합 fail {agent.assembled_fail} · 재실측 fail {agent.measure_section_fail} · 시도 {agent.attempts}
                  </Text>
                  {agent.bbox_dev_max_m !== null && (
                    <Text size="xs" c="dimmed">
                      참고: 정답 대조 — 노드 누락 {agent.only_ref} · 초과 {agent.only_ours}
                      {' '}· bbox {(agent.bbox_dev_max_m * 1000).toFixed(0)}mm
                    </Text>
                  )}
                </Stack>
              ) : <Text size="xs" c="dimmed">채점 정보 없음</Text>}
              {agentResult?.assumptions?.length ? (
                <>
                  <Text size="xs" fw={600}>가정</Text>
                  {agentResult.assumptions.map((a, i) => <Text key={i} size="xs">- {a}</Text>)}
                </>
              ) : null}
              {agentResult?.questions?.length ? (
                <>
                  <Text size="xs" fw={600}>질문</Text>
                  {agentResult.questions.map((q, i) => <Text key={i} size="xs">- {q}</Text>)}
                </>
              ) : null}
            </Stack>
          )}
          <Text size="xs" fw={600}>
            self-check {selected
              ? `${selected.selfcheck.pass} PASS / ${selected.selfcheck.fail} FAIL`
              : `${st.selfcheck.pass} PASS / ${st.selfcheck.fail} FAIL / ${st.selfcheck.skipped} SKIP`}
          </Text>
          {selected && (
            <Table fz="xs" verticalSpacing={2}>
              <Table.Tbody>
                {selected.selfcheck.checks.map((c) => (
                  <Table.Tr key={c.label}>
                    <Table.Td>{okBadge(c.ok)}</Table.Td>
                    <Table.Td>{c.label}</Table.Td>
                    <Table.Td c="dimmed">{c.detail}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          <Text size="xs">결합본: 메시 {st.meshes} · 삼각형 {st.triangles}</Text>
          <Text size="xs">재실측: {st.measure ? `${st.measure.pass} PASS / ${st.measure.fail} FAIL / ${st.measure.info} INFO` : '없음(시범)'}</Text>
          <Text size="xs">참조 대조: {st.compare ? `${st.compare.match} match / ${st.compare.mismatch} mismatch / ${st.compare.na} na` : '없음'}</Text>
          <Text size="xs" fw={600}>렌더</Text>
          <Group gap={6}>
            {[...renderUrls].map(([key, url]) => (
              <Image key={key} src={url} w={150} radius="sm" style={{ cursor: 'zoom-in' }} onClick={() => setZoom(url)} alt={key} />
            ))}
          </Group>
          <Modal opened={zoom !== null} onClose={() => setZoom(null)} size="90%" title="렌더">
            {zoom && <Image src={zoom} alt="렌더" />}
          </Modal>
          <Text size="xs" fw={600}>다운로드</Text>
          {[...downloadUrls].map(([key, url]) => (
            <Anchor key={key} href={url} size="xs" target="_blank" rel="noreferrer">{key}</Anchor>
          ))}
          <Text size="xs" fw={600}>승인 이력 ({history.length})</Text>
          {history.map((a) => (
            <Group key={a.id} gap={6}>
              <Badge size="xs" color={a.verdict === '승인' ? 'green' : 'red'}>{a.verdict}</Badge>
              <Text size="xs">{a.created_at.slice(0, 16).replace('T', ' ')} {a.note}</Text>
            </Group>
          ))}
          <Text size="xs" c="dimmed">섹션 승인 {sections.filter((s) => latest.get(s.id)?.verdict === '승인').length}/{sections.length}</Text>
        </Stack>
      </ScrollArea>
      {build.kind === 'agent' && onRevise && (
        <Group gap={6} align="flex-end" wrap="nowrap">
          <Textarea size="xs" style={{ flex: 1 }} placeholder="수정 요청 (예: 개구를 1.4×1.4 로)" value={revise}
            onChange={(e) => setRevise(e.currentTarget.value)} autosize minRows={1} />
          <Button id="revise-button" size="xs" variant="light" color="violet" disabled={!revise.trim()}
            onClick={() => { onRevise(revise); setRevise(''); }}>수정 요청</Button>
        </Group>
      )}
      <SegmentedControl size="xs" value={verdict} onChange={(v) => setVerdict(v as Verdict)} data={['승인', '반려']} />
      <Textarea size="xs" placeholder="메모(선택, 500자)" value={note} onChange={(e) => setNote(e.currentTarget.value)} autosize minRows={2} />
      {err && <Text size="xs" c="red">{err}</Text>}
      <Button id="approve-button" size="xs" loading={busy} onClick={() => void record()}>
        {selected ? '이 섹션 ' : '결합본 '}{verdict} 기록
      </Button>
    </Stack>
  );
}
