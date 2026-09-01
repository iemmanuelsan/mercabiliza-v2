"""Aba 6 — Ficha Cadastral e Contrato de Prestação de Serviços.

## Como o estado é gerenciado (e por que não há rerun indesejado)

Três decisões evitam os problemas clássicos de Streamlit neste tipo de tela:

1. **Buscas dentro de `st.form`.** Digitar CNPJ ou CEP não dispara rerun; só o
   `form_submit_button` submete. Sem isso, cada tecla reexecutaria o script.

2. **Preenchimento automático via callback.** As buscas de CNPJ e CEP rodam em
   `on_click`, que executa ANTES do rerun. Só assim é possível escrever em
   `st.session_state["ct_pj_razao"]` e ter o `text_input` de mesma `key` já
   renderizando o valor novo. Escrever em `session_state` depois do widget
   instanciado levantaria `StreamlitAPIException`.

3. **`@st.fragment` no bloco de documentos.** Mexer em valor, vencimento ou
   cláusula re-renderiza apenas essa seção — as abas de consulta não
   reexecutam, e nada é perdido ao alternar de aba.

Os PDFs são montados só quando o usuário clica, e ficam em `session_state`
para o `download_button` servir sem regerar a cada interação.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from ...config import FORO_PADRAO, settings
from ...core.cnpj import CNPJInvalidoError
from ...core.cnpj import validar as validar_cnpj
from ...core.contrato import (
    FORMAS_PAGAMENTO,
    INDICES_REAJUSTE,
    OBJETO_PADRAO,
    ParametrosContrato,
    listar_minutas,
)
from ...core.cpf import CPFInvalidoError
from ...core.cpf import validar as validar_cpf
from ...core.formatters import moeda
from ...core.models import Endereco
from ...core.pessoas import (
    ESTADOS_CIVIS,
    QUALIFICACOES_SIGNATARIO,
    ContratantePF,
    ContratantePJ,
    RepresentanteLegal,
    contratada_padrao,
    de_empresa,
)
from ...core.tributario import calcular_honorarios
from ..state import consultar_cep_cached, consultar_dossie

# --------------------------------------------------------------------------- #
# Chaves de estado                                                            #
# --------------------------------------------------------------------------- #
MODALIDADES = (
    "PJ — Contrato regular",
    "MEI — Desenquadramento",
    "PF — Abertura de empresa",
)
DESCRICAO_MODALIDADE = {
    MODALIDADES[0]: "Empresa já constituída: consulta o CNPJ e gera ficha + contrato.",
    MODALIDADES[1]: "MEI que estourou o limite: consulta o CNPJ, gera ficha + "
                    "contrato e o formulário de alteração com o que falta o "
                    "cliente decidir (razão social, capital, quotas).",
    MODALIDADES[2]: "Sem empresa aberta: coleta os dados por CPF e CEP e gera o "
                    "formulário de abertura para o cliente preencher.",
}
K_TIPO = "ct_tipo"
K_PDF_BRANCO = "doc_pdf_branco"
K_MSG_BUSCA = "ct_msg_busca"
K_QSA = "ct_qsa_opcoes"
K_FICHA_PDF = "ct_ficha_pdf"
K_CONTRATO_PDF = "ct_contrato_pdf"
K_NOME_ARQ = "ct_nome_arquivo"
K_DOCX = "ct_docx_formulario"

CAMPOS_PJ = {
    "ct_pj_cnpj": "", "ct_pj_razao": "", "ct_pj_fantasia": "", "ct_pj_cnae": "",
    "ct_pj_ie": "", "ct_pj_im": "", "ct_pj_tel": "", "ct_pj_email": "",
    "ct_pj_regime": "", "ct_pj_abertura": "",
    "ct_pj_log": "", "ct_pj_num": "", "ct_pj_compl": "", "ct_pj_bairro": "",
    "ct_pj_mun": "", "ct_pj_uf": "", "ct_pj_cep": "",
    "ct_rep_nome": "", "ct_rep_cpf": "", "ct_rep_rg": "", "ct_rep_orgao": "",
    "ct_rep_prof": "contador", "ct_rep_nac": "brasileiro",
}
CAMPOS_PF = {
    "ct_pf_nome": "", "ct_pf_cpf": "", "ct_pf_rg": "", "ct_pf_orgao": "",
    "ct_pf_prof": "", "ct_pf_nac": "brasileiro",
    "ct_pf_tel": "", "ct_pf_email": "",
    "ct_pf_log": "", "ct_pf_num": "", "ct_pf_compl": "", "ct_pf_bairro": "",
    "ct_pf_mun": "", "ct_pf_uf": "", "ct_pf_cep": "",
}


def _tem_cnpj() -> bool:
    """PJ e MEI partem de um CNPJ existente; PF é preenchimento manual."""
    return not st.session_state.get(K_TIPO, MODALIDADES[0]).startswith("PF")


def _perfil() -> str:
    """Código curto da modalidade: ``PJ``, ``MEI`` ou ``PF``."""
    return st.session_state.get(K_TIPO, MODALIDADES[0]).split(" ")[0]


def _inicializar() -> None:
    st.session_state.setdefault(K_TIPO, MODALIDADES[0])
    st.session_state.setdefault(K_MSG_BUSCA, None)
    st.session_state.setdefault(K_QSA, [])
    for chave, padrao in {**CAMPOS_PJ, **CAMPOS_PF}.items():
        st.session_state.setdefault(chave, padrao)


# --------------------------------------------------------------------------- #
# Callbacks de busca (rodam ANTES do rerun)                                   #
# --------------------------------------------------------------------------- #
def _buscar_cnpj() -> None:
    bruto = st.session_state.get("ct_busca_cnpj", "")
    try:
        cnpj = validar_cnpj(bruto)
    except CNPJInvalidoError as exc:
        st.session_state[K_MSG_BUSCA] = ("erro", str(exc))
        return

    empresa = consultar_dossie(cnpj, 0.0)
    if empresa is None:
        st.session_state[K_MSG_BUSCA] = (
            "erro",
            ("CNPJ não localizado nas bases públicas, ou os provedores estão "
             "indisponíveis. Preencha manualmente ou tente novamente."),
        )
        return

    pj = de_empresa(empresa)
    st.session_state.update({
        "ct_pj_cnpj": pj.cnpj,
        "ct_pj_razao": pj.razao_social,
        "ct_pj_fantasia": pj.nome_fantasia,
        "ct_pj_cnae": pj.cnae_principal,
        "ct_pj_ie": pj.inscricao_estadual,
        "ct_pj_im": pj.inscricao_municipal,
        "ct_pj_tel": pj.telefone,
        "ct_pj_email": pj.email,
        "ct_pj_regime": pj.regime,
        "ct_pj_abertura": pj.data_abertura,
        "ct_pj_log": pj.endereco.logradouro,
        "ct_pj_num": pj.endereco.numero,
        "ct_pj_bairro": pj.endereco.bairro,
        "ct_pj_mun": pj.endereco.municipio,
        "ct_pj_uf": pj.endereco.uf,
        "ct_pj_cep": pj.endereco.cep,
        K_QSA: [s.nome for s in empresa.socios],
    })
    # Pré-seleciona o primeiro sócio como signatário provável.
    if empresa.socios:
        st.session_state["ct_rep_nome"] = empresa.socios[0].nome

    achados = len(empresa.socios)
    st.session_state[K_MSG_BUSCA] = (
        "ok",
        f"Dados de {pj.razao_social} carregados de {', '.join(empresa.fontes)}. "
        + (f"{achados} sócio(s) no QSA — confira o signatário abaixo."
           if achados else "Nenhum sócio no QSA; informe o signatário manualmente."),
    )


def _buscar_cep(prefixo: str) -> None:
    """``prefixo`` é ``'pj'`` ou ``'pf'`` — define quais campos preencher."""
    bruto = st.session_state.get(f"ct_busca_cep_{prefixo}", "")
    from ...services.cep import CEPInvalidoError

    try:
        endereco = consultar_cep_cached(bruto)
    except CEPInvalidoError as exc:
        st.session_state[K_MSG_BUSCA] = ("erro", str(exc))
        return

    if endereco is None:
        st.session_state[K_MSG_BUSCA] = (
            "erro", "CEP não localizado no ViaCEP nem na BrasilAPI.")
        return

    st.session_state.update({
        f"ct_{prefixo}_log": endereco.logradouro,
        f"ct_{prefixo}_bairro": endereco.bairro,
        f"ct_{prefixo}_mun": endereco.municipio,
        f"ct_{prefixo}_uf": endereco.uf,
        f"ct_{prefixo}_cep": endereco.cep,
    })
    st.session_state[K_MSG_BUSCA] = (
        "ok", (f"Endereço encontrado: {endereco.linha_completa}. "
               "Complete o número e o complemento."))


# --------------------------------------------------------------------------- #
# Construção dos objetos de domínio a partir do estado                        #
# --------------------------------------------------------------------------- #
def _endereco_de(prefixo: str) -> Endereco:
    g = st.session_state.get
    return Endereco(
        logradouro=g(f"ct_{prefixo}_log", ""),
        numero=g(f"ct_{prefixo}_num", ""),
        complemento=g(f"ct_{prefixo}_compl", ""),
        bairro=g(f"ct_{prefixo}_bairro", ""),
        municipio=g(f"ct_{prefixo}_mun", ""),
        uf=g(f"ct_{prefixo}_uf", ""),
        cep=g(f"ct_{prefixo}_cep", ""),
    )


def _montar_contratante():
    g = st.session_state.get
    if _tem_cnpj():
        return ContratantePJ(
            razao_social=g("ct_pj_razao", ""),
            nome_fantasia=g("ct_pj_fantasia", ""),
            cnpj=g("ct_pj_cnpj", ""),
            cnae_principal=g("ct_pj_cnae", ""),
            endereco=_endereco_de("pj"),
            telefone=g("ct_pj_tel", ""),
            email=g("ct_pj_email", ""),
            inscricao_estadual=g("ct_pj_ie", ""),
            inscricao_municipal=g("ct_pj_im", ""),
            regime=g("ct_pj_regime", ""),
            data_abertura=g("ct_pj_abertura", ""),
            representante=RepresentanteLegal(
                nome=g("ct_rep_nome", ""),
                cpf=g("ct_rep_cpf", ""),
                rg=g("ct_rep_rg", ""),
                orgao_emissor=g("ct_rep_orgao", ""),
                nacionalidade=g("ct_rep_nac", "brasileiro"),
                estado_civil=g("ct_rep_civil", ""),
                profissao=g("ct_rep_prof", ""),
                qualificacao=g("ct_rep_qualif", "sócio administrador"),
                genero_feminino=g("ct_rep_fem", False),
            ),
        )

    return ContratantePF(
        nome=g("ct_pf_nome", ""),
        cpf=g("ct_pf_cpf", ""),
        rg=g("ct_pf_rg", ""),
        orgao_emissor=g("ct_pf_orgao", ""),
        nacionalidade=g("ct_pf_nac", "brasileiro"),
        estado_civil=g("ct_pf_civil", ""),
        profissao=g("ct_pf_prof", ""),
        endereco=_endereco_de("pf"),
        telefone=g("ct_pf_tel", ""),
        email=g("ct_pf_email", ""),
        genero_feminino=g("ct_pf_fem", False),
    )


# --------------------------------------------------------------------------- #
# Formulários                                                                  #
# --------------------------------------------------------------------------- #
def _bloco_endereco(prefixo: str, titulo: str = "Endereço") -> None:
    st.markdown(f"**{titulo}**")

    with st.form(f"form_cep_{prefixo}", clear_on_submit=False):
        c1, c2 = st.columns([1, 2])
        with c1:
            st.text_input("CEP", key=f"ct_busca_cep_{prefixo}",
                          placeholder="13201-804", max_chars=9)
        with c2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            st.form_submit_button(
                "🔎 Buscar endereço pelo CEP",
                on_click=_buscar_cep, args=(prefixo,), width="stretch")

    c1, c2, c3 = st.columns([3, 1, 1])
    c1.text_input("Logradouro", key=f"ct_{prefixo}_log")
    c2.text_input("Número", key=f"ct_{prefixo}_num")
    c3.text_input("Complemento", key=f"ct_{prefixo}_compl")

    c4, c5, c6, c7 = st.columns([2, 2, 1, 1])
    c4.text_input("Bairro", key=f"ct_{prefixo}_bairro")
    c5.text_input("Município", key=f"ct_{prefixo}_mun")
    c6.text_input("UF", key=f"ct_{prefixo}_uf", max_chars=2)
    c7.text_input("CEP", key=f"ct_{prefixo}_cep", max_chars=9,
                  help="Preenchido pela busca; editável.")


def _form_pj() -> None:
    st.markdown("#### 1. Dados da empresa")

    with st.form("form_busca_cnpj", clear_on_submit=False):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.text_input("CNPJ do cliente", key="ct_busca_cnpj",
                          placeholder="00.000.000/0001-91 ou 12.ABC.345/01DE-35")
        with c2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            st.form_submit_button("🔎 Buscar na Receita", type="primary",
                                  on_click=_buscar_cnpj, width="stretch")

    c1, c2 = st.columns(2)
    c1.text_input("Razão social *", key="ct_pj_razao")
    c2.text_input("Nome fantasia", key="ct_pj_fantasia")

    c3, c4, c5 = st.columns([2, 1, 1])
    c3.text_input("CNPJ *", key="ct_pj_cnpj")
    c4.text_input("Inscrição estadual", key="ct_pj_ie")
    c5.text_input("Inscrição municipal", key="ct_pj_im")

    c6, c7 = st.columns([2, 1])
    c6.text_input("CNAE principal", key="ct_pj_cnae")
    c7.text_input("Regime tributário", key="ct_pj_regime")

    c8, c9 = st.columns(2)
    c8.text_input("Telefone comercial", key="ct_pj_tel")
    c9.text_input("E-mail financeiro *", key="ct_pj_email")

    st.divider()
    _bloco_endereco("pj", "Endereço da sede")

    st.divider()
    st.markdown("#### 2. Representante legal (quem assina)")

    opcoes = list(st.session_state.get(K_QSA, []))
    if opcoes:
        st.caption(f"Sócios encontrados no QSA: {', '.join(opcoes)}")
        escolha = st.radio(
            "Signatário", [*opcoes, "Outro (procurador ou não consta do QSA)"],
            key="ct_rep_escolha", horizontal=False,
        )
        if not escolha.startswith("Outro"):
            st.session_state["ct_rep_nome"] = escolha
    else:
        st.caption("Nenhum sócio carregado do QSA — informe o signatário abaixo.")

    c1, c2, c3 = st.columns([2, 1, 1])
    c1.text_input("Nome completo *", key="ct_rep_nome")
    c2.text_input("CPF *", key="ct_rep_cpf", placeholder="000.000.000-00")
    c3.selectbox("Qualificação", QUALIFICACOES_SIGNATARIO, key="ct_rep_qualif")

    c4, c5, c6 = st.columns(3)
    c4.text_input("RG", key="ct_rep_rg")
    c5.text_input("Órgão emissor", key="ct_rep_orgao", placeholder="SSP/SP")
    c6.text_input("Profissão", key="ct_rep_prof")

    c7, c8, c9 = st.columns([1, 1, 1])
    c7.text_input("Nacionalidade", key="ct_rep_nac")
    c8.selectbox("Estado civil", ("", *ESTADOS_CIVIS), key="ct_rep_civil")
    c9.checkbox("Concordância no feminino", key="ct_rep_fem",
                help="Flexiona 'portadora', 'inscrita', 'sócia' no contrato.")

    if cpf := st.session_state.get("ct_rep_cpf", ""):
        try:
            validar_cpf(cpf)
        except CPFInvalidoError as exc:
            st.error(f"❌ CPF do representante: {exc}")


def _form_pf() -> None:
    st.markdown("#### 1. Qualificação civil")

    c1, c2 = st.columns([2, 1])
    c1.text_input("Nome completo *", key="ct_pf_nome")
    c2.text_input("CPF *", key="ct_pf_cpf", placeholder="000.000.000-00")

    if cpf := st.session_state.get("ct_pf_cpf", ""):
        try:
            cpf_ok = validar_cpf(cpf)
            st.caption(f"✅ CPF válido: {cpf_ok[:3]}.{cpf_ok[3:6]}.{cpf_ok[6:9]}-{cpf_ok[9:]}")
        except CPFInvalidoError as exc:
            st.error(f"❌ {exc}")

    c3, c4, c5 = st.columns(3)
    c3.text_input("RG", key="ct_pf_rg")
    c4.text_input("Órgão emissor", key="ct_pf_orgao", placeholder="SSP/SP")
    c5.text_input("Profissão *", key="ct_pf_prof")

    c6, c7, c8 = st.columns([1, 1, 1])
    c6.text_input("Nacionalidade", key="ct_pf_nac")
    c7.selectbox("Estado civil *", ("", *ESTADOS_CIVIS), key="ct_pf_civil")
    c8.checkbox("Concordância no feminino", key="ct_pf_fem",
                help="Flexiona 'portadora', 'inscrita', 'domiciliada' no contrato.")

    c9, c10 = st.columns(2)
    c9.text_input("Telefone / WhatsApp", key="ct_pf_tel")
    c10.text_input("E-mail", key="ct_pf_email")

    st.divider()
    _bloco_endereco("pf", "Endereço residencial")


# --------------------------------------------------------------------------- #
# Parâmetros + documentos (fragment isolado)                                   #
# --------------------------------------------------------------------------- #
@st.fragment
def _gerar_docx(contratante) -> bytes:
    """Formulário DOCX com o que o sistema já sabe preenchido em negrito.

    O perfil define o título e as seções: MEI ganha o bloco de
    desenquadramento; PF entra sem dados de empresa (ainda não existe).
    """
    from ...core.pessoas import ContratantePJ
    from ...exporters.docx_abertura import (
        dados_de_contratante,
        gerar_formulario_abertura,
    )

    empresa, endereco, socios = dados_de_contratante(contratante)
    perfil = _perfil()

    desenq = None
    if perfil == "MEI" and isinstance(contratante, ContratantePJ):
        desenq = {
            "cnpj": contratante.documento_principal,
            "razao_atual": contratante.razao_social,
            "abertura": contratante.data_abertura,
            "ie": contratante.inscricao_estadual,
        }

    # Na abertura (PF) não há razão social nem CNAE definidos: tudo é decisão
    # do cliente, então o bloco da empresa sai inteiro para preencher.
    if perfil == "PF":
        empresa = {}

    return gerar_formulario_abertura(
        perfil, empresa, endereco, socios, desenq,
        minimo_socios=2 if perfil != "MEI" else 1,
    )


def _bloco_documentos(contratante) -> None:
    from ...exporters.pdf_documentos import gerar_contrato, gerar_ficha_cadastral

    contratada = contratada_padrao()
    precos = settings.precos

    st.markdown("#### 3. Parâmetros do contrato")

    objeto = st.text_area(
        "Objeto do serviço", value=OBJETO_PADRAO, key="ct_objeto", height=80,
        help="Completa a frase: “…a prestação dos serviços de {objeto}”.",
    )

    st.markdown("**Honorários**")
    modo = st.radio(
        "Origem do valor",
        ["Calcular pela tabela do app", "Informar manualmente"],
        key="ct_modo_valor", horizontal=True,
    )

    if modo.startswith("Calcular"):
        c1, c2, c3 = st.columns(3)
        qtd_cnpjs = c1.number_input("Unidades / CNPJs", 1, 50, 1, key="ct_qtd_cnpj")
        qtd_pessoas = c2.number_input("Vínculos (DP)", 0, 200, 0, key="ct_qtd_pes")
        pontuais = []
        with c3:
            if st.checkbox(f"Desenq. MEI ({moeda(precos.desenquadramento_mei)})",
                           key="ct_inc_desenq"):
                pontuais.append(("Desenquadramento de MEI",
                                 precos.desenquadramento_mei))
            if st.checkbox(f"Abertura ({moeda(precos.abertura_empresa)})",
                           key="ct_inc_abert"):
                pontuais.append(("Constituição de empresa", precos.abertura_empresa))
        h = calcular_honorarios(qtd_cnpjs, qtd_pessoas, pontuais, precos)
        valor_mensal, valor_implantacao = h.mensal, h.total_pontual
        st.caption(
            f"Base {moeda(h.base)} + filiais {moeda(h.adicional_cnpjs)} + "
            f"DP {moeda(h.adicional_dp)} = **{moeda(h.mensal)}/mês**"
            + (f" · pontuais {moeda(h.total_pontual)}" if h.total_pontual else "")
        )
    else:
        c1, c2 = st.columns(2)
        valor_mensal = c1.number_input("Honorário mensal (R$)", 0.0,
                                       value=350.0, step=50.0, key="ct_val_mes")
        valor_implantacao = c2.number_input("Taxa de implantação (R$)", 0.0,
                                           value=0.0, step=50.0, key="ct_val_impl")

    c1, c2, c3 = st.columns(3)
    dia_venc = c1.number_input("Dia do vencimento", 1, 31, 10, key="ct_dia")
    forma = c2.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, key="ct_forma")
    indice = c3.selectbox("Índice de reajuste", INDICES_REAJUSTE, key="ct_indice")

    c4, c5, c6 = st.columns(3)
    data_inicio = c4.date_input("Início da vigência", value=date.today(),
                                key="ct_inicio", format="DD/MM/YYYY")
    vigencia = c5.number_input("Vigência (meses; 0 = indeterminado)", 0, 120, 12,
                               key="ct_vigencia")
    rescisao = c6.number_input("Aviso prévio (dias)", 0, 180, 30, key="ct_rescisao")

    c7, c8, c9 = st.columns(3)
    foro = c7.text_input("Foro (comarca)", value=FORO_PADRAO, key="ct_foro")
    cidade = c8.text_input("Cidade da assinatura",
                           value=FORO_PADRAO.split("/")[0], key="ct_cidade")
    data_assin = c9.date_input("Data da assinatura", value=date.today(),
                               key="ct_data_assin", format="DD/MM/YYYY")

    particulares_txt = st.text_area(
        "Cláusulas particulares (uma por linha, opcional)",
        key="ct_particulares", height=90,
        placeholder="Os três primeiros meses terão desconto de 20% sobre os honorários.",
    )

    minutas = listar_minutas()
    template = None
    if len(minutas) > 1:
        template = st.selectbox("Modelo de minuta", minutas, key="ct_template")

    parametros = ParametrosContrato(
        objeto=objeto,
        valor_mensal=float(valor_mensal),
        valor_implantacao=float(valor_implantacao),
        dia_vencimento=int(dia_venc),
        forma_pagamento=forma,
        data_inicio=data_inicio,
        vigencia_meses=int(vigencia),
        indice_reajuste=indice,
        prazo_rescisao_dias=int(rescisao),
        foro=foro,
        cidade_assinatura=cidade,
        data_assinatura=data_assin,
        clausulas_particulares=tuple(
            linha.strip() for linha in particulares_txt.splitlines() if linha.strip()
        ),
    )

    # ---------------- Pré-visualização ------------------------------- #
    st.divider()
    st.markdown("#### 4. Conferência antes de gerar")

    pend_cliente = contratante.pendencias
    pend_param = parametros.pendencias
    pend_contratada = contratada.pendencias

    col_a, col_b = st.columns(2)
    with col_a:
        if pend_cliente:
            st.warning("**Faltando no cadastro do cliente:**\n\n"
                       + "\n".join(f"- {p}" for p in pend_cliente))
        else:
            st.success("✅ Cadastro do cliente completo.")
        if pend_param:
            st.warning("**Faltando nos parâmetros:**\n\n"
                       + "\n".join(f"- {p}" for p in pend_param))
        else:
            st.success("✅ Parâmetros do contrato completos.")
    with col_b:
        if pend_contratada:
            st.error("**Faltando no cadastro da Mercabiliza** (edite `src/config.py`):\n\n"
                     + "\n".join(f"- {p}" for p in pend_contratada))
        else:
            st.success("✅ Cadastro da contratada completo.")

    with st.expander("👁️ Qualificação das partes (texto que vai ao contrato)",
                     expanded=True):
        st.markdown(f"**CONTRATANTE**\n\n{contratante.qualificacao_contratual}.")
        st.markdown(f"**CONTRATADA**\n\n{contratada.qualificacao_contratual}.")

    with st.expander("📋 Resumo dos dados cadastrais"):
        import pandas as pd
        linhas = contratante.linhas_ficha()
        if contratante.tipo == "PJ":
            linhas = [*linhas, ("—— Representante ——", ""),
                      *contratante.linhas_representante()]
        st.dataframe(
            pd.DataFrame(linhas, columns=["Campo", "Valor"]),
            hide_index=True, width="stretch",
        )

    # ---------------- Geração ---------------------------------------- #
    st.divider()
    st.markdown("#### 5. Gerar documentos")

    nome_arquivo = "".join(
        c for c in (contratante.cnpj if contratante.tipo == "PJ" else contratante.cpf)
        if c.isalnum()
    ) or "cliente"

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📋 Gerar Ficha Cadastral", width="stretch"):
            try:
                st.session_state[K_FICHA_PDF] = gerar_ficha_cadastral(
                    contratante, contratada, parametros)
                st.session_state[K_NOME_ARQ] = nome_arquivo
            except Exception as exc:
                st.error(f"Falha ao gerar a ficha: {exc}")
    with c2:
        if st.button("📄 Gerar Contrato", type="primary", width="stretch"):
            try:
                st.session_state[K_CONTRATO_PDF] = gerar_contrato(
                    contratante, contratada, parametros, template=template)
                st.session_state[K_NOME_ARQ] = nome_arquivo
            except Exception as exc:
                st.error(f"Falha ao gerar o contrato: {exc}")
    with c3:
        rotulo_docx = {
            "MEI": "📝 Gerar Form. Desenquadramento",
            "PF": "📝 Gerar Form. Abertura",
        }.get(_perfil(), "📝 Gerar Form. Alteração")
        if st.button(rotulo_docx, width="stretch"):
            try:
                st.session_state[K_DOCX] = _gerar_docx(contratante)
                st.session_state[K_NOME_ARQ] = nome_arquivo
            except Exception as exc:
                st.error(f"Falha ao gerar o formulário: {exc}")

    arq = st.session_state.get(K_NOME_ARQ, nome_arquivo)
    d1, d2, d3 = st.columns(3)
    with d1:
        if pdf := st.session_state.get(K_FICHA_PDF):
            st.download_button(
                "⬇️ Baixar Ficha Cadastral (PDF)", data=pdf,
                file_name=f"ficha_cadastral_{arq}.pdf",
                mime="application/pdf", width="stretch",
            )
    with d2:
        if pdf := st.session_state.get(K_CONTRATO_PDF):
            st.download_button(
                "⬇️ Baixar Contrato (PDF)", data=pdf,
                file_name=f"contrato_{arq}.pdf",
                mime="application/pdf", type="primary", width="stretch",
            )

    with d3:
        if docx := st.session_state.get(K_DOCX):
            st.download_button(
                "⬇️ Baixar Formulário (DOCX)", data=docx,
                file_name=f"formulario_{_perfil().lower()}_{arq}.docx",
                mime=("application/vnd.openxmlformats-officedocument"
                      ".wordprocessingml.document"),
                width="stretch",
            )

    if pend_cliente or pend_param or pend_contratada:
        st.caption(
            "⚠️ Com campos pendentes, o contrato sai com a tarja "
            "“MINUTA PARA CONFERÊNCIA — não assinar” e linhas de preenchimento "
            "no lugar dos dados que faltam."
        )


# --------------------------------------------------------------------------- #
# Ficha em branco — para quando NÃO há CNPJ a consultar                        #
# --------------------------------------------------------------------------- #
@st.fragment
def _bloco_ficha_branco() -> None:
    """Ficha vazia para o cliente preencher.

    É o caminho correto quando não há CNPJ: **não existe base pública de CPF**.
    A Consulta CPF do SERPRO só confirma nome e situação cadastral (não devolve
    endereço, telefone nem estado civil), e bureau privado exige base legal
    própria sob a LGPD. Pedir ao titular é mais rápido, mais barato e mais
    sólido — a declaração de veracidade assinada vale mais que a consulta.

    ``@st.fragment`` isola o bloco: gerar a ficha não reexecuta o formulário
    acima nem perde o que já foi digitado.
    """
    from ...exporters.pdf_ficha import gerar_ficha_em_branco

    st.subheader("📋 Ficha em branco para o cliente preencher")
    st.caption(
        "Use quando o cliente ainda não tem CNPJ, ou quando os dados precisam "
        "vir dele — pessoa física não tem base pública consultável."
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    tipo = col1.radio("Modelo", ["PF", "PJ"], horizontal=True, key="branco_tipo")
    operacao = col2.checkbox("Incluir dados da operação", value=True,
                             key="branco_operacao",
                             help="Lojas, sistema de gestão, NFC-e, franquia.")
    if col3.button("Gerar ficha em branco", width="stretch"):
        st.session_state[K_PDF_BRANCO] = gerar_ficha_em_branco(
            tipo, incluir_operacao=operacao)

    if pdf := st.session_state.get(K_PDF_BRANCO):
        st.download_button(
            "📄 Baixar ficha em branco (PDF)", data=pdf,
            file_name=f"ficha_cadastral_em_branco_{st.session_state.branco_tipo}.pdf",
            mime="application/pdf", type="primary", width="stretch",
        )


# --------------------------------------------------------------------------- #
# Entrada da aba                                                               #
# --------------------------------------------------------------------------- #
def render() -> None:
    _inicializar()

    st.header("📝 Ficha Cadastral & Contrato")
    st.caption(
        "Gera a ficha para conferência do cliente e a minuta contratual em PDF. "
        "Para PJ, os dados vêm da consulta de CNPJ; para PF, o endereço vem da "
        "busca por CEP."
    )

    contratada = contratada_padrao()
    if not contratada.esta_configurada:
        st.warning(
            "⚙️ **Cadastro da Mercabiliza incompleto.** Os documentos podem ser "
            "gerados para conferência, mas sairão marcados como minuta. "
            "Complete em `src/config.py`: "
            + ", ".join(contratada.pendencias) + ".",
            icon="⚙️",
        )

    st.radio(
        "Modalidade",
        MODALIDADES, key=K_TIPO, horizontal=True,
        help="PJ: contrato regular. MEI: desenquadramento com formulário de "
             "alteração. PF: abertura de empresa nova.",
    )
    st.caption(DESCRICAO_MODALIDADE[st.session_state[K_TIPO]])

    if msg := st.session_state.get(K_MSG_BUSCA):
        nivel, texto = msg
        (st.success if nivel == "ok" else st.error)(texto)
        st.session_state[K_MSG_BUSCA] = None

    st.divider()
    if _tem_cnpj():
        _form_pj()
    else:
        _form_pf()

    st.divider()
    _bloco_documentos(_montar_contratante())

    st.divider()
    _bloco_ficha_branco()
