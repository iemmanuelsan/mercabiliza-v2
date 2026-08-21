"""Mercabiliza — Inteligência Tributária & Onboarding Contábil.

Ponto de entrada do Streamlit. Deve permanecer fino: a única
responsabilidade daqui é configurar a página e montar a navegação.
"""

from __future__ import annotations

import logging

import streamlit as st

from src.ui.auth import botao_sair, exigir_login
from src.ui.state import inicializar_estado
from src.ui.tabs import comparador, contratos, crm, dossie, lote, mei

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

st.set_page_config(
    page_title="Mercabiliza | Inteligência Tributária",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "about": "Mercabiliza — onboarding contábil para minimercados autônomos.",
    },
)


def _sidebar() -> None:
    with st.sidebar:
        st.title("🛒 Mercabiliza")
        st.caption("Inteligência tributária para minimercados autônomos")
        st.divider()

        st.markdown(
            "**Como usar**\n\n"
            "1. **Dossiê** — consulte um CNPJ e gere o relatório completo.\n"
            "2. **Regimes** — simule Simples × Presumido.\n"
            "3. **Lote** — processe uma planilha de prospects.\n"
            "4. **MEI** — estime o custo do desenquadramento.\n"
            "5. **Ficha & Contrato** — emita a ficha cadastral e a minuta.\n"
            "6. **CRM** — consulte e exporte a base de leads."
        )
        st.divider()

        st.markdown(
            "**⚖️ Escopo e limites**\n\n"
            "Os dados vêm de bases públicas de CNPJ. O app **não emite certidões** "
            "e **não substitui** a apuração oficial no PGDAS-D. Todos os valores "
            "são estimativas gerenciais."
        )
        st.divider()
        st.caption("v2.0 · dados: BrasilAPI · CNPJ.ws · ReceitaWS · IBGE · BACEN")


def main() -> None:
    # O gate vem ANTES de qualquer render: o app trata dado pessoal de
    # cliente, e a aba CRM expõe a base inteira. Sem isto, quem tiver o link
    # tem os dados.
    if not exigir_login():
        st.stop()

    inicializar_estado()
    _sidebar()
    botao_sair()

    st.title("Inteligência Tributária & Onboarding Contábil")
    st.caption(
        "Dossiê completo de CNPJ, PIS/COFINS monofásico, comparador de regimes, "
        "calculadora de MEI e CRM integrado."
    )

    aba_dossie, aba_regimes, aba_lote, aba_mei, aba_docs, aba_crm = st.tabs([
        "🔍 Dossiê individual",
        "⚔️ Comparador de regimes",
        "📊 Análise em lote",
        "🛠️ Calculadora MEI",
        "📝 Ficha & contrato",
        "🗃️ CRM & leads",
    ])

    with aba_dossie:
        dossie.render()
    with aba_regimes:
        comparador.render()
    with aba_lote:
        lote.render()
    with aba_mei:
        mei.render()
    with aba_docs:
        contratos.render()
    with aba_crm:
        crm.render()


if __name__ == "__main__":
    main()
