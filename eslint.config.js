// @ts-check
import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

/**
 * 워크스페이스 전체를 하나의 flat config 로 린트한다.
 * 타입 검사는 `tsc` 가 담당하므로 여기서는 타입 인지 규칙을 켜지 않는다 (CI 속도·안정성).
 */
export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/coverage/**',
      '**/node_modules/**',
      '**/.venv/**',
      'samples/**/source/**',
      'samples/**/derived/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      'no-restricted-syntax': [
        'error',
        {
          // 규칙 §1: "도면 치수는 mm 정본, 모델은 m — 변환은 한 곳(빌더 상수)에서만."
          // 1000 으로 곱하거나 나누는 식이 흩어지면 그 한 곳이 무너진다. units.ts 만 예외다.
          // (카메라 far 평면 같은 무관한 1000 리터럴은 잡지 않는다.)
          selector: 'BinaryExpression[operator=/^[*\\/]$/] > Literal[value=1000]',
          message:
            'mm↔m 변환 상수는 @model3d/contracts 의 units.ts (MM_PER_MODEL_UNIT) 한 곳에만 둔다 (규칙 §1).',
        },
      ],
    },
  },
  {
    // units.ts 가 그 "한 곳"이다.
    files: ['packages/contracts/src/units.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },
  {
    files: ['apps/web/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    languageOptions: { globals: globals.browser },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    files: ['**/*.test.ts', '**/*.test.tsx', '**/tests/**/*.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },
  {
    // 설정·스크립트 파일은 node 환경이다.
    files: ['**/*.{js,mjs,cjs}'],
    languageOptions: { globals: globals.node },
  },
);
