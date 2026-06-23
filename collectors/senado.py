from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from collectors.base import BaseCollector
from config import settings


class SenadoParlamentaresCollector(BaseCollector):
    """Collect current senators from Senado Federal Dados Abertos."""

    source = "senado"
    base_url = "https://legis.senado.leg.br/dadosabertos/"

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("rate_limit_per_minute", settings.rate_limit_senado)
        kwargs.setdefault("timeout_seconds", settings.request_timeout_seconds)
        super().__init__(*args, **kwargs)

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        headers["Accept"] = "application/json"
        return headers

    async def collect(self) -> list[dict[str, Any]]:
        payload = await self.request_json("senador/lista/atual")
        senators = self._extract_senators(payload)
        return [self._normalize_senator(item) for item in senators]

    def _extract_senators(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        root = payload.get("ListaParlamentarEmExercicio", payload)
        parlamentares = root.get("Parlamentares", root)
        senador = parlamentares.get("Parlamentar", [])
        if isinstance(senador, dict):
            return [senador]
        return senador or []

    def _normalize_senator(self, item: dict[str, Any]) -> dict[str, Any]:
        identity = item.get("IdentificacaoParlamentar", item)
        mandate = item.get("Mandato", {})
        code = self._to_int(identity.get("CodigoParlamentar"))
        return {
            "nome_civil": identity.get("NomeCompletoParlamentar") or identity.get("NomeParlamentar"),
            "nome_parlamentar": identity.get("NomeParlamentar"),
            "cpf": None,
            "casa": "senado",
            "partido": identity.get("SiglaPartidoParlamentar"),
            "uf": identity.get("UfParlamentar") or mandate.get("UfParlamentar"),
            "legislatura": self._to_int(mandate.get("CodigoLegislatura")),
            "id_camara": None,
            "codigo_senado": code,
            "foto_url": identity.get("UrlFotoParlamentar"),
            "email": identity.get("EmailParlamentar"),
            "situacao": item.get("DescricaoParticipacao") or "Em exercicio",
            "raw_data": item,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _to_int(value: object | None) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def persist(self, records: list[dict[str, Any]]) -> dict[str, int]:
        return self.upsert_rows("parlamentares", records, on_conflict="codigo_senado")
