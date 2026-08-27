import { describeEnv } from './lib/env.js';
import { GlbViewer } from './viewer/GlbViewer.js';

const PIPELINE_STAGES = [
  { n: 1, name: '업로드', status: 'M1' },
  { n: 2, name: '변환·정규화', status: 'M1' },
  { n: 3, name: '카탈로그·분류', status: 'M1' },
  { n: 4, name: '병렬 판독', status: 'M2' },
  { n: 5, name: '질문 루프', status: 'M2' },
  { n: 6, name: '병렬 모델링', status: 'M3' },
  { n: 7, name: '3중 검증', status: 'M3' },
  { n: 8, name: '산출·연동', status: 'M3' },
] as const;

/**
 * M0 스켈레톤 화면.
 * 파이프라인 8단계는 아직 하나도 구현되지 않았다 — 여기서 그 사실을 숨기지 않고 보여준다.
 */
export function App(): React.JSX.Element {
  const env = describeEnv(import.meta.env as unknown as Record<string, string | undefined>);

  return (
    <main className="app">
      <header>
        <h1>model3d-studio</h1>
        <p className="app__sub">AI 도면 기반 3D 모델링 — M0 부트스트랩</p>
      </header>

      <section>
        <h2>환경</h2>
        <p className={env.configured ? 'status status--ok' : 'status status--warn'}>
          {env.configured ? '✓' : '!'} {env.message}
        </p>
      </section>

      <section>
        <h2>파이프라인 단계</h2>
        <ol className="stages">
          {PIPELINE_STAGES.map((s) => (
            <li key={s.n}>
              <span className="stages__n">[{s.n}]</span> {s.name}
              <span className="stages__todo">미구현 · {s.status}</span>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2>3D 뷰어</h2>
        <p className="app__note">
          GLB 로더와 뷰 계약 카메라만 배선되어 있다. 모델은 M3 에서 붙는다.
        </p>
        <GlbViewer />
      </section>
    </main>
  );
}
