from __future__ import annotations

import time
from typing import Any

import structlog

from collectors.base import BaseCollector
from config import settings
from db import Database
from utils.normalization import decimal_from_brl, normalize_name


class TransparenciaCollector(BaseCollector):
    """Collect data from Portal da Transparencia APIs."""

    source = "portal_transparencia"
    base_url = "https://api.portaldatransparencia.gov.br/api-de-dados/"

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("rate_limit_per_minute", settings.rate_limit_transparencia)
        kwargs.setdefault("timeout_seconds", settings.request_timeout_seconds)
        super().__init__(*args, **kwargs)
        self._parlamentar_name_index: dict[str, str] | None = None
        self.logger = structlog.get_logger(self.__class__.__name__).bind(source=self.source)

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        if settings.transparencia_api_key:
            headers["chave-api-dados"] = settings.transparencia_api_key
        return headers

    async def collect(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Use coletar_emendas(ano).")

    def persist(self, records: list[dict[str, Any]]) -> dict[str, int]:
        return self.upsert_rows("emendas", records, on_conflict="numero_emenda,ano")

    async def coletar_emendas(self, ano: int) -> dict[str, int]:
        """Collect parliamentary amendments for one year and persist them."""
        started_at = time.monotonic()
        status = "sucesso"
        error = None
        records: list[dict[str, Any]] = []
        write_result = {"inserted": 0, "updated": 0}
        params = {"ano": ano}

        try:
            raw_records = await self.collect_paginated(
                "emendas",
                params=params,
                page_param="pagina",
                page_size_param="tamanhoPagina",
                page_size=500,
                data_key="dados",
            )
            records = [self._normalize_emenda(item, ano) for item in raw_records]
            write_result = self.persist(records)
            return {
                "coletados": len(records),
                "inseridos": write_result.get("inserted", 0),
                "atualizados": write_result.get("updated", 0),
                "vinculados": sum(1 for row in records if row.get("parlamentar_id")),
                "pendentes": sum(1 for row in records if not row.get("parlamentar_id")),
            }
        except Exception as exc:
            status = "erro"
            error = str(exc)
            self.logger.exception("emendas_collection_failed", ano=ano, error=error)
            raise
        finally:
            self.log_collection(
                endpoint="emendas",
                parametros=params,
                registros_coletados=len(records),
                registros_inseridos=write_result.get("inserted", 0),
                registros_atualizados=write_result.get("updated", 0),
                status=status,
                erro=error,
                duracao_segundos=time.monotonic() - started_at,
            )

    def _normalize_emenda(self, item: dict[str, Any], ano: int) -> dict[str, Any]:
        author = self._first(
            item,
            "autor",
            "nomeAutor",
            "nomeAutorEmenda",
            "autorEmenda",
            "nomeParlamentar",
        )
        numero = self._first(item, "codigoEmenda", "numeroEmenda", "numero", "id")
        normalized_author = normalize_name(author)
        return {
            "parlamentar_id": self._find_parlamentar_id_by_name(normalized_author),
            "numero_emenda": str(numero) if numero is not None else None,
            "tipo": self._to_int(self._first(item, "tipoEmenda", "codigoTipoEmenda")),
            "ano": self._to_int(self._first(item, "ano", "anoEmenda")) or ano,
            "autor": author,
            "localidade_gasto": self._first(
                item,
                "localidadeDoGasto",
                "localidadeGasto",
                "localidade",
                "ufBeneficiada",
            ),
            "cod_funcao": self._first(item, "codFuncao", "codigoFuncao", "funcao"),
            "cod_subfuncao": self._first(item, "codSubfuncao", "codigoSubfuncao", "subfuncao"),
            "valor_empenhado": self._decimal_text(
                self._first(item, "valorEmpenhado", "valor_empenhado")
            ),
            "valor_liquidado": self._decimal_text(
                self._first(item, "valorLiquidado", "valor_liquidado")
            ),
            "valor_pago": self._decimal_text(self._first(item, "valorPago", "valor_pago")),
            "valor_resto_pago": self._decimal_text(
                self._first(item, "valorRestoPago", "valorRestosAPagar", "valor_resto_pago")
            ),
            "fonte": self.source,
            "raw_data": item,
        }

    def _find_parlamentar_id_by_name(self, normalized_name: str | None) -> str | None:
        if not normalized_name or not self.db.enabled:
            return None
        if self._parlamentar_name_index is None:
            self._parlamentar_name_index = self._build_parlamentar_name_index()
        return self._parlamentar_name_index.get(normalized_name)

    def _build_parlamentar_name_index(self) -> dict[str, str]:
        rows = self.db.select(
            "parlamentares",
            columns="id,nome_civil,nome_parlamentar",
        )
        index: dict[str, str] = {}
        for row in rows:
            row_id = row.get("id")
            if not row_id:
                continue
            for key in ("nome_civil", "nome_parlamentar"):
                normalized = normalize_name(row.get(key))
                if normalized and normalized not in index:
                    index[normalized] = row_id
        return index

    @staticmethod
    def _first(item: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
        return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decimal_text(value: Any) -> str | None:
        parsed = decimal_from_brl(value)
        return str(parsed) if parsed is not None else None
