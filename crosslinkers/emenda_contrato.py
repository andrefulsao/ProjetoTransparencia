from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import structlog

from db import Database
from utils.normalization import normalize_cnpj


class EmendaContratoLinker:
    """Link emendas parlamentares to contratos by CNPJ of beneficiary."""

    source = "emenda_contrato_linker"

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.logger = structlog.get_logger(self.__class__.__name__)

    def cruzar(self, ano: int) -> dict[str, Any]:
        """Cross-reference paid emendas with contracts active during the year."""
        if not self.db.enabled:
            raise RuntimeError("Supabase precisa estar configurado para cruzar dados.")

        started_at = time.monotonic()
        status = "sucesso"
        error = None
        result: dict[str, Any] = {
            "emendas_com_pagamento": 0,
            "emendas_cruzadas": 0,
            "contratos_vinculados": 0,
            "valor_total_cruzado": "0",
            "top_fornecedores": [],
        }

        try:
            emendas = self._load_emendas_pagas(ano)
            contratos = self._load_contratos()
            contratos_por_cnpj = self._index_por_cnpj(contratos)

            result["emendas_com_pagamento"] = len(emendas)

            links: list[dict[str, Any]] = []
            seen_keys: set[tuple[str, str]] = set()
            emendas_com_match: set[str] = set()
            contratos_ids: set[str] = set()
            valor_total = Decimal("0")
            valor_por_cnpj: dict[str, Decimal] = {}

            for emenda in emendas:
                emenda_matched = False
                valor_pago = self._to_decimal(emenda.get("valor_pago")) or Decimal("0")
                raw = emenda.get("raw_data") or {}
                keywords = self._keywords_from_funcao(raw.get("funcao"), raw.get("subfuncao"))

                # Tenta CNPJ primeiro (alta confiança)
                cnpjs = self._extract_cnpjs(raw)
                for cnpj in cnpjs:
                    for contrato in contratos_por_cnpj.get(cnpj, []):
                        if not self._vigencia_compativel(contrato, ano):
                            continue
                        key = (emenda["id"], contrato["id"])
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        links.append({
                            "emenda_id": emenda["id"],
                            "contrato_id": contrato["id"],
                            "tipo_vinculo": "cnpj_favorecido",
                            "confianca": 0.8,
                        })
                        contratos_ids.add(contrato["id"])
                        emenda_matched = True
                        valor_por_cnpj[cnpj] = (
                            valor_por_cnpj.get(cnpj, Decimal("0")) + valor_pago
                        )

                # Fallback: match por funcao/subfuncao no objeto do contrato
                if not emenda_matched and keywords:
                    for contrato in contratos:
                        if not self._vigencia_compativel(contrato, ano):
                            continue
                        if not self._objeto_contem_keywords(contrato.get("objeto"), keywords):
                            continue
                        key = (emenda["id"], contrato["id"])
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        links.append({
                            "emenda_id": emenda["id"],
                            "contrato_id": contrato["id"],
                            "tipo_vinculo": "funcao_objeto",
                            "confianca": 0.3,
                        })
                        contratos_ids.add(contrato["id"])
                        emenda_matched = True
                        cnpj = contrato.get("fornecedor_cnpj", "")
                        if cnpj:
                            valor_por_cnpj[cnpj] = (
                                valor_por_cnpj.get(cnpj, Decimal("0")) + valor_pago
                            )

                if emenda_matched and emenda["id"] not in emendas_com_match:
                    emendas_com_match.add(emenda["id"])
                    valor_total += valor_pago

            if links:
                self.db.upsert(
                    "emenda_contrato_link",
                    links,
                    on_conflict="emenda_id,contrato_id",
                )

            top = sorted(valor_por_cnpj.items(), key=lambda x: x[1], reverse=True)[:10]
            result.update({
                "emendas_cruzadas": len(emendas_com_match),
                "contratos_vinculados": len(contratos_ids),
                "valor_total_cruzado": str(valor_total),
                "top_fornecedores": [
                    {"cnpj": cnpj, "valor_total": str(v)} for cnpj, v in top
                ],
            })
            return result

        except Exception as exc:
            status = "erro"
            error = str(exc)
            self.logger.exception("cruzamento_failed", ano=ano, error=error)
            raise
        finally:
            self.db.insert_log({
                "fonte": self.source,
                "endpoint": "emenda-contrato",
                "parametros": {"ano": ano},
                "registros_coletados": result.get("emendas_com_pagamento", 0),
                "registros_inseridos": result.get("emendas_cruzadas", 0),
                "registros_atualizados": 0,
                "status": status,
                "erro": error,
                "duracao_segundos": round(time.monotonic() - started_at, 2),
            })

    def _load_emendas_pagas(self, ano: int) -> list[dict[str, Any]]:
        rows = self.db.select(
            "emendas",
            columns="id,valor_pago,raw_data",
            filters={"ano": ano},
        )
        return [
            r for r in rows
            if (v := self._to_decimal(r.get("valor_pago"))) and v > 0
        ]

    def _load_contratos(self) -> list[dict[str, Any]]:
        return self.db.select(
            "contratos",
            columns="id,fornecedor_cnpj,data_inicio,data_fim,objeto",
        )

    @staticmethod
    def _index_por_cnpj(
        contratos: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for contrato in contratos:
            cnpj = contrato.get("fornecedor_cnpj")
            if cnpj:
                index.setdefault(cnpj, []).append(contrato)
        return index

    @staticmethod
    def _vigencia_compativel(contrato: dict[str, Any], ano: int) -> bool:
        """Return True if the contract was active at any point during the year."""
        inicio_ano = f"{ano}-01-01"
        fim_ano = f"{ano}-12-31"
        data_inicio = contrato.get("data_inicio")
        data_fim = contrato.get("data_fim")
        if data_inicio and data_inicio > fim_ano:
            return False
        if data_fim and data_fim < inicio_ano:
            return False
        return True

    @staticmethod
    def _extract_cnpjs(raw_data: Any) -> set[str]:
        """Extract CNPJ values from an emenda raw_data dict."""
        if not isinstance(raw_data, dict):
            return set()
        cnpjs: set[str] = set()

        for field in ("cnpjFornecedor", "cnpjFavorecido", "cpfCnpjFavorecido", "cnpj"):
            val = raw_data.get(field)
            if val:
                normalized = normalize_cnpj(val)
                if normalized and len(normalized) == 14:
                    cnpjs.add(normalized)

        for key in ("favorecido", "fornecedor", "beneficiario", "credor"):
            nested = raw_data.get(key)
            if isinstance(nested, dict):
                for field in ("cnpj", "cpfCnpj", "cpfCnpjFavorecido"):
                    val = nested.get(field)
                    if val:
                        normalized = normalize_cnpj(val)
                        if normalized and len(normalized) == 14:
                            cnpjs.add(normalized)

        return cnpjs

    @staticmethod
    def _keywords_from_funcao(funcao: Any, subfuncao: Any = None) -> set[str]:
        """Extract normalized keywords from funcao/subfuncao fields."""
        stop = {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "para", "com"}
        words: set[str] = set()
        for text in (funcao, subfuncao):
            if not isinstance(text, str):
                continue
            for word in text.lower().split():
                word = word.strip(".,;:()")
                if len(word) >= 4 and word not in stop:
                    words.add(word)
        return words

    @staticmethod
    def _objeto_contem_keywords(objeto: Any, keywords: set[str]) -> bool:
        """Return True if the contract objeto contains at least 2 of the keywords."""
        if not isinstance(objeto, str) or not keywords:
            return False
        objeto_lower = objeto.lower()
        hits = sum(1 for kw in keywords if kw in objeto_lower)
        return hits >= 2

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
