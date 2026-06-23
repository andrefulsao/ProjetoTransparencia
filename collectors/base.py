from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from db import Database
from utils.rate_limiter import AsyncTokenBucket


class BaseCollector(ABC):
    """
    Base async collector with retries, rate limiting, pagination helpers,
    Supabase upsert support and coleta_log persistence.
    """

    source: str
    base_url: str

    def __init__(
        self,
        db: Database | None = None,
        rate_limit_per_minute: int = 30,
        timeout_seconds: float = 30,
    ) -> None:
        self.db = db or Database()
        self.rate_limiter = AsyncTokenBucket(rate_limit_per_minute)
        self.timeout_seconds = timeout_seconds
        self.logger = structlog.get_logger(self.__class__.__name__).bind(source=self.source)

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.default_headers(),
            timeout=self.timeout_seconds,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.client.aclose()

    def default_headers(self) -> dict[str, str]:
        return {"User-Agent": "transparencia-brasil-pipeline/0.1"}

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=32),
        reraise=True,
    )
    async def request_json(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a GET request and return parsed JSON."""
        await self.rate_limiter.acquire()
        response = await self.client.get(endpoint, params=params)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    async def collect_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        page_param: str = "pagina",
        page_size_param: str = "itens",
        page_size: int = 100,
        data_key: str = "dados",
        start_page: int = 1,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Collect endpoints that expose numeric pagination and optional link metadata."""
        records: list[dict[str, Any]] = []
        page = start_page
        base_params = dict(params or {})

        while True:
            request_params = {
                **base_params,
                page_param: page,
                page_size_param: page_size,
            }
            payload = await self.request_json(endpoint, request_params)
            if isinstance(payload, list):
                page_records = payload
            elif isinstance(payload, dict):
                page_records = payload.get(data_key, [])
            else:
                page_records = []
            if not page_records:
                break

            records.extend(page_records)
            if max_pages and page >= max_pages:
                break

            links = payload.get("links", []) if isinstance(payload, dict) else []
            has_next = any(link.get("rel") == "next" for link in links if isinstance(link, dict))
            if not has_next and len(page_records) < page_size:
                break
            page += 1

        return records

    def upsert_rows(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        on_conflict: str | None = None,
    ) -> dict[str, int]:
        """Persist rows when Supabase is configured."""
        if not self.db.enabled:
            self.logger.warning("supabase_not_configured", table=table_name, rows=len(rows))
            return {"inserted": 0, "updated": 0}
        return self.db.upsert(table_name, rows, on_conflict=on_conflict)

    def log_collection(
        self,
        *,
        endpoint: str,
        parametros: dict[str, Any] | None,
        registros_coletados: int,
        registros_inseridos: int,
        registros_atualizados: int,
        status: str,
        erro: str | None,
        duracao_segundos: float,
    ) -> None:
        self.db.insert_log(
            {
                "fonte": self.source,
                "endpoint": endpoint,
                "parametros": parametros or {},
                "registros_coletados": registros_coletados,
                "registros_inseridos": registros_inseridos,
                "registros_atualizados": registros_atualizados,
                "status": status,
                "erro": erro,
                "duracao_segundos": round(duracao_segundos, 2),
            }
        )

    async def run_logged(self, endpoint: str, params: dict[str, Any] | None = None) -> int:
        """Run collect(), upsert records and write coleta_log."""
        started_at = time.monotonic()
        collected = 0
        inserted = 0
        updated = 0
        status = "sucesso"
        error = None
        try:
            records = await self.collect()
            collected = len(records)
            result = self.persist(records)
            inserted = result.get("inserted", 0)
            updated = result.get("updated", 0)
            return collected
        except Exception as exc:
            status = "erro"
            error = str(exc)
            self.logger.exception("collection_failed", error=error)
            raise
        finally:
            self.log_collection(
                endpoint=endpoint,
                parametros=params,
                registros_coletados=collected,
                registros_inseridos=inserted,
                registros_atualizados=updated,
                status=status,
                erro=error,
                duracao_segundos=time.monotonic() - started_at,
            )

    @abstractmethod
    async def collect(self) -> list[dict[str, Any]]:
        """Collect normalized records."""

    @abstractmethod
    def persist(self, records: list[dict[str, Any]]) -> dict[str, int]:
        """Persist normalized records."""
