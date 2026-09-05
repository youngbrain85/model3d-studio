// 질문 카드 — 한 질문 = 한 요소 (지식베이스 §4): 크롭·선택지(권장안 첫 번째, 근거)·모델 영향·"모르겠다"·메모.
import { useEffect, useState } from 'react';
import {
  Alert, Badge, Box, Button, Collapse, Group, Image, Modal, Radio, Stack, Text, Textarea, Title,
} from '@mantine/core';

import { decisionPayload, type Choice, type DecisionRow, UNSURE_LABEL } from '../lib/decisions';
import { cropSignedUrl, submitDecision, type Question } from '../lib/questions';
import { supabase } from '../lib/supabase';

interface Props {
  question: Question;
  slug: string;
  projectId: string;
  choice: Choice | null;
  onChoice: (c: Choice | null) => void;
  onDecided: (row: DecisionRow) => void;
}

export function QuestionCard({ question: q, slug, projectId, choice, onChoice, onDecided }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [imgError, setImgError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    setUrl(null);
    setImgError(null);
    setNote('');
    setError(null);
    if (supabase === null) return;
    cropSignedUrl(supabase, slug, q.id)
      .then(setUrl)
      .catch((e: Error) => setImgError(`이미지 없음 — worker 에서 \`m3d publish\` 를 실행하세요 (${e.message})`));
  }, [q.id, slug]);

  async function decide() {
    if (supabase === null || choice === null) return;
    setBusy(true);
    setError(null);
    try {
      const row = await submitDecision(
        supabase,
        decisionPayload({ projectId, ambiguityId: q.id, options: q.options, choice, note }),
      );
      onDecided(row);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const radioValue = choice === null ? '' : choice === 'unsure' ? 'unsure' : String(choice);
  const statusColor = q.status === '대기' ? 'gray' : q.status === '결정' ? 'green' : 'yellow';

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <Title order={4}>{q.item}</Title>
        <Group gap="xs">
          <Badge variant="light">{q.ord} p{q.pageNo ?? '?'}</Badge>
          <Badge color={statusColor}>{q.status}</Badge>
        </Group>
      </Group>

      {imgError ? (
        <Alert color="yellow">{imgError}</Alert>
      ) : (
        <Box style={{ cursor: 'zoom-in' }} onClick={() => setZoom(true)}>
          <Image src={url ?? undefined} alt={q.item} radius="sm" fit="contain" mah={420} />
        </Box>
      )}
      <Modal opened={zoom} onClose={() => setZoom(false)} size="90%" title={q.item}>
        <Image src={url ?? undefined} alt={q.item} fit="contain" />
      </Modal>

      <Radio.Group value={radioValue} onChange={(v) => onChoice(v === 'unsure' ? 'unsure' : Number(v))}>
        <Stack gap="xs">
          {q.options.map((o, i) => (
            <Radio
              key={i}
              value={String(i)}
              label={
                <span>
                  <Text span fw={600}>{i + 1}. {o.label}</Text>
                  {i === 0 && <Badge ml="xs" size="xs" color="blue">권장</Badge>}
                  <Text span size="sm" c="dimmed"> — {o.basis}</Text>
                </span>
              }
            />
          ))}
          <Radio value="unsure" label={<Text span c="dimmed">0. {UNSURE_LABEL}</Text>} />
        </Stack>
      </Radio.Group>

      <Alert color="blue" title="모델 영향" variant="light">{q.modelImpact}</Alert>

      <Textarea label="메모" placeholder="근거·현장 확인 사항" value={note}
        onChange={(e) => setNote(e.currentTarget.value)} autosize minRows={2} />

      {error && <Alert color="red">{error}</Alert>}
      <Group>
        <Button id="decide-button" onClick={() => void decide()} disabled={choice === null} loading={busy}>
          결정 (Enter)
        </Button>
        {q.latest && (
          <Text size="sm" c="dimmed">
            현재: {q.latest.provisional ? '잠정' : '결정'} · {q.latest.choice_label} ·{' '}
            {new Date(q.latest.decided_at).toLocaleString('ko-KR')}
          </Text>
        )}
      </Group>
      {q.history.length > 0 && (
        <>
          <Button variant="subtle" size="xs" onClick={() => setShowHistory((v) => !v)}>
            이력 {q.history.length}건 {showHistory ? '접기' : '펼치기'}
          </Button>
          <Collapse in={showHistory}>
            <Stack gap={4}>
              {q.history.map((h) => (
                <Text key={h.id} size="xs" c="dimmed">
                  {new Date(h.decided_at).toLocaleString('ko-KR')} · {h.provisional ? '잠정' : '결정'} · {h.choice_label}
                  {h.note ? ` · ${h.note}` : ''}
                </Text>
              ))}
            </Stack>
          </Collapse>
        </>
      )}
    </Stack>
  );
}
