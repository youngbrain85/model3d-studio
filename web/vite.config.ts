import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// 리포 루트 — .env 와 contracts/ 가 여기 있다 (설계서 §8)
const repoRoot = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig({
  plugins: [react()],
  envDir: repoRoot,
  server: {
    fs: { allow: [repoRoot] },
  },
});
