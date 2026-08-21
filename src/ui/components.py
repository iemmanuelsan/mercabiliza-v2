"""Componentes reutilizáveis de interface."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..core.cnpj import formatar as formatar_cnpj
from ..core.formatters import moeda, url_google_maps, url_whatsapp
from ..core.models import Empresa
from .state import pdf_cartao_bytes

AVISO_COMPLIANCE = (
    "Os selos abaixo refletem **apenas o cadastro público do CNPJ**. "
    "CND federal, CRF/FGTS e CNDT **não foram consultadas** — exigem emissão "
    "formal com o certificado digital do cliente."
)


def cabecalho_empresa(empresa: Empresa) -> None:
    st.subheader(empresa.razao_social)
    st.caption(
        f"CNPJ {formatar_cnpj(empresa.cnpj)}  ·  Abertura {empresa.data_abertura}  ·  "
        f"{empresa.matriz_filial}  ·  {empresa.endereco.regiao}  ·  "
        f"Fontes: {', '.join(empresa.fontes)}"
    )


def painel_compliance(empresa: Empresa) -> None:
    """[CORRIGIDO — risco de produto] A versão anterior exibia quatro métricas
    verdes fixas ("Cadastro FGTS: Ativo", "CNDT: Ativo", "Apontamentos: 0
    Públicos") sem consultar nenhuma dessas bases. Afirmar regularidade
    trabalhista não verificada num documento entregue ao cliente é risco
    jurídico e reputacional, não só bug."""
    st.markdown("#### 🛡️ Situação cadastral")
    esq, dir_ = st.columns([1, 2])
    with esq:
        st.metric("Situação na Receita", empresa.situacao.situacao_receita,
                  delta="Regular" if empresa.situacao.esta_ativa else "Irregular",
                  delta_color="normal" if empresa.situacao.esta_ativa else "inverse")
        st.caption(f"Regime: **{empresa.regime}** · Porte: {empresa.porte}")
    with dir_:
        st.warning(AVISO_COMPLIANCE)
        with st.expander("O que ainda precisa ser verificado formalmente"):
            for item in empresa.situacao.pendentes_de_verificacao:
                st.markdown(f"- {item}")


def painel_tributario(empresa: Empresa) -> None:
    st.markdown("#### ⚡ Engenharia tributária")
    if not empresa.atividade_principal:
        st.info("CNAE principal não localizado nas bases consultadas.")
        return

    diag = empresa.atividade_principal.diagnostico
    esq, dir_ = st.columns([1, 2])
    with esq:
        st.markdown(f"**CNAE principal**\n\n`{empresa.cnae_principal_str}`")
        st.success(f"**Enquadramento:** {diag.anexo}")
        st.caption(f"Alíquota: {diag.aliquota_inicial}")
        if diag.is_minimercado:
            st.info("🛒 Minimercado / varejo alimentício — perfil-alvo Mercabiliza.")
        if diag.tem_fator_r:
            st.warning("⚡ Sujeito ao Fator R — simular folha antes de recomendar.")
    with dir_:
        st.markdown(f"**💡 Diagnóstico de economia**\n\n{diag.dica_engenharia}")

    if empresa.atividades_secundarias:
        with st.expander(f"📋 {len(empresa.atividades_secundarias)} CNAEs secundários"):
            st.dataframe(
                pd.DataFrame([{
                    "CNAE": a.codigo,
                    "Descrição": a.descricao,
                    "Anexo": a.diagnostico.anexo,
                    "Alíquota": a.diagnostico.aliquota_inicial,
                } for a in empresa.atividades_secundarias]),
                hide_index=True,
            )


def painel_societario(empresa: Empresa) -> None:
    st.markdown("#### 👥 Quadro societário")
    if empresa.tem_risco_societario:
        st.warning(
            "⚠️ **Risco de teto do Simples:** empresa com múltiplos sócios. "
            "Se algum sócio detiver ≥10% de outra empresa do Simples, as receitas "
            "somam para o limite de R$ 4,8 mi/ano (art. 3º, §4º, LC 123/2006)."
        )
    if empresa.socios:
        st.dataframe(
            pd.DataFrame([{
                "Sócio / Administrador": s.nome,
                "Qualificação": s.qualificacao,
                "Faixa etária": s.faixa_etaria,
            } for s in empresa.socios]),
            hide_index=True,
        )
    else:
        st.info("Empresário individual / MEI — sem sócios no QSA.")


def painel_contato(empresa: Empresa) -> None:
    st.markdown("#### 📍 Endereço e abordagem comercial")
    esq, dir_ = st.columns(2)
    with esq:
        st.markdown(f"**Endereço**\n\n{empresa.endereco.linha_completa}")
        st.caption(f"IBGE: `{empresa.endereco.cod_ibge}` · Região: {empresa.endereco.regiao}")
        st.link_button("🗺️ Abrir no Google Maps",
                       url_google_maps(empresa.endereco.linha_completa))
    with dir_:
        st.markdown(f"**E-mail(s):** {empresa.email_str}")
        st.markdown(f"**Telefone(s):** {empresa.telefone_str}")
        st.caption(f"Capital social: {moeda(empresa.capital_social)}")

        # [CORRIGIDO] Antes: todos os telefones eram concatenados e cortados em
        # 11 dígitos, gerando um número inexistente. Agora o usuário escolhe.
        if empresa.telefones:
            escolhido = st.selectbox(
                "Telefone para o WhatsApp:", empresa.telefones,
                key=f"wpp_{empresa.cnpj}",
            )
            mensagem = (
                f"Olá! Sou da Mercabiliza Contabilidade. Analisei o CNPJ "
                f"{formatar_cnpj(empresa.cnpj)} ({empresa.razao_social}) e identifiquei "
                f"oportunidades de otimização tributária. Posso enviar o diagnóstico?"
            )
            url = url_whatsapp(escolhido, mensagem)
            if url:
                st.link_button("📱 Abrir conversa no WhatsApp", url, type="primary")
            else:
                st.caption("Telefone com menos de 10 dígitos — não é possível montar o link.")
        else:
            st.caption("Nenhum telefone público disponível para abordagem.")


def cartao_cnpj(empresa: Empresa) -> None:
    with st.expander("📜 Comprovante de Inscrição e Situação Cadastral"):
        st.caption("Reprodução a partir de bases públicas — não substitui o "
                   "comprovante oficial da Receita Federal.")
        dados = {
            "Número de inscrição": f"{formatar_cnpj(empresa.cnpj)} ({empresa.matriz_filial})",
            "Data de abertura": empresa.data_abertura,
            "Nome empresarial": empresa.razao_social,
            "Nome fantasia": empresa.nome_fantasia,
            "Atividade principal": empresa.cnae_principal_str,
            "Natureza jurídica": empresa.natureza_juridica,
            "Endereço": empresa.endereco.linha_completa,
            "E-mail": empresa.email_str,
            "Telefone": empresa.telefone_str,
            "Situação cadastral": empresa.situacao.situacao_receita,
            "Porte": empresa.porte,
        }
        # [MELHORIA] Substitui um bloco de HTML montado por f-string com
        # ``unsafe_allow_html=True`` — que injetava dados de API direto no DOM
        # sem escape (XSS armazenado via razão social maliciosa).
        st.dataframe(
            pd.DataFrame({"Campo": list(dados), "Valor": list(dados.values())}),
            hide_index=True, width="stretch",
        )
        st.download_button(
            "📄 Baixar Cartão CNPJ (PDF)",
            data=pdf_cartao_bytes(empresa.cnpj, empresa),
            file_name=f"cartao_cnpj_{empresa.cnpj}.pdf",
            mime="application/pdf",
            key=f"dl_cartao_{empresa.cnpj}",
        )


def renderizar_dossie(empresa: Empresa) -> None:
    cabecalho_empresa(empresa)
    cartao_cnpj(empresa)
    painel_compliance(empresa)
    st.divider()
    painel_tributario(empresa)
    st.divider()
    painel_societario(empresa)
    st.divider()
    painel_contato(empresa)
