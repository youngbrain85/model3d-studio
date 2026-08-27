/**
 * JSON Schema 파일 로더. 스키마 파일은 이 패키지의 정본이며,
 * TS·Python 테스트가 **같은 파일**을 읽어 검증한다.
 *
 * Node 전용(fs 사용). 브라우저 번들에 끌려들어가지 않도록 UI 코드에서는 import 하지 않는다.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/** schemas/ 안의 스키마 파일 목록. 새 스키마를 추가하면 여기에도 등록한다 (테스트가 강제). */
export const SCHEMA_FILES = [
  'ambiguity.schema.json',
  'coordinate_system.schema.json',
  'decision.schema.json',
  'member.schema.json',
  'sample_manifest.schema.json',
  'sample_set.schema.json',
  'sheet.schema.json',
  'ssot_item.schema.json',
  'verification_report.schema.json',
  'view_contract.schema.json',
] as const;

export type SchemaFile = (typeof SCHEMA_FILES)[number];

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..');

export function schemaDir(): string {
  return join(packageRoot, 'schemas');
}

export function fixtureDir(): string {
  return join(packageRoot, 'fixtures');
}

export function loadSchema(name: SchemaFile): Record<string, unknown> {
  return JSON.parse(readFileSync(join(schemaDir(), name), 'utf8')) as Record<string, unknown>;
}
