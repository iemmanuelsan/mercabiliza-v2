"""Aba 5 — CRM de leads."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from ..state import obter_repositorio


@st.cache_data(show_spinner=False)
def _to_excel(chave: str, _df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _df.to_excel(writer, index=False, sheet_name="Leads_CRM")
    return buffer.getvalue()


def render() -> None:
    st.header("🗃️ CRM contábil — base de prospects")

    st.warning(
        "⚠️ **Persistência efêmera:** no Streamlit Community Cloud o banco SQLite é "
        "apagado a cada reboot ou redeploy. Exporte o Excel regularmente ou migre "
        "para um Postgres gerenciado antes de usar isto como CRM de verdade.",
        icon="⚠️",
    )

    try:
        df = obter_repositorio().listar()
    except Exception as exc:
        st.error(f"❌ Não foi possível ler o banco de leads: {exc}")
        return

    if df.empty:
        st.info("Nenhum lead registrado. Faça consultas nas abas 1 ou 3 para "
                "alimentar a base.")
        return

    # ---------------- Filtros ------------------------------------------- #
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ufs = sorted(u for u in df["uf"].dropna().unique() if u)
        filtro_uf = st.multiselect("UF", ufs)
    with col_b:
        regimes = sorted(r for r in df["regime"].dropna().unique() if r)
        filtro_regime = st.multiselect("Regime", regimes)
    with col_c:
        busca = st.text_input("Buscar por razão social ou CNPJ")

    filtrado = df
    if filtro_uf:
        filtrado = filtrado[filtrado["uf"].isin(filtro_uf)]
    if filtro_regime:
        filtrado = filtrado[filtrado["regime"].isin(filtro_regime)]
    if busca:
        alvo = busca.strip().lower()
        filtrado = filtrado[
            filtrado["razao_social"].str.lower().str.contains(alvo, na=False)
            | filtrado["cnpj"].str.lower().str.contains(alvo, na=False)
        ]

    # ---------------- Indicadores ---------------------------------------- #
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total na base", len(df))
    m2.metric("Filtrados", len(filtrado))
    m3.metric("MEIs", int((filtrado["regime"] == "MEI").sum()))
    m4.metric("Estados", filtrado["uf"].nunique())

    st.dataframe(filtrado, hide_index=True, width="stretch")

    if not filtrado.empty:
        st.bar_chart(filtrado["uf"].value_counts(), x_label="UF",
                     y_label="Leads", horizontal=True)

    st.download_button(
        f"📥 Exportar {len(filtrado)} lead(s) em Excel",
        data=_to_excel(f"{len(filtrado)}-{hash(tuple(filtrado['cnpj']))}", filtrado),
        file_name=f"crm_leads_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    with st.expander("🗑️ Remover um lead (LGPD — direito de eliminação)"):
        alvo = st.selectbox("CNPJ", filtrado["cnpj"].tolist(), key="rm_lead")
        if st.button("Remover definitivamente"):
            if obter_repositorio().remover(alvo):
                st.success(f"Lead {alvo} removido.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.warning("Lead não encontrado.")
