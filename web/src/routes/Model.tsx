// 3D 검수 화면 — 좌: 빌드·섹션 트리 / 중: three.js 캔버스 / 우: 검증·승인 패널 (M4 설계서 §6)
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Alert, Anchor, Badge, Box, Button, Checkbox, Group, Loader, Paper, ScrollArea, Select, Stack, Text, Title } from '@mantine/core';

import { fetchProject, type ProjectRef } from '../lib/questions';
import { fetchBuilds, fetchSections, signedUrls, type BuildRow, type SectionRow } from '../lib/models';
import { supabase } from '../lib/supabase';
import { createViewer, type PickInfo, type Viewer } from '../lib/viewer/scene';

type LoadState = 'loading' | 'ok' | 'error';

export function Model() {
  const { slug = '' } = useParams();
  const [project, setProject] = useState<ProjectRef | null>(null);
  const [builds, setBuilds] = useState<BuildRow[] | null>(null);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [sections, setSections] = useState<SectionRow[]>([]);
  const [load, setLoad] = useState<Record<string, LoadState>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [solo, setSolo] = useState<string | null>(null);
  const [picked, setPicked] = useState<PickInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const loadedBuildRef = useRef<string | null>(null);      // 같은 빌드 이중 로드 방지(StrictMode 이중 fetch)

  const build = useMemo(() => builds?.find((b) => b.id === buildId) ?? null, [builds, buildId]);

  useEffect(() => {
    if (supabase === null) return;
    (async () => {
      try {
        const p = await fetchProject(supabase, slug);
        setProject(p);
        const bs = await fetchBuilds(supabase, p);
        setBuilds(bs);
        setBuildId(bs[0]?.id ?? null);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [slug]);

  // 빌드가 바뀌면 섹션 로드(프로그레시브) — 뷰어는 캔버스가 마운트된 뒤 처음 필요할 때 만든다
  const loadBuild = useCallback(async (b: BuildRow) => {
    if (supabase === null || !canvasRef.current) return;
    if (loadedBuildRef.current === b.id) return;
    loadedBuildRef.current = b.id;
    if (!viewerRef.current) {
      const v = createViewer(canvasRef.current);
      v.onPick((info) => { setPicked(info); v.highlight(info?.node ?? null); });
      viewerRef.current = v;
      if (import.meta.env.DEV) (window as unknown as { __m3dViewer?: Viewer }).__m3dViewer = v;   // 브라우저 E2E 진단용
    }
    const viewer = viewerRef.current;
    const secs = await fetchSections(supabase, b.id);
    setSections(secs);
    setLoad(Object.fromEntries(secs.map((s) => [s.section_key, 'loading' as LoadState])));
    setVisible(Object.fromEntries(secs.map((s) => [s.section_key, true])));
    const { urls, failed } = await signedUrls(supabase, secs.map((s) => s.glb_path));
    for (const s of secs) {
      const url = urls.get(s.glb_path);
      if (!url || failed.includes(s.glb_path)) { setLoad((m) => ({ ...m, [s.section_key]: 'error' })); continue; }
      viewer.loadSection(s.section_key, url)
        .then(() => setLoad((m) => ({ ...m, [s.section_key]: 'ok' })))
        .catch(() => setLoad((m) => ({ ...m, [s.section_key]: 'error' })));
    }
  }, []);
  useEffect(() => { if (build) void loadBuild(build); }, [build, loadBuild]);
  useEffect(() => () => { viewerRef.current?.dispose(); viewerRef.current = null; loadedBuildRef.current = null; }, []);

  if (error) return <Alert m="xl" color="red">{error}</Alert>;
  if (!project || !builds) return <Loader m="xl" />;

  const statusColor = (s: string) => (s === '승인' ? 'green' : s === '반려' ? 'red' : 'gray');

  return (
    <Group align="stretch" gap={0} h="100vh" wrap="nowrap">
      <Paper w={300} p="md" withBorder radius={0} style={{ overflow: 'hidden' }}>
        <Stack gap="sm" h="100%">
          <Anchor component={Link} to="/" size="sm">← 프로젝트</Anchor>
          <Title order={5}>{project.name} — 3D 검수</Title>
          {builds.length === 0 && <Text c="dimmed" size="sm">빌드가 없습니다 — worker 에서 `m3d publish-model` 을 실행하세요.</Text>}
          <Select size="xs" label="빌드" value={buildId} onChange={setBuildId}
            data={builds.map((b) => ({ value: b.id, label: `b${b.version} · ${b.kind} · ${b.stats.meshes} 메시 · ${b.status}` }))} />
          {build && (
            <Group gap={6}>
              <Text size="xs" c="dimmed">구간 {build.segment} · 결합본</Text>
              <Badge size="xs" color={statusColor(build.status)}>{build.status}</Badge>
            </Group>
          )}
          <ScrollArea style={{ flex: 1 }}>
            <Stack gap={4}>
              {sections.map((s) => (
                <Group key={s.id} gap="xs" wrap="nowrap" justify="space-between">
                  <Checkbox size="xs" checked={visible[s.section_key] ?? true} disabled={solo !== null}
                    onChange={(e) => {
                      const on = e.currentTarget.checked;
                      setVisible((m) => ({ ...m, [s.section_key]: on }));
                      viewerRef.current?.setVisible(s.section_key, on);
                    }}
                    label={<Text size="sm">{s.label} <Text span c="dimmed" size="xs">{s.code} · {s.meshes}</Text></Text>} />
                  <Group gap={4} wrap="nowrap">
                    {load[s.section_key] === 'loading' && <Loader size={12} />}
                    {load[s.section_key] === 'error' && <Badge size="xs" color="red">로드 실패</Badge>}
                    <Badge size="xs" color={statusColor(s.status)}>{s.status}</Badge>
                    <Button size="compact-xs" variant={solo === s.section_key ? 'filled' : 'subtle'}
                      onClick={() => { const next = solo === s.section_key ? null : s.section_key; setSolo(next); viewerRef.current?.solo(next); }}>
                      단독
                    </Button>
                  </Group>
                </Group>
              ))}
            </Stack>
          </ScrollArea>
        </Stack>
      </Paper>
      <Box style={{ flex: 1, position: 'relative', minWidth: 0 }}>
        <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />
        <Paper pos="absolute" top={8} left={8} p="xs" withBorder>
          <Text size="xs">{picked ? `${picked.node} · ${picked.section}` : '부재를 클릭하면 노드명이 표시됩니다'}</Text>
        </Paper>
      </Box>
      <Paper w={340} p="md" withBorder radius={0}>
        <Text size="sm" c="dimmed">검증·승인 패널 (Task 6)</Text>
      </Paper>
    </Group>
  );
}
