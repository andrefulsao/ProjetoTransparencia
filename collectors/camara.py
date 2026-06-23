from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from collectors.base import BaseCollector
from config import settings
from utils.normalization import decimal_from_brl, normalize_cpf, normalize_document


class CamaraParlamentaresCollector(BaseCollector):
    """Collect current federal deputies from Dados Abertos da Camara."""

    source = "camara"
    base_url = "https://dadosabertos.camara.leg.br/api/v2/"

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("rate_limit_per_minute", settings.rate_limit_camara)
        kwargs.setdefault("timeout_seconds", settings.request_timeout_seconds)
        super().__init__(*args, **kwargs)
        self._detail_semaphore = asyncio.Semaphore(5)

    async def collect(self) -> list[dict[str, Any]]:
        deputies = await self.collect_paginated(
            "deputados",
            params={"ordem": "ASC", "ordenarPor": "nome"},
            page_size=100,
        )
        detail_tasks = [self._enrich_deputy(item) for item in deputies]
        records = await asyncio.gather(*detail_tasks)
        return [record for record in records if record]

    async def _enrich_deputy(self, item: dict[str, Any]) -> dict[str, Any] | None:
        deputy_id = item.get("id")
        detail: dict[str, Any] = {}
        if deputy_id is not None:
            async with self._detail_semaphore:
                payload = await self.request_json(f"deputados/{deputy_id}")
                detail = payload.get("dados", {}) if isinstance(payload, dict) else {}

        status = detail.get("ultimoStatus") or {}
        raw_data = {"lista": item, "detalhe": detail}
        return {
            "nome_civil": detail.get("nomeCivil") or item.get("nome"),
            "nome_parlamentar": status.get("nomeEleitoral") or item.get("nome"),
            "cpf": normalize_cpf(detail.get("cpf")),
            "casa": "camara",
            "partido": status.get("siglaPartido") or item.get("siglaPartido"),
            "uf": status.get("siglaUf") or item.get("siglaUf"),
            "legislatura": status.get("idLegislatura") or item.get("idLegislatura"),
            "id_camara": deputy_id,
            "codigo_senado": None,
            "foto_url": status.get("urlFoto") or item.get("urlFoto"),
            "email": status.get("email") or item.get("email"),
            "situacao": status.get("situacao") or detail.get("situacao"),
            "raw_data": raw_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def persist(self, records: list[dict[str, Any]]) -> dict[str, int]:
        return self.upsert_rows("parlamentares", records, on_conflict="id_camara")

    async def coletar_cota_parlamentar(self, deputado_id: int, ano: int) -> dict[str, int]:
        """Collect CEAP expenses for one deputy and year."""
        started_at = time.monotonic()
        status = "sucesso"
        error = None
        records: list[dict[str, Any]] = []
        write_result = {"inserted": 0, "updated": 0}
        params = {"deputado_id": deputado_id, "ano": ano}

        try:
            parlamentar_id = self._get_parlamentar_id_by_camara_id(deputado_id)
            raw_records = await self.collect_paginated(
                f"deputados/{deputado_id}/despesas",
                params={"ano": ano, "ordem": "ASC", "ordenarPor": "mes"},
                page_size=100,
            )
            records = [
                self._normalize_cota(item, parlamentar_id=parlamentar_id, ano=ano)
                for item in raw_records
            ]
            write_result = self.upsert_rows(
                "cota_parlamentar",
                records,
                on_conflict=(
                    "parlamentar_id,ano,mes,tipo_despesa,"
                    "fornecedor_cnpj_cpf,valor_documento"
                ),
            )
            return {
                "coletados": len(records),
                "inseridos": write_result.get("inserted", 0),
                "atualizados": write_result.get("updated", 0),
            }
        except Exception as exc:
            status = "erro"
            error = str(exc)
            self.logger.exception(
                "cota_collection_failed",
                deputado_id=deputado_id,
                ano=ano,
                error=error,
            )
            raise
        finally:
            self.log_collection(
                endpoint="deputados/despesas",
                parametros=params,
                registros_coletados=len(records),
                registros_inseridos=write_result.get("inserted", 0),
                registros_atualizados=write_result.get("updated", 0),
                status=status,
                erro=error,
                duracao_segundos=time.monotonic() - started_at,
            )

    async def coletar_todas_cotas(self, ano: int) -> dict[str, int]:
        """Collect CEAP expenses for all Camara parliamentarians with checkpointing."""
        if not self.db.enabled:
            raise RuntimeError("Supabase precisa estar configurado para coletar todas as cotas.")

        deputies = self.db.select(
            "parlamentares",
            columns="id,id_camara,nome_parlamentar",
            filters={"casa": "camara"},
        )
        deputies = [row for row in deputies if row.get("id_camara")]
        deputies.sort(key=lambda row: int(row["id_camara"]))

        checkpoint = self.db.latest_log(
            fonte=self.source,
            endpoint="deputados/despesas/checkpoint",
            parametros_contains={"ano": ano},
        )
        last_processed = None
        if checkpoint:
            last_processed = (checkpoint.get("parametros") or {}).get("ultimo_deputado_id")

        if last_processed:
            deputies = [
                row for row in deputies if int(row["id_camara"]) > int(last_processed)
            ]

        totals = {
            "deputados_processados": 0,
            "registros_coletados": 0,
            "registros_inseridos": 0,
            "registros_atualizados": 0,
            "ultimo_deputado_id": last_processed,
        }

        for index, deputy in enumerate(deputies, start=1):
            deputado_id = int(deputy["id_camara"])
            result = await self.coletar_cota_parlamentar(deputado_id=deputado_id, ano=ano)
            totals["deputados_processados"] += 1
            totals["registros_coletados"] += result.get("coletados", 0)
            totals["registros_inseridos"] += result.get("inseridos", 0)
            totals["registros_atualizados"] += result.get("atualizados", 0)
            totals["ultimo_deputado_id"] = deputado_id

            if index % 50 == 0:
                self._save_cota_checkpoint(ano=ano, totals=totals)

        if totals["deputados_processados"]:
            self._save_cota_checkpoint(ano=ano, totals=totals)

        return totals

    def _get_parlamentar_id_by_camara_id(self, deputado_id: int) -> str | None:
        if not self.db.enabled:
            return None
        rows = self.db.select(
            "parlamentares",
            columns="id",
            filters={"id_camara": deputado_id},
            limit=1,
        )
        return rows[0]["id"] if rows else None

    def _normalize_cota(
        self,
        item: dict[str, Any],
        *,
        parlamentar_id: str | None,
        ano: int,
    ) -> dict[str, Any]:
        return {
            "parlamentar_id": parlamentar_id,
            "ano": self._to_int(item.get("ano")) or ano,
            "mes": self._to_int(item.get("mes")),
            "tipo_despesa": item.get("tipoDespesa"),
            "descricao": item.get("tipoDocumento") or item.get("numDocumento"),
            "fornecedor_nome": item.get("nomeFornecedor"),
            "fornecedor_cnpj_cpf": normalize_document(item.get("cnpjCpfFornecedor")),
            "valor_documento": self._decimal_text(item.get("valorDocumento")),
            "valor_glosa": self._decimal_text(item.get("valorGlosa")),
            "valor_liquido": self._decimal_text(item.get("valorLiquido")),
            "url_documento": item.get("urlDocumento"),
            "fonte": self.source,
        }

    def _save_cota_checkpoint(self, *, ano: int, totals: dict[str, Any]) -> None:
        self.log_collection(
            endpoint="deputados/despesas/checkpoint",
            parametros={
                "ano": ano,
                "ultimo_deputado_id": totals.get("ultimo_deputado_id"),
                "deputados_processados": totals.get("deputados_processados"),
            },
            registros_coletados=totals.get("registros_coletados", 0),
            registros_inseridos=totals.get("registros_inseridos", 0),
            registros_atualizados=totals.get("registros_atualizados", 0),
            status="sucesso",
            erro=None,
            duracao_segundos=0,
        )

    @staticmethod
    def _to_int(value: object | None) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decimal_text(value: object | None) -> str | None:
        parsed = decimal_from_brl(value)
        return str(parsed) if parsed is not None else None
