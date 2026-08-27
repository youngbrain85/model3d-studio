/**
 * @model3d/contracts — 워커(Python)와 웹(TS)이 공유하는 데이터 계약.
 *
 * **정본은 `schemas/*.json` (JSON Schema draft 2020-12)** 이다.
 * 이 패키지의 TS 타입·헬퍼와 `apps/worker` 의 pydantic 모델은 그 미러이며,
 * `fixtures/` 를 양쪽에서 같은 스키마로 검증하는 테스트가 둘의 일치를 보장한다.
 *
 * 이 진입점은 **브라우저 안전**하다 — node 내장 모듈을 쓰지 않는다.
 * 스키마 파일을 fs 로 읽어야 하면 `@model3d/contracts/node` 를 쓴다.
 */
export * from './types.js';
export * from './units.js';
export * from './viewContract.js';
export * from './memberName.js';
