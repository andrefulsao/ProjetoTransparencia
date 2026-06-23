from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from config import settings


class Database:
    """Small Supabase wrapper for schema-qualified upserts and collection logs."""

    def __init__(self, client: Client | None = None) -> None:
        if client is not None:
            self.client = client
        elif settings.has_supabase:
            self.client = create_client(settings.supabase_url, settings.supabase_key)
        else:
            self.client = None

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def table(self, name: str):
        if self.client is None:
            raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
        return self.client.schema("transparencia").table(name)

    def upsert(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        on_conflict: str | None = None,
    ) -> dict[str, int]:
        """Upsert rows into a table and return coarse write counters."""
        if not rows:
            return {"inserted": 0, "updated": 0}
        query = self.table(table_name).upsert(rows, on_conflict=on_conflict)
        query.execute()
        return {"inserted": len(rows), "updated": 0}

    def select(
        self,
        table_name: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        is_null: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows from a schema-qualified table."""
        if limit is not None:
            query = self._select_query(table_name, columns, filters, is_null)
            query = query.limit(limit)
            result = query.execute()
            return result.data or []

        rows: list[dict[str, Any]] = []
        page_size = 1000
        offset = 0
        while True:
            query = self._select_query(table_name, columns, filters, is_null)
            result = query.range(offset, offset + page_size - 1).execute()
            page = result.data or []
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size

    def _select_query(
        self,
        table_name: str,
        columns: str,
        filters: dict[str, Any] | None,
        is_null: list[str] | None,
    ):
        query = self.table(table_name).select(columns)
        for key, value in (filters or {}).items():
            query = query.eq(key, value)
        for key in is_null or []:
            query = query.is_(key, "null")
        return query

    def update_by_id(self, table_name: str, row_id: str, values: dict[str, Any]) -> None:
        """Update one row by primary key."""
        self.table(table_name).update(values).eq("id", row_id).execute()

    def insert_log(self, row: dict[str, Any]) -> None:
        """Insert one row into transparencia.coleta_log when Supabase is configured."""
        if not self.enabled:
            return
        self.table("coleta_log").insert(row).execute()

    def latest_logs(self, fonte: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent collection logs."""
        query = self.table("coleta_log").select("*").order("executado_em", desc=True).limit(limit)
        if fonte:
            query = query.eq("fonte", fonte)
        result = query.execute()
        return result.data or []

    def latest_log(
        self,
        *,
        fonte: str,
        endpoint: str,
        parametros_contains: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return latest log for a source and endpoint."""
        query = (
            self.table("coleta_log")
            .select("*")
            .eq("fonte", fonte)
            .eq("endpoint", endpoint)
            .order("executado_em", desc=True)
            .limit(10)
        )
        result = query.execute()
        rows = result.data or []
        if not parametros_contains:
            return rows[0] if rows else None
        for row in rows:
            parametros = row.get("parametros") or {}
            if all(parametros.get(key) == value for key, value in parametros_contains.items()):
                return row
        return None
