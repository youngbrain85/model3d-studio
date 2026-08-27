import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { fixtureDir } from '../src/node.js';
import type { MemberSide } from '../src/types.js';
import {
  MEMBER_CODE_PATTERN,
  formatMemberCode,
  isValidMemberCode,
  memberCodeMatchesFields,
  parseMemberCode,
} from '../src/memberName.js';

interface MemberCases {
  pattern: string;
  valid: {
    code: string;
    structure: string;
    segment: string;
    member_type: string;
    index: number;
    side: MemberSide | null;
    index_width: number;
  }[];
  invalid: { code: string; why: string }[];
}

const fixture = JSON.parse(
  readFileSync(join(fixtureDir(), 'member_code.cases.json'), 'utf8'),
) as MemberCases;

describe('부재 명명 규칙 (규칙 §5)', () => {
  it('픽스처의 패턴이 구현 상수와 같다', () => {
    expect(fixture.pattern).toBe(MEMBER_CODE_PATTERN);
  });

  it.each(fixture.valid)('$code 를 성분으로 분해한다', (c) => {
    expect(isValidMemberCode(c.code)).toBe(true);
    const parsed = parseMemberCode(c.code);
    expect(parsed).not.toBeNull();
    expect(parsed!.structure).toBe(c.structure);
    expect(parsed!.segment).toBe(c.segment);
    expect(parsed!.member_type).toBe(c.member_type);
    expect(parsed!.index).toBe(c.index);
    expect(parsed!.side).toBe(c.side);
    expect(parsed!.indexWidth).toBe(c.index_width);
  });

  it.each(fixture.valid)('$code 를 성분에서 그대로 재조립한다', (c) => {
    expect(
      formatMemberCode({
        structure: c.structure,
        segment: c.segment,
        member_type: c.member_type,
        index: c.index,
        side: c.side,
        indexWidth: c.index_width,
      }),
    ).toBe(c.code);
  });

  it.each(fixture.invalid)('$code 를 거부한다 — $why', (c) => {
    expect(isValidMemberCode(c.code)).toBe(false);
    expect(parseMemberCode(c.code)).toBeNull();
  });

  it('규칙에 맞지 않는 조립은 조용히 넘어가지 않고 던진다', () => {
    expect(() =>
      formatMemberCode({ structure: 'ab1', segment: 'S5', member_type: 'DIA', index: 7 }),
    ).toThrow(/부재 명명 규칙 위반/);
  });

  it('code 와 분해 성분이 어긋나면 잡아낸다', () => {
    const ok = {
      code: 'AB1_S5_DIA07',
      project_id: 'p',
      structure: 'AB1',
      segment: 'S5',
      member_type: 'DIA',
      index: 7,
      side: null,
    };
    expect(memberCodeMatchesFields(ok)).toBe(true);
    expect(memberCodeMatchesFields({ ...ok, index: 8 })).toBe(false);
    expect(memberCodeMatchesFields({ ...ok, segment: 'S6' })).toBe(false);
  });
});
