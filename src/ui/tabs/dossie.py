"""Aba 1 — Dossiê individual completo."""

from __future__ import annotations

import streamlit as st

from ...config import settings
from ...core.cnpj import CNPJInvalidoError, eh_alfanumerico, validar
from ...core.formatters import moeda
from ...core.tributario import calcular_honorarios
from ..components import renderizar_dossie
from ..state import (
    CHAVE_HISTORICO,
    consultar_dossie,
    excel_bytes,
    obter_repositorio,
    pdf_dossie_bytes,
    registrar_no_historico,
)


def _buscar(cnpj_bruto: str, rbt12: float) -> None:
    """Callback do formulário — roda ANTES do rerun, então o resultado já
    aparece na primeira renderização."""
    try:
        cnpj = validar(cnpj_bruto)
    except CNPJInvalidoError as exc:
        st.session_state["erro_dossie"] = str(exc)
        return

    st.session_state["erro_dossie"] = None
    with st.spinner("Consultando BrasilAPI, CNPJ.ws, ReceitaWS e IBGE em paralelo…"):
        empresa = consultar_dossie(cnpj, rbt12)

    if empresa is None:
        st.session_state["erro_dossie"] = (
            "CNPJ não localizado nas bases públicas, ou os três provedores estão "
            "indisponíveis/limitando requisições. Tente novamente em alguns minutos."
        )
        return

    registrar_no_historico(empresa)
    try:
        obter_repositorio().salvar(empresa)
        st.session_state["ok_dossie"] = "Dossiê gerado e lead gravado no CRM."
    except Exception as exc:
        st.session_state["ok_dossie"] = (
            f"Dossiê gerado, mas a gravação no CRM falhou: {exc}"
        )


def render() -> None:
    st.header("🔍 Dossiê individual completo")

    with st.form("form_dossie"):
        col_cnpj, col_fat = st.columns([2, 1])
        with col_cnpj:
            cnpj_input = st.text_input(
                "CNPJ do cliente",
                placeholder="00.000.000/0001-91 ou 12.ABC.345/01DE-35",
                help="Aceita o formato numérico tradicional e o novo CNPJ "
                     "alfanumérico (vigente desde julho/2026).",
            )
        with col_fat:
            rbt12 = st.number_input(
                "Faturamento dos últimos 12 meses (RBT12)",
                min_value=0.0, step=10_000.0, value=0.0,
                help="Opcional. Informando o RBT12, a alíquota exibida passa a ser "
                     "a efetiva da faixa da empresa, e não a da 1ª faixa.",
            )
        enviado = st.form_submit_button("Gerar dossiê inteligente", type="primary",
                                        width="stretch")

    if enviado:
        _buscar(cnpj_input, rbt12)

    if erro := st.session_state.get("erro_dossie"):
        st.error(f"❌ {erro}")
    if ok := st.session_state.pop("ok_dossie", None):
        st.success(f"✅ {ok}")

    historico = st.session_state[CHAVE_HISTORICO]
    if not historico:
        st.info("Nenhuma consulta nesta sessão. Informe um CNPJ acima para começar.")
        return

    # [MELHORIA] O original guardava o histórico mas só exibia ``historico[0]``.
    rotulos = {f"{e.razao_social} — {e.cnpj}": e for e in historico}
    escolha = st.selectbox("Empresa consultada nesta sessão:", list(rotulos),
                           key="sel_hist")
    empresa = rotulos[escolha]

    if eh_alfanumerico(empresa.cnpj):
        st.info("🆕 Este é um CNPJ alfanumérico. Confirme se os sistemas de "
                "emissão fiscal do cliente já foram atualizados para o novo layout.")

    renderizar_dossie(empresa)

    st.divider()
    st.subheader("📥 Exportações")
    col_xls, col_pdf = st.columns(2)
    with col_xls:
        st.download_button(
            f"📊 Excel — {len(historico)} empresa(s) desta sessão",
            data=excel_bytes(
                "|".join(sorted(e.cnpj for e in historico)), tuple(historico)),
            file_name=f"dossie_sessao_{len(historico)}_empresas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with col_pdf:
        st.download_button(
            "📄 PDF — dossiê da empresa selecionada",
            data=pdf_dossie_bytes(empresa.cnpj, empresa),
            file_name=f"dossie_{empresa.cnpj}.pdf",
            mime="application/pdf", type="primary", width="stretch",
        )

    st.divider()
    _bloco_proposta(empresa)


@st.fragment
def _bloco_proposta(empresa) -> None:
    """``@st.fragment`` isola este bloco: mexer nos controles de preço
    re-renderiza SÓ esta seção, sem reexecutar as abas de consulta."""
    from ...exporters.pdf_dossie import gerar_proposta

    precos = settings.precos
    st.subheader("📄 Proposta comercial personalizada")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Serviços pontuais**")
        inc_desenq = st.checkbox(
            f"Desenquadramento de MEI ({moeda(precos.desenquadramento_mei)})",
            value=empresa.optante_mei)
        inc_abertura = st.checkbox(
            f"Constituição / abertura ({moeda(precos.abertura_empresa)})")
    with col_b:
        st.markdown("**Serviços recorrentes**")
        qtd_cnpjs = st.number_input("Unidades / CNPJs (matriz + filiais)",
                                    min_value=1, max_value=50, value=1)
        qtd_pessoas = st.number_input("Vínculos (funcionários + pró-labore)",
                                      min_value=0, max_value=200, value=1)

    pontuais = []
    if inc_desenq:
        pontuais.append(("Desenquadramento de MEI", precos.desenquadramento_mei))
    if inc_abertura:
        pontuais.append(("Constituição / abertura de empresa", precos.abertura_empresa))

    honorarios = calcular_honorarios(qtd_cnpjs, qtd_pessoas, pontuais, precos)

    m1, m2, m3 = st.columns(3)
    m1.metric("Mensalidade recorrente", moeda(honorarios.mensal))
    m2.metric("Serviços pontuais", moeda(honorarios.total_pontual))
    m3.metric("1º mês", moeda(honorarios.mensal + honorarios.total_pontual))
    st.caption(
        f"Base {moeda(honorarios.base)} + filiais {moeda(honorarios.adicional_cnpjs)} "
        f"+ DP {moeda(honorarios.adicional_dp)} ({honorarios.blocos_dp} bloco(s) de "
        f"até {precos.pessoas_por_bloco_dp} pessoas)"
    )

    # Gerado sob demanda: o PDF só é montado quando o usuário clica.
    if st.button("Montar proposta em PDF", width="stretch"):
        st.session_state["proposta_pdf"] = gerar_proposta(
            empresa, honorarios, incluir_dp=qtd_pessoas > 0)

    if pdf := st.session_state.get("proposta_pdf"):
        st.download_button(
            "📄 Baixar proposta comercial (PDF)", data=pdf,
            file_name=f"proposta_mercabiliza_{empresa.cnpj}.pdf",
            mime="application/pdf", type="primary", width="stretch",
        )
