"""Aba 3 — Análise em lote via upload de planilha."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from ...config import settings
from ...core.cnpj import CNPJInvalidoError, validar
from ..components import renderizar_dossie
from ..state import (
    CHAVE_LOTE,
    consultar_dossie,
    excel_bytes,
    obter_repositorio,
    pdf_dossie_bytes,
)

logger = logging.getLogger(__name__)


def _extrair_cnpjs(df: pd.DataFrame) -> tuple[list[str], list[tuple[str, str]]]:
    colunas = [c for c in df.columns if "CNPJ" in str(c).upper()]
    if not colunas:
        raise ValueError("A planilha precisa conter uma coluna chamada 'CNPJ'.")

    validos: list[str] = []
    invalidos: list[tuple[str, str]] = []
    vistos: set[str] = set()

    for bruto in df[colunas[0]].dropna().astype(str):
        try:
            cnpj = validar(bruto)
        except CNPJInvalidoError as exc:
            invalidos.append((bruto, str(exc)))
            continue
        if cnpj not in vistos:          # [MELHORIA] deduplicação
            vistos.add(cnpj)
            validos.append(cnpj)
    return validos, invalidos


def _processar(cnpjs: list[str]) -> list:
    """Processa o lote com concorrência limitada e progresso real.

    [CORRIGIDO] O loop original era estritamente sequencial e dividia por
    ``len(cnpjs)`` sem checar lista vazia (ZeroDivisionError). Também não havia
    teto de itens: uma planilha com 5 mil linhas disparava 15 mil requisições e
    derrubava o app por rate limit.
    """
    total = len(cnpjs)
    if total == 0:
        return []

    barra = st.progress(0.0, text="Iniciando…")
    resultados: list = []
    falhas: list[str] = []

    with ThreadPoolExecutor(
        max_workers=settings.http.max_workers_lote, thread_name_prefix="lote"
    ) as pool:
        futuros = {pool.submit(consultar_dossie, c, 0.0): c for c in cnpjs}
        for concluidos, futuro in enumerate(as_completed(futuros), 1):
            cnpj = futuros[futuro]
            try:
                empresa = futuro.result()
            except Exception as exc:
                logger.exception("Falha ao processar %s", cnpj)
                falhas.append(f"{cnpj}: {exc}")
                empresa = None
            if empresa:
                resultados.append(empresa)
            else:
                falhas.append(f"{cnpj}: não localizado nas bases públicas")
            barra.progress(concluidos / total,
                           text=f"{concluidos}/{total} processados · "
                                f"{len(resultados)} encontrados")

    barra.empty()
    if falhas:
        with st.expander(f"⚠️ {len(falhas)} CNPJ(s) sem retorno"):
            st.code("\n".join(falhas))
    return resultados


def render() -> None:
    st.header("📊 Análise em lote")
    st.caption(
        f"Envie um `.xlsx` ou `.csv` com uma coluna **CNPJ**. Limite de "
        f"{settings.limites.max_cnpjs_por_lote} CNPJs por execução, processados "
        f"{settings.http.max_workers_lote} a {settings.http.max_workers_lote} para "
        "respeitar o rate limit das APIs públicas."
    )

    arquivo = st.file_uploader("Planilha de CNPJs", type=["xlsx", "csv"])
    if arquivo is not None:
        try:
            df = (pd.read_csv(arquivo) if arquivo.name.lower().endswith(".csv")
                  else pd.read_excel(arquivo))
        except Exception as exc:
            st.error(f"❌ Não foi possível ler a planilha: {exc}")
            return

        try:
            validos, invalidos = _extrair_cnpjs(df)
        except ValueError as exc:
            st.error(f"❌ {exc}")
            st.caption(f"Colunas encontradas: {', '.join(map(str, df.columns))}")
            return

        col_a, col_b = st.columns(2)
        col_a.metric("CNPJs válidos e únicos", len(validos))
        col_b.metric("Descartados", len(invalidos))

        if invalidos:
            with st.expander("Ver linhas descartadas"):
                st.dataframe(pd.DataFrame(invalidos, columns=["Valor", "Motivo"]),
                             hide_index=True, width="stretch")

        if not validos:
            st.warning("Nenhum CNPJ válido na planilha.")
            return

        teto = settings.limites.max_cnpjs_por_lote
        if len(validos) > teto:
            st.warning(f"Serão processados apenas os primeiros {teto} CNPJs.")
            validos = validos[:teto]

        if st.button(f"🚀 Processar {len(validos)} CNPJs", type="primary"):
            with st.spinner("Consultando as bases públicas…"):
                empresas = _processar(validos)
            st.session_state[CHAVE_LOTE] = empresas
            if empresas:
                try:
                    gravados = obter_repositorio().salvar_varios(empresas)
                    st.success(f"✅ {len(empresas)} empresa(s) processada(s) · "
                               f"{gravados} gravada(s) no CRM.")
                except Exception as exc:
                    st.warning(f"Processado, mas a gravação no CRM falhou: {exc}")
            else:
                st.error("Nenhuma empresa retornou dados.")

    lote = st.session_state[CHAVE_LOTE]
    if not lote:
        return

    st.divider()
    st.subheader(f"🔍 {len(lote)} empresa(s) no lote")

    resumo = pd.DataFrame([e.to_row() for e in lote])
    st.dataframe(resumo, hide_index=True, width="stretch")

    rotulos = {f"{e.razao_social} — {e.cnpj}": e for e in lote}
    empresa = rotulos[st.selectbox("Examinar em detalhe:", list(rotulos))]
    renderizar_dossie(empresa)

    st.divider()
    col_x, col_p = st.columns(2)
    with col_x:
        st.download_button(
            f"📊 Excel consolidado ({len(lote)} empresas · 4 abas)",
            data=excel_bytes("|".join(sorted(e.cnpj for e in lote)), tuple(lote)),
            file_name=f"dossie_lote_{len(lote)}_empresas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with col_p:
        st.download_button(
            "📄 PDF da empresa selecionada",
            data=pdf_dossie_bytes(empresa.cnpj, empresa),
            file_name=f"dossie_{empresa.cnpj}.pdf",
            mime="application/pdf", type="primary", width="stretch",
        )
