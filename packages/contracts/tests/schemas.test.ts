import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { describe, expect, it } from 'vitest';
import { SCHEMA_FILES, fixtureDir, loadSchema, schemaDir } from '../src/node.js';
import { MEMBER_CODE_PATTERN } from '../src/memberName.js';

function makeAjv() {
  // strictTuples 는 prefixItems 를 "닫힌 튜플"로만 가정하는 휴리스틱이라,
  // "첫 항목만 추가 제약 + 나머지는 items" (ambiguity.options) 를 오탐한다.
  // 규칙 자체는 아래 invalid 케이스가 거부되는 것으로 검증된다.
  // allowUnionTypes: SsotItem.value 는 수치와 텍스트("가변" 등)를 모두 담는다 — 의도된 유니온.
  const ajv = new Ajv2020({
    allErrors: true,
    strict: true,
    strictTuples: false,
    allowUnionTypes: true,
  });
  addFormats(ajv);
  for (const name of SCHEMA_FILES) ajv.addSchema(loadSchema(name));
  return ajv;
}

interface CaseFile {
  schema?: string;
  valid?: unknown[];
  invalid?: { why: string; doc: unknown }[];
}

function loadCases(name: string): CaseFile {
  return JSON.parse(readFileSync(join(fixtureDir(), name), 'utf8')) as CaseFile;
}

describe('JSON Schema 정본', () => {
  it('SCHEMA_FILES 가 schemas/ 디렉터리와 일치한다', () => {
    const onDisk = readdirSync(schemaDir())
      .filter((f) => f.endsWith('.schema.json'))
      .sort();
    expect(onDisk).toEqual([...SCHEMA_FILES].sort());
  });

  it('모든 스키마가 유효한 draft 2020-12 이다', () => {
    // addSchema 가 컴파일까지 통과하면 스키마 자체가 유효하다.
    expect(() => makeAjv()).not.toThrow();
  });

  it('부재 코드 정규식이 member.schema.json 의 pattern 과 문자열까지 같다', () => {
    const schema = loadSchema('member.schema.json') as {
      properties: { code: { pattern: string } };
    };
    expect(schema.properties.code.pattern).toBe(MEMBER_CODE_PATTERN);
  });
});

const CASE_FILES = ['ambiguity', 'decision', 'ssot_item', 'verification_report'];

describe.each(CASE_FILES)('%s 케이스', (base) => {
  const cases = loadCases(`${base}.cases.json`);
  const ajv = makeAjv();
  const schemaId = `https://model3d.studio/schemas/${cases.schema}`;
  const validate = ajv.getSchema(schemaId);

  it('스키마를 찾을 수 있다', () => {
    expect(validate, `${schemaId} 미등록`).toBeDefined();
  });

  it('valid 문서를 모두 통과시킨다', () => {
    for (const [i, doc] of (cases.valid ?? []).entries()) {
      const ok = validate!(doc);
      expect(ok, `valid[${i}] 거부됨: ${ajv.errorsText(validate!.errors)}`).toBe(true);
    }
  });

  it('invalid 문서를 모두 거부한다 — 규칙이 스키마로 강제되는지의 증거', () => {
    for (const [i, c] of (cases.invalid ?? []).entries()) {
      const ok = validate!(c.doc);
      expect(ok, `invalid[${i}] 이 통과됨 (거부되어야 함): ${c.why}`).toBe(false);
    }
  });
});
