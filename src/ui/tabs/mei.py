"""Aba 4 — Transição e simulador de desenquadramento do MEI."""

from __future__ import annotations

import streamlit as st

from ...core.formatters import moeda
from ...core.tributario import LIMITE_MEI_MENSAL, diagnosticar_mei
from ..state import indicadores_bacen

AVISO = (
    "⚠️ **Aviso técnico:** os valores são uma **estimativa gerencial** com base nas "
    "informações declaradas e nas alíquotas da LC 123/2006. O valor exato a recolher "
    "é apurado no PGDAS-D após a transmissão da DASN-SIMEI e do PGDAS pela "
    "contabilidade habilitada. Multa e juros de mora seguem a legislação vigente na "
    "data do pagamento."
)


def render() -> None:
    st.header("🛠️ Desenquadramento do MEI — simulador retroativo")

    indicadores = indicadores_bacen()
    if indicadores.ao_vivo:
        st.caption(
            f"🏛️ BACEN em tempo real · Selic acumulada 12m: "
            f"`{indicadores.selic_acumulada_12m:.2f}%` · IPCA 12m: "
            f"`{indicadores.ipca_acumulado_12m:.2f}%`"
        )
    else:
        st.caption(
            f"🏛️ BACEN indisponível — usando valores de referência: Selic "
            f"`{indicadores.selic_acumulada_12m:.2f}%` · IPCA "
            f"`{indicadores.ipca_acumulado_12m:.2f}%`"
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        faturamento = st.number_input("Faturamento acumulado no ano (R$)",
                                      min_value=0.0, value=92_000.0, step=5_000.0)
    with col2:
        meses = st.slider("Meses de atividade no ano", 1, 12, 12)
    with col3:
        pct_mono = st.slider("Vendas monofásicas (%)", 0, 90, 55, step=5)

    diag = diagnosticar_mei(faturamento, meses,
                            indicadores.selic_acumulada_12m, pct_mono)

    st.divider()
    st.caption(
        f"Limite proporcional para {meses} mês(es): "
        f"**{moeda(diag.limite_proporcional)}** "
        f"({moeda(LIMITE_MEI_MENSAL)}/mês × {meses})"
    )

    if diag.excesso <= 0:
        st.success("🟢 **MEI regular** — faturamento dentro do limite proporcional.")
        folga = diag.limite_proporcional - faturamento
        st.progress(min(1.0, faturamento / diag.limite_proporcional),
                    text=f"Folga de {moeda(folga)} até o limite")
        st.caption(AVISO)
        return

    st.error(
        f"🔴 **Limite excedido em {moeda(diag.excesso)}** "
        f"({diag.pct_excesso:.1f}% acima do permitido)."
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Imposto retroativo estimado", moeda(diag.imposto_estimado))
    m1.caption("Apurado no Anexo I, líquido dos DAS-MEI já pagos")
    m2.metric("Multa e juros de mora", moeda(diag.encargos_estimados))
    m2.caption(f"Multa de mora (teto 20%) + Selic de {diag.selic_utilizada:.2f}% + 1%")
    m3.metric("Total estimado", moeda(diag.total_com_encargos))
    m3.caption("Guia PGDAS-D projetada")

    st.info(f"💡 **Parecer técnico**\n\n{diag.orientacao}")

    st.markdown("##### 💬 Como apresentar ao cliente")
    st.markdown(
        f"- O passivo estimado é de **{moeda(diag.total_com_encargos)}**; agir agora "
        "evita que os juros continuem correndo.\n"
        f"- O serviço de desenquadramento custa **{moeda(350)}** — uma fração do "
        "passivo em risco.\n"
        "- Com a segregação correta de monofásicos, parte relevante desse imposto "
        "pode ser legalmente reduzida na apuração."
    )
    st.caption(AVISO)
