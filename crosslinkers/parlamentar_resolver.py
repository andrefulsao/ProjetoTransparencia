from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Any

import structlog

from db import Database
from utils.normalization import normalize_cpf, normalize_name, only_digits


class ParlamentarResolver:
    """Resolve pending emendas.parlamentar_id from CPF and name matches."""

    def __init__(self, db: Database | None = None, threshold: float = 0.85) -> None:
        self.db = db or Database()
        self.threshold = threshold
        self.logger = structlog.get_logger(self.__class__.__name__)

    def resolver(self) -> dict[str, int]:
        """Resolve all emendas without parlamentar_id and return counters."""
        if not self.db.enabled:
            raise RuntimeError("Supabase precisa estar configurado para resolver parlamentares.")

        started_at = time.monotonic()
        status = "sucesso"
        error = None
        counters = {
            "pendentes_iniciais": 0,
            "resolvidos": 0,
            "ambiguos": 0,
            "pendentes": 0,
        }

        try:
            emendas = self.db.select(
                "emendas",
                columns="id,autor,raw_data",
                is_null=["parlamentar_id"],
            )
            parlamentares = self.db.select(
                "parlamentares",
                columns="id,cpf,nome_civil,nome_parlamentar,uf,partido",
            )
            counters["pendentes_iniciais"] = len(emendas)

            for emenda in emendas:
                match = self._match_emenda(emenda, parlamentares)
                if match["status"] == "resolvido":
                    self.db.update_by_id(
                        "emendas",
                        emenda["id"],
                        {"parlamentar_id": match["parlamentar_id"]},
                    )
                    counters["resolvidos"] += 1
                elif match["status"] == "ambiguo":
                    counters["ambiguos"] += 1
                    self._log_ambiguous_match(emenda, match["candidatos"])

            counters["pendentes"] = (
                counters["pendentes_iniciais"]
                - counters["resolvidos"]
                - counters["ambiguos"]
            )
            return counters
        except Exception as exc:
            status = "erro"
            error = str(exc)
            self.logger.exception("resolver_failed", error=error)
            raise
        finally:
            self.db.insert_log(
                {
                    "fonte": "parlamentar_resolver",
                    "endpoint": "resolver-parlamentares",
                    "parametros": {
                        "threshold": self.threshold,
                        **counters,
                    },
                    "registros_coletados": counters["pendentes_iniciais"],
                    "registros_inseridos": 0,
                    "registros_atualizados": counters["resolvidos"],
                    "status": status,
                    "erro": error,
                    "duracao_segundos": round(time.monotonic() - started_at, 2),
                }
            )

    def _match_emenda(
        self,
        emenda: dict[str, Any],
        parlamentares: list[dict[str, Any]],
    ) -> dict[str, Any]:
        author = emenda.get("autor") or ""
        author_cpf = self._extract_cpf(author)
        if author_cpf:
            cpf_matches = [p for p in parlamentares if p.get("cpf") == author_cpf]
            if len(cpf_matches) == 1:
                return {"status": "resolvido", "parlamentar_id": cpf_matches[0]["id"]}
            if len(cpf_matches) > 1:
                return {"status": "ambiguo", "candidatos": cpf_matches}

        normalized_author = normalize_name(author)
        if not normalized_author:
            return {"status": "pendente"}

        exact_matches = [
            p for p in parlamentares if normalized_author in self._candidate_names(p)
        ]
        if len(exact_matches) == 1:
            return {"status": "resolvido", "parlamentar_id": exact_matches[0]["id"]}
        if len(exact_matches) > 1:
            return {"status": "ambiguo", "candidatos": exact_matches}

        scored = []
        for parlamentar in parlamentares:
            best_score = max(
                (
                    SequenceMatcher(None, normalized_author, candidate_name).ratio()
                    for candidate_name in self._candidate_names(parlamentar)
                ),
                default=0,
            )
            if best_score >= self.threshold:
                scored.append((best_score, parlamentar))

        scored.sort(key=lambda item: item[0], reverse=True)
        if len(scored) == 1:
            return {"status": "resolvido", "parlamentar_id": scored[0][1]["id"]}
        if len(scored) > 1:
            return {
                "status": "ambiguo",
                "candidatos": [
                    {**candidate, "score": round(score, 4)}
                    for score, candidate in scored
                ],
            }
        return {"status": "pendente"}

    def _candidate_names(self, parlamentar: dict[str, Any]) -> set[str]:
        names = {
            normalize_name(parlamentar.get("nome_civil")),
            normalize_name(parlamentar.get("nome_parlamentar")),
        }
        return {name for name in names if name}

    def _log_ambiguous_match(
        self,
        emenda: dict[str, Any],
        candidatos: list[dict[str, Any]],
    ) -> None:
        compact_candidates = [
            {
                "id": item.get("id"),
                "nome_civil": item.get("nome_civil"),
                "nome_parlamentar": item.get("nome_parlamentar"),
                "uf": item.get("uf"),
                "partido": item.get("partido"),
                "score": item.get("score"),
            }
            for item in candidatos
        ]
        self.logger.warning(
            "ambiguous_parlamentar_match",
            emenda_id=emenda.get("id"),
            autor=emenda.get("autor"),
            candidatos=compact_candidates,
        )
        self.db.insert_log(
            {
                "fonte": "parlamentar_resolver",
                "endpoint": "resolver-parlamentares/ambiguo",
                "parametros": {
                    "emenda_id": emenda.get("id"),
                    "autor": emenda.get("autor"),
                    "candidatos": compact_candidates,
                },
                "registros_coletados": 1,
                "registros_inseridos": 0,
                "registros_atualizados": 0,
                "status": "parcial",
                "erro": "match_ambiguo",
                "duracao_segundos": 0,
            }
        )

    @staticmethod
    def _extract_cpf(value: object | None) -> str | None:
        digits = only_digits(value)
        if not digits or len(digits) < 11:
            return None
        return normalize_cpf(digits[-11:])
