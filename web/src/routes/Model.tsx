// 3D 검수 화면 — 좌: 빌드·섹션 트리 / 중: three.js 캔버스 + 툴바(프리셋·단면 클리핑·선택) / 우: 검증·승인 패널 (M4 설계서 §6)
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert, Anchor, Badge, Box, Button, Checkbox, Group, Loader, Paper, ScrollArea, SegmentedControl, Select, Slider, Stack, Switch, Text, Title,
} from '@mantine/core';

import { VerifyPanel } from '../components/VerifyPanel';
import {
  fetchApprovals, fetchBuilds, fetchJson, fetchSections, signedUrls,
  type ApprovalRow, type BuildRow, type SectionRow,
} from '../lib/models';
import { fetchProject, type ProjectRef } from '../lib/questions';
import { supabase } from '../lib/supabase';
import { zFromDistance, type Keep, type Preset } from '../lib/viewer/math';
import { createViewer, type PickInfo, type Viewer } from '../lib/viewer/scene';

type LoadState = 'loading' | 'ok' | 'error';
const PRESETS: { value: Preset; label: string }[] = [
  { value: 'iso', label: '아이소' }, { value: 'side', label: '측면' }, { value: 'front', label: '정면' }, { value: 'bottom', label: '저면' },
];
const KEEPS = [{ value: 'below', label: '이전 유지' }, { value: 'above', label: '이후 유지' }];
const shortName = (key: string) => key.split('/').slice(-2).join('/');

export function Model() {
  const { slug = '' } = useParams();
  const [project, setProject] = useState<ProjectRef | null>(null);
  const [builds, setBuilds] = useState<BuildRow[] | null>(null);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [sections, setSections] = useState<SectionRow[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRow[]>([]);
  const [renderUrls, setRenderUrls] = useState<Map<string, string>>(new Map());
  const [downloadUrls, setDownloadUrls] = useState<Map<string, string>>(new Map());
  const [load, setLoad] = useState<Record<string, LoadState>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [solo, setSolo] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [picked, setPicked] = useState<PickInfo | null>(null);
  const [preset, setPreset] = useState<Preset>('iso');
  const [zP4, setZP4] = useState(-525);
  const [clipZ, setClipZ] = useState<{ enabled: boolean; d: number; keep: Keep }>({ enabled: false, d: 35, keep: 'below' });
  const [clipX, setClipX] = useState<{ enabled: boolean; x: number; keep: Keep }>({ enabled: false, x: 0, keep: 'below' });
  const [error, setError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const loadedBuildRef = useRef<string | null>(null);      // 같은 빌드 이중 로드 방지(StrictMode 이중 fetch)

  const build = useMemo(() => builds?.find((b) => b.id === buildId) ?? null, [builds, buildId]);
  const selected = useMemo(() => sections.find((s) => s.section_key === selectedKey) ?? null, [sections, selectedKey]);

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

  // 빌드가 바뀌면 섹션·승인·서명 URL 로드(프로그레시브) — 뷰어는 캔버스가 마운트된 뒤 처음 필요할 때 만든다
  const loadBuild = useCallback(async (b: BuildRow) => {
    if (supabase === null || !canvasRef.current) return;
    if (loadedBuildRef.current === b.id) return;
    loadedBuildRef.current = b.id;
    if (!viewerRef.current) {
      const v = createViewer(canvasRef.current);
      v.onPick((info) => {
        setPicked(info);
        v.highlight(info?.node ?? null);
        if (info) setSelectedKey(info.section);
      });
      viewerRef.current = v;
      if (import.meta.env.DEV) (window as unknown as { __m3dViewer?: Viewer }).__m3dViewer = v;   // 브라우저 E2E 진단용
    }
    const viewer = viewerRef.current;
    const secs = await fetchSections(supabase, b.id);
    setSections(secs);
    setSelectedKey(null);
    setLoad(Object.fromEntries(secs.map((s) => [s.section_key, 'loading' as LoadState])));
    setVisible(Object.fromEntries(secs.map((s) => [s.section_key, true])));
    fetchApprovals(supabase, b.id).then(setApprovals).catch((e: Error) => setError(e.message));

    const fileKeys = [b.glb_path, ...b.files.json, ...secs.map((s) => s.glb_path)];
    const { urls, failed } = await signedUrls(supabase, [...secs.map((s) => s.glb_path), ...b.files.renders, ...fileKeys]);
    setRenderUrls(new Map(b.files.renders.flatMap((k) => (urls.has(k) ? [[k.split('/').pop() ?? k, urls.get(k)!] as [string, string]] : []))));
    setDownloadUrls(new Map(fileKeys.flatMap((k) => (urls.has(k) ? [[shortName(k), urls.get(k)!] as [string, string]] : []))));
    const specKey = b.files.json.find((k) => k.endsWith('modelspec.json'));
    if (specKey && urls.has(specKey)) {
      fetchJson<{ spec: { coord: { z_p4: number } } }>(urls.get(specKey)!).then((j) => setZP4(j.spec.coord.z_p4)).catch(() => undefined);
    }
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

  // 클리핑·프리셋 → 뷰어
  useEffect(() => { viewerRef.current?.setClip('z', { enabled: clipZ.enabled, value: zFromDistance(zP4, clipZ.d), keep: clipZ.keep }); }, [clipZ, zP4]);
  useEffect(() => { viewerRef.current?.setClip('x', { enabled: clipX.enabled, value: clipX.x, keep: clipX.keep }); }, [clipX]);

  function onApproved(row: ApprovalRow) {
    setApprovals((prev) => [row, ...prev]);
    if (row.section_id) setSections((prev) => prev.map((s) => (s.id === row.section_id ? { ...s, status: row.verdict } : s)));
    else setBuilds((prev) => (prev ?? []).map((b) => (b.id === row.build_id ? { ...b, status: row.verdict } : b)));
  }

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
              <Button size="compact-xs" variant={selectedKey === null ? 'filled' : 'subtle'} onClick={() => setSelectedKey(null)}>결합본 선택</Button>
            </Group>
          )}
          <ScrollArea style={{ flex: 1 }}>
            <Stack gap={4}>
              {sections.map((s) => (
                <Group key={s.id} gap="xs" wrap="nowrap" justify="space-between"
                  style={{ background: selectedKey === s.section_key ? 'var(--mantine-color-blue-light)' : undefined, borderRadius: 4, padding: '2px 4px' }}>
                  <Checkbox size="xs" checked={visible[s.section_key] ?? true} disabled={solo !== null}
                    onChange={(e) => {
                      const on = e.currentTarget.checked;
                      setVisible((m) => ({ ...m, [s.section_key]: on }));
                      viewerRef.current?.setVisible(s.section_key, on);
                    }}
                    label={
                      <Text size="sm" style={{ cursor: 'pointer' }} onClick={(e) => { e.preventDefault(); setSelectedKey(s.section_key); }}>
                        {s.label} <Text span c="dimmed" size="xs">{s.code} · {s.meshes}</Text>
                      </Text>
                    } />
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
          <Stack gap={6}>
            <Group gap="sm">
              <SegmentedControl size="xs" value={preset} data={PRESETS}
                onChange={(v) => { setPreset(v as Preset); viewerRef.current?.preset(v as Preset); }} />
              <Text size="xs" id="picked-node">{picked ? `${picked.node} · ${picked.section}` : '부재를 클릭하면 노드명이 표시됩니다'}</Text>
              {picked && <Button size="compact-xs" variant="subtle" onClick={() => { setPicked(null); viewerRef.current?.highlight(null); }}>선택 해제</Button>}
            </Group>
            <Group gap="sm">
              <Switch size="xs" label="z 단면" checked={clipZ.enabled} onChange={(e) => setClipZ({ ...clipZ, enabled: e.currentTarget.checked })} />
              <Slider w={220} size="xs" min={0} max={70} step={0.1} value={clipZ.d} disabled={!clipZ.enabled}
                label={(v) => `P4+${v.toFixed(1)} m`} onChange={(d) => setClipZ({ ...clipZ, d })} />
              <SegmentedControl size="xs" value={clipZ.keep} data={KEEPS} onChange={(v) => setClipZ({ ...clipZ, keep: v as Keep })} />
            </Group>
            <Group gap="sm">
              <Switch size="xs" label="x 절개" checked={clipX.enabled} onChange={(e) => setClipX({ ...clipX, enabled: e.currentTarget.checked })} />
              <Slider w={220} size="xs" min={-8} max={8} step={0.05} value={clipX.x} disabled={!clipX.enabled}
                label={(v) => `x=${v.toFixed(2)} m`} onChange={(x) => setClipX({ ...clipX, x })} />
              <SegmentedControl size="xs" value={clipX.keep} data={KEEPS} onChange={(v) => setClipX({ ...clipX, keep: v as Keep })} />
            </Group>
          </Stack>
        </Paper>
      </Box>
      <Paper w={340} p="md" withBorder radius={0}>
        {build && (
          <VerifyPanel project={project} build={build} sections={sections} selected={selected}
            renderUrls={renderUrls} downloadUrls={downloadUrls} approvals={approvals} onApproved={onApproved} />
        )}
      </Paper>
    </Group>
  );
}
