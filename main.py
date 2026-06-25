from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from collectors.camara import CamaraParlamentaresCollector
from collectors.senado import SenadoParlamentaresCollector
from collectors.transparencia import TransparenciaCollector
from config import settings
from crosslinkers.emenda_contrato import EmendaContratoLinker
from crosslinkers.parlamentar_resolver import ParlamentarResolver
from db import Database
from utils.logging_config import configure_logging


app = typer.Typer(help="Pipeline Transparencia Brasil")
coletar_app = typer.Typer(help="Comandos de coleta")
cruzar_app = typer.Typer(help="Comandos de cruzamento")
app.add_typer(coletar_app, name="coletar")
app.add_typer(cruzar_app, name="cruzar")


async def _collect_parlamentares(source: str) -> dict[str, int]:
    db = Database()
    totals = {"camara": 0, "senado": 0}

    if source in {"all", "camara"}:
        async with CamaraParlamentaresCollector(db=db) as collector:
            totals["camara"] = await collector.run_logged("deputados")

    if source in {"all", "senado"}:
        async with SenadoParlamentaresCollector(db=db) as collector:
            totals["senado"] = await collector.run_logged("senador/lista/atual")

    return totals


async def _collect_emendas(ano: int) -> dict[str, int]:
    db = Database()
    async with TransparenciaCollector(db=db) as collector:
        return await collector.coletar_emendas(ano=ano)


async def _collect_contratos(ano: int) -> dict[str, int]:
    db = Database()
    async with TransparenciaCollector(db=db) as collector:
        return await collector.coletar_contratos(ano=ano)


async def _collect_licitacoes(ano: int) -> dict[str, int]:
    db = Database()
    async with TransparenciaCollector(db=db) as collector:
        return await collector.coletar_licitacoes(ano=ano)


async def _collect_cota(ano: int, deputado_id: int | None) -> dict[str, int]:
    db = Database()
    async with CamaraParlamentaresCollector(db=db) as collector:
        if deputado_id is not None:
            return await collector.coletar_cota_parlamentar(deputado_id=deputado_id, ano=ano)
        return await collector.coletar_todas_cotas(ano=ano)


@coletar_app.command("parlamentares")
def coletar_parlamentares(
    fonte: Annotated[
        str,
        typer.Option(
            "--fonte",
            "-f",
            help="Fonte a coletar: all, camara ou senado.",
        ),
    ] = "all",
) -> None:
    """Collect deputies and senators into transparencia.parlamentares."""
    configure_logging(settings.log_level)
    source = fonte.lower()
    if source not in {"all", "camara", "senado"}:
        raise typer.BadParameter("fonte deve ser all, camara ou senado")

    totals = asyncio.run(_collect_parlamentares(source))
    typer.echo(f"Camara: {totals['camara']} registros coletados")
    typer.echo(f"Senado: {totals['senado']} registros coletados")


@coletar_app.command("all")
def coletar_all() -> None:
    """Run currently implemented collectors."""
    coletar_parlamentares(fonte="all")


@coletar_app.command("emendas")
def coletar_emendas(
    ano: Annotated[int, typer.Option("--ano", "-a", help="Ano das emendas.")]
) -> None:
    """Collect parliamentary amendments from Portal da Transparencia."""
    configure_logging(settings.log_level)
    result = asyncio.run(_collect_emendas(ano=ano))
    typer.echo(
        "Emendas {ano}: coletadas={coletados}, upserts={inseridos}, "
        "vinculadas={vinculados}, pendentes={pendentes}".format(ano=ano, **result)
    )


@coletar_app.command("contratos")
def coletar_contratos(
    ano: Annotated[int, typer.Option("--ano", "-a", help="Ano dos contratos.")],
) -> None:
    """Collect government contracts from Portal da Transparencia."""
    configure_logging(settings.log_level)
    result = asyncio.run(_collect_contratos(ano=ano))
    typer.echo(
        "Contratos {ano}: coletados={coletados}, upserts={inseridos}".format(
            ano=ano, **result
        )
    )


@coletar_app.command("licitacoes")
def coletar_licitacoes(
    ano: Annotated[int, typer.Option("--ano", "-a", help="Ano das licitacoes.")],
) -> None:
    """Collect public tenders from Portal da Transparencia."""
    configure_logging(settings.log_level)
    result = asyncio.run(_collect_licitacoes(ano=ano))
    typer.echo(
        "Licitacoes {ano}: coletados={coletados}, upserts={inseridos}".format(
            ano=ano, **result
        )
    )


@coletar_app.command("cota")
def coletar_cota(
    ano: Annotated[int, typer.Option("--ano", "-a", help="Ano das despesas CEAP.")],
    deputado_id: Annotated[
        int | None,
        typer.Option("--deputado-id", help="ID do deputado na API da Camara."),
    ] = None,
) -> None:
    """Collect CEAP expenses for one deputy or all deputies in the database."""
    configure_logging(settings.log_level)
    result = asyncio.run(_collect_cota(ano=ano, deputado_id=deputado_id))
    if deputado_id is not None:
        typer.echo(
            "Cota deputado {deputado_id}/{ano}: coletadas={coletados}, upserts={inseridos}".format(
                deputado_id=deputado_id,
                ano=ano,
                **result,
            )
        )
        return

    typer.echo(
        "Cotas {ano}: deputados={deputados_processados}, coletadas={registros_coletados}, "
        "upserts={registros_inseridos}, ultimo_deputado_id={ultimo_deputado_id}".format(
            ano=ano,
            **result,
        )
    )


@app.command("status")
def status(
    fonte: Annotated[
        str | None,
        typer.Option("--fonte", "-f", help="Filtrar por fonte: camara, senado etc."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=100)] = 10,
) -> None:
    """Show latest collection logs from Supabase."""
    db = Database()
    logs = db.latest_logs(fonte=fonte, limit=limit)
    if not logs:
        typer.echo("Nenhum log encontrado.")
        return

    for row in logs:
        typer.echo(
            "{executado_em} | {fonte} | {endpoint} | {status} | coletados={registros_coletados}".format(
                **row
            )
        )


@cruzar_app.command("emenda-contrato")
def cruzar_emenda_contrato(
    ano: Annotated[int, typer.Option("--ano", "-a", help="Ano das emendas.")],
) -> None:
    """Cross-reference paid emendas with contracts by CNPJ."""
    configure_logging(settings.log_level)
    result = EmendaContratoLinker().cruzar(ano=ano)
    typer.echo(
        "Cruzamento {ano}: {emendas_cruzadas} emendas cruzadas com "
        "{contratos_vinculados} contratos, valor total R$ {valor_total_cruzado}".format(
            ano=ano, **result
        )
    )
    if result["top_fornecedores"]:
        typer.echo("Top fornecedores:")
        for rank, item in enumerate(result["top_fornecedores"], start=1):
            typer.echo(
                "  {rank}. CNPJ {cnpj} — R$ {valor_total}".format(rank=rank, **item)
            )


@cruzar_app.command("resolver-parlamentares")
def resolver_parlamentares() -> None:
    """Resolve pending emenda to parlamentar links."""
    configure_logging(settings.log_level)
    result = ParlamentarResolver().resolver()
    typer.echo(
        "Resolver parlamentares: pendentes_iniciais={pendentes_iniciais}, "
        "resolvidos={resolvidos}, ambiguos={ambiguos}, pendentes={pendentes}".format(
            **result
        )
    )


if __name__ == "__main__":
    app()
