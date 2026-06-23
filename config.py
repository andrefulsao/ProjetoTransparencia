from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    supabase_url: str | None = os.getenv("SUPABASE_URL")
    supabase_key: str | None = os.getenv("SUPABASE_KEY")
    transparencia_api_key: str | None = os.getenv("TRANSPARENCIA_API_KEY")
    dados_gov_token: str | None = os.getenv("DADOS_GOV_TOKEN")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    coleta_ano_inicio: int = _int_env("COLETA_ANO_INICIO", 2023)
    coleta_ano_fim: int = _int_env("COLETA_ANO_FIM", 2025)
    rate_limit_transparencia: int = _int_env("RATE_LIMIT_TRANSPARENCIA", 80)
    rate_limit_camara: int = _int_env("RATE_LIMIT_CAMARA", 25)
    rate_limit_senado: int = _int_env("RATE_LIMIT_SENADO", 25)
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


settings = Settings()
