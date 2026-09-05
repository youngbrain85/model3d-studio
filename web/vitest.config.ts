import { defineConfig } from 'vitest/config';

// 순수 로직(lib/*.test.ts)만 돌린다 — 컴포넌트 렌더 테스트는 브라우저 E2E 로 대체 (설계서 §6)
export default defineConfig({
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
