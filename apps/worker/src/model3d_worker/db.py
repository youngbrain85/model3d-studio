"""Supabase REST 헬퍼 — 아키텍처 §3 의 ``_db.py`` 패턴.

스키마·시딩·검증 쿼리를 위해 PostgREST 를 직접 친다. 워커는 service key 를 쓰므로
**RLS 를 우회**한다 — 그만큼 이 모듈을 통과하는 코드는 프로젝트 경계를 스스로 지켜야 한다.

키는 절대 로그·예외 메시지에 넣지 않는다 (CLAUDE.md §3).
"""

from __future__ import annotations

from typing import Any, Literal, Self

import httpx

from .config import Settings, get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """SUPABASE_URL / SUPABASE_SERVICE_KEY 가 없다."""


class SupabaseRest:
    """PostgREST 최소 클라이언트."""

    def __init__(self, settings: Settings | None = None, *, timeout: float = 30.0) -> None:
        s = settings or get_settings()
        if not s.supabase_url or not s.supabase_service_key:
            raise SupabaseNotConfiguredError(
                "SUPABASE_URL / SUPABASE_SERVICE_KEY 가 설정되지 않았습니다. "
                ".env.example 을 참고해 로컬 .env 를 채우세요 (커밋 금지)."
            )
        key = s.supabase_service_key.get_secret_value()
        self._client = httpx.Client(
            base_url=s.supabase_url.rstrip("/") + "/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        limit: int | None = None,
        **filters: str,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": columns, **filters}
        if limit is not None:
            params["limit"] = str(limit)
        r = self._client.get(f"/{table}", params=params)
        _raise_for_status(r)
        data: list[dict[str, Any]] = r.json()
        return data

    def insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
        returning: Literal["representation", "minimal"] = "representation",
    ) -> list[dict[str, Any]]:
        headers = {"Prefer": f"return={returning}"}
        params: dict[str, str] = {}
        if on_conflict:
            headers["Prefer"] = f"resolution=merge-duplicates,return={returning}"
            params["on_conflict"] = on_conflict
        r = self._client.post(f"/{table}", json=rows, headers=headers, params=params)
        _raise_for_status(r)
        if returning == "minimal" or not r.content:
            return []
        data: list[dict[str, Any]] = r.json()
        return data

    def health(self) -> bool:
        """연결과 인증이 살아 있는지 확인한다. 스키마가 비어 있어도 True 일 수 있다."""
        r = self._client.get("/", params={})
        return r.status_code < 500


def _raise_for_status(r: httpx.Response) -> None:
    """오류를 올릴 때 **요청 헤더(키 포함)를 노출하지 않는다.**"""
    if r.is_success:
        return
    body = r.text[:500]
    raise httpx.HTTPStatusError(
        f"Supabase REST {r.request.method} {r.request.url.path} → {r.status_code}: {body}",
        request=r.request,
        response=r,
    )
