#!/usr/bin/env bash
# Supabase 스키마 검증 — 마이그레이션을 실제 PostgreSQL 에 적용하고 도메인 규칙 테스트를 돌린다.
#
# "검증 없이 완료 주장 금지"(규칙 §6). SQL 은 실행해 보기 전에는 맞는지 알 수 없다.
#
# 사용법:
#   scripts/verify-supabase.sh                       # PGHOST 등 환경변수 사용
#   PGDATABASE=m3d_verify scripts/verify-supabase.sh
#
# 테스트는 빈 DB 를 전제로 한다(고정 UUID 를 삽입하므로 재실행 불가) — 매번 새로 만든다.
set -euo pipefail

DB="${PGDATABASE:-m3d_verify}"
export PGDATABASE=postgres

echo "▶ 데이터베이스 재생성: $DB"
psql -q -tAc "drop database if exists ${DB};"
psql -q -tAc "create database ${DB};"

export PGDATABASE="$DB"

echo "▶ Supabase shim (auth/storage 흉내 — 마이그레이션에는 포함되지 않음)"
psql -v ON_ERROR_STOP=1 -q -f supabase/tests/00_supabase_shim.sql

for f in supabase/migrations/*.sql; do
  echo "▶ 마이그레이션: $(basename "$f")"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
done

echo "▶ 도메인 규칙 테스트"
out="$(psql -v ON_ERROR_STOP=1 -f supabase/tests/01_domain_rules_test.sql 2>&1)"
echo "$out"

# 테스트는 통과 항목을 " ok " 로, 실패를 " FAIL " 로 낸다.
# (설명 문구 안의 'FAIL' 과 구분하려고 줄 시작 기준으로 센다.)
ok_count="$(grep -cE '^ +ok ' <<<"$out" || true)"
fail_count="$(grep -cE '^ +FAIL ' <<<"$out" || true)"

echo
echo "── 결과: 통과 ${ok_count} / 실패 ${fail_count}"
if [[ "$fail_count" != "0" ]]; then
  echo "✗ 도메인 규칙 테스트 실패" >&2
  exit 1
fi
if [[ "$ok_count" == "0" ]]; then
  echo "✗ 통과 항목이 0 이다 — 테스트가 실제로 돌지 않았다" >&2
  exit 1
fi
echo "✓ Supabase 스키마 검증 통과"
