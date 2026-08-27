/**
 * @model3d/contracts/node — node 전용 진입점.
 *
 * 스키마·픽스처 파일을 디스크에서 읽는다. `node:fs` 를 쓰므로
 * 브라우저 번들에 들어가면 안 된다 — 그래서 메인 진입점에서 분리했다.
 */
export { SCHEMA_FILES, loadSchema, schemaDir, fixtureDir } from './schemas.js';
export type { SchemaFile } from './schemas.js';
