"""Aba 2 — Comparador de regimes e economia com monofásicos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ...core.formatters import moeda, percentual
from ...core.tributario import LIMITE_SIMPLES_ANUAL, comparar_regimes


def render() -> None:
    st.header("⚔️ Comparador de regimes")
    st.caption(
        "Simulação gerencial para comércio varejista (Anexo I). Usa as tabelas "
        "progressivas da LC 123/2006 e a tributação real do Lucro Presumido — "
        "não substitui a apuração no PGDAS-D."
    )

    col1, col2 = st.columns(2)
    with col1:
        faturamento = st.number_input("Faturamento médio mensal (R$)",
                                      min_value=0.0, value=35_000.0, step=5_000.0)
    with col2:
        pct_mono = st.slider(
            "Participação de produtos monofásicos nas vendas (%)",
            min_value=0, max_value=90, value=55, step=5,
            help="Bebidas, higiene pessoal e itens com PIS/COFINS recolhido na "
                 "indústria. Essa parcela sai da base de PIS/COFINS.",
        )

    resultado = comparar_regimes(faturamento, pct_mono)
    if resultado.faturamento_anual <= 0:
        st.info("Informe um faturamento mensal para simular.")
        return

    if resultado.faturamento_anual > LIMITE_SIMPLES_ANUAL:
        st.error(
            f"🚨 Receita anual projetada de {moeda(resultado.faturamento_anual)} "
            f"excede o teto do Simples ({moeda(LIMITE_SIMPLES_ANUAL)}). "
            "A empresa está sujeita a exclusão — avaliar Lucro Presumido/Real."
        )

    st.divider()
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Simples com segregação",
                  f"{moeda(resultado.simples_otimizado / 12)} /mês",
                  delta=f"{moeda(resultado.simples_otimizado)} /ano",
                  delta_color="off")
        st.caption(f"Alíquota efetiva: "
                   f"{percentual(resultado.aliquota_simples_efetiva)}")
    with m2:
        st.metric("Lucro Presumido", f"{moeda(resultado.presumido / 12)} /mês",
                  delta=f"{moeda(resultado.presumido)} /ano", delta_color="off")
        st.caption(f"Carga efetiva: "
                   f"{percentual(resultado.aliquota_presumido_efetiva)} (sem ICMS)")
    with m3:
        st.metric("Diferença entre regimes",
                  f"{moeda(resultado.diferenca_anual / 12)} /mês",
                  delta=f"{moeda(resultado.diferenca_anual)} /ano")
        st.caption("A favor do regime vencedor")

    st.success(f"🏆 **Regime mais vantajoso:** {resultado.melhor_regime}")

    esq, dir_ = st.columns([1, 1])
    with esq:
        st.markdown("**Ganho com a segregação de monofásicos**")
        st.metric("Economia no DAS",
                  f"{moeda(resultado.economia_monofasico / 12)} /mês",
                  delta=f"{moeda(resultado.economia_monofasico)} /ano")
        st.info(
            f"💬 **Argumento comercial:** a economia de "
            f"{moeda(resultado.economia_monofasico / 12)}/mês na guia do DAS já "
            "cobre boa parte dos honorários — a contabilidade se paga."
        )
    with dir_:
        st.markdown("**Composição do Lucro Presumido (anual)**")
        st.dataframe(
            pd.DataFrame({
                "Tributo": list(resultado.detalhamento_presumido),
                "Valor": [moeda(v) for v in resultado.detalhamento_presumido.values()],
            }),
            hide_index=True, width="stretch",
        )
        st.caption("Não inclui ICMS, ISS nem a CPP sobre a folha.")

    with st.expander("ℹ️ Premissas do cálculo"):
        st.markdown(
            f"""
- **Simples Nacional:** alíquota efetiva = `(RBT12 × alíquota nominal − parcela a
  deduzir) ÷ RBT12`, Anexo I. Para {moeda(resultado.faturamento_anual)} de RBT12 a
  efetiva é **{percentual(resultado.aliquota_simples_efetiva)}**.
- **Segregação de monofásicos:** PIS+COFINS representam 15,50% da alíquota do
  Anexo I; a economia é proporcional à parcela monofásica da receita.
- **Lucro Presumido:** PIS 0,65% + COFINS 3,00% sobre a receita não monofásica;
  IRPJ 15% sobre presunção de 8% (+10% de adicional acima de R$ 240 mil de lucro
  presumido anual); CSLL 9% sobre presunção de 12%.
- **Fora do escopo:** ICMS (varia por UF e substituição tributária), ISS e
  contribuição patronal sobre a folha.
            """
        )
