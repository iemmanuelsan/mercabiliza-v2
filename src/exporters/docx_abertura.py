"""Formulário de Abertura / Desenquadramento em DOCX.

Replica a estrutura da "FICHA CADASTRAL - ABERTURA DE EMPRESA" da Mercabiliza,
com o diferencial que motiva o módulo: **preenchimento híbrido**.

## Por que DOCX e não XLSX

O formulário original é um documento com tabelas rotuladas, não uma planilha
de dados. Em DOCX o cliente preenche no Word, no Google Docs ou imprime e
escreve à mão, sem quebrar layout — e é o formato que ele já conhece. XLSX
faria sentido se o retorno fosse importado de volta em massa; para um
formulário assinado por cliente, DOCX é o certo.

## Convenção visual

* **Negrito** = preenchido pelo sistema (via API de CNPJ, CEP ou cadastro).
  O cliente só confere.
* `[ PREENCHER AQUI ]` em vermelho = depende de decisão do cliente (opções de
  razão social, capital social, distribuição de quotas, previsão de
  faturamento).
* Campo vazio = dado que o cliente tem mas o sistema não conseguiu obter.

Essa distinção é o ponto do documento: sem ela o cliente relê tudo, e com ela
ele vai direto às ~8 decisões que só ele pode tomar.
"""

from __future__ import annotations

import io
from datetime import date

from docx import Document
from docx.shared import Pt

from ..core.cnpj import formatar as formatar_cnpj
from ..core.contrato import valor_extenso
from ..core.cpf import formatar as formatar_cpf
from ..core.formatters import moeda
from .docx_base import (
    MARCADOR_PENDENTE,
    Campo,
    Secao,
    cabecalho as _cabecalho,
    configurar_pagina as _configurar_pagina,
    legenda as _legenda,
    run as _run,
    rodape_assinatura,
    tabela_campos as _tabela_campos,
    titulo_secao as _titulo_secao,
)

# Reexportado: `MARCADOR_PENDENTE` faz parte da interface pública deste módulo
# desde antes da extração da base, e há teste importando daqui.
__all__ = [
    "MARCADOR_PENDENTE",
    "Campo",
    "Secao",
    "capital_social_formatado",
    "dados_de_contratante",
    "gerar_formulario_abertura",
]

DECLARACAO = (
    "declaro que as informações prestadas neste formulário são verdadeiras e "
    "completas, e autorizo seu uso para os atos de constituição/alteração "
    "societária e cadastro nos órgãos competentes, nos termos da Lei nº "
    "13.709/2018 (LGPD)."
)


# --------------------------------------------------------------------------- #
# Montagem das seções                                                          #
# --------------------------------------------------------------------------- #
def _secao_empresa(dados: dict) -> Secao:
    """Dados da futura empresa (ou da nova configuração, no desenquadramento)."""
    return Secao("Dados da empresa", [
        Campo("Razão Social (1ª opção)", dados.get("razao_social", ""),
              pendente=True, dica="Nome empresarial pretendido"),
        Campo("2ª opção de Razão Social", "", pendente=True),
        Campo("3ª opção de Razão Social", "", pendente=True),
        Campo("Nome Fantasia", dados.get("nome_fantasia", ""), pendente=True),
        Campo("Descrição da Atividade", dados.get("atividade", ""), pendente=True,
              dica="O que a empresa vende/faz, em uma frase"),
        Campo("CNAE pretendido", dados.get("cnae", ""),
              dica="Sugerido pela contabilidade"),
        Campo("Capital Social (R$)", dados.get("capital_social", ""), pendente=True),
        Campo("Capital Social por extenso", dados.get("capital_extenso", ""),
              pendente=True),
        Campo("Tipo Jurídico", dados.get("tipo_juridico", ""), pendente=True,
              dica="Sociedade Limitada, Sociedade Unipessoal, Empresário Individual"),
        Campo("Previsão de faturamento mensal", dados.get("faturamento", ""),
              pendente=True),
        Campo("Regime tributário pretendido", dados.get("regime", ""),
              dica="Sugerido pela contabilidade após análise"),
        Campo("Nº de funcionários previstos", dados.get("funcionarios", ""),
              pendente=True),
    ])


def _secao_endereco(dados: dict) -> Secao:
    return Secao("Endereço da empresa", [
        Campo("Logradouro", dados.get("logradouro", "")),
        Campo("Número", dados.get("numero", "")),
        Campo("Complemento", dados.get("complemento", "")),
        Campo("Bairro", dados.get("bairro", "")),
        Campo("Município", dados.get("municipio", "")),
        Campo("UF", dados.get("uf", "")),
        Campo("CEP", dados.get("cep", "")),
        Campo("Ponto de referência", "", pendente=False),
        Campo("Telefone", dados.get("telefone", "")),
        Campo("E-mail", dados.get("email", "")),
        Campo("O imóvel é próprio ou alugado?", "", pendente=True),
        Campo("IPTU / inscrição imobiliária", "", pendente=True,
              dica="Necessário para o alvará"),
    ])


def _secao_socio(numero: int, dados: dict) -> Secao:
    return Secao(f"Sócio {numero:02d}", [
        Campo("Nome completo", dados.get("nome", "")),
        Campo("Nacionalidade", dados.get("nacionalidade", "brasileiro(a)")),
        Campo("Naturalidade", dados.get("naturalidade", ""), pendente=True),
        Campo("Profissão", dados.get("profissao", "")),
        Campo("Data de nascimento", dados.get("nascimento", ""), pendente=True),
        Campo("Estado civil", dados.get("estado_civil", "")),
        Campo("Regime de bens", dados.get("regime_bens", ""), pendente=True,
              dica="Parcial, Total, Universal — se casado(a)"),
        Campo("CPF/MF", dados.get("cpf", "")),
        Campo("C.I. / R.G.", dados.get("rg", "")),
        Campo("Órgão emissor / UF", dados.get("orgao", "")),
        Campo("Data de expedição", dados.get("expedicao", ""), pendente=True),
        Campo("Título de eleitor", "", pendente=True),
        Campo("Participação no capital (%)", dados.get("participacao", ""),
              pendente=True),
        Campo("Sócio administrador?", dados.get("administrador", ""), pendente=True,
              dica="Sim ou Não"),
        Campo("Logradouro", dados.get("logradouro", "")),
        Campo("Número", dados.get("numero", "")),
        Campo("Complemento", dados.get("complemento", "")),
        Campo("Bairro", dados.get("bairro", "")),
        Campo("Município", dados.get("municipio", "")),
        Campo("UF", dados.get("uf", "")),
        Campo("CEP", dados.get("cep", "")),
        Campo("Telefone / Celular", dados.get("telefone", "")),
        Campo("E-mail", dados.get("email", "")),
    ])


def _secao_desenquadramento(dados: dict) -> Secao:
    """Só aparece no perfil MEI — o que muda ao sair do MEI."""
    return Secao("Desenquadramento do MEI", [
        Campo("CNPJ atual (MEI)", dados.get("cnpj", "")),
        Campo("Razão social atual", dados.get("razao_atual", "")),
        Campo("Data de abertura", dados.get("abertura", "")),
        Campo("Faturamento acumulado no ano", dados.get("faturamento_ano", ""),
              pendente=True, dica="Determina se o desenquadramento é retroativo"),
        Campo("Faturamento do ano anterior", "", pendente=True),
        Campo("Data pretendida de efeito", "", pendente=True,
              dica="Retroativo a 01/01 ou a partir do mês seguinte"),
        Campo("Possui funcionário registrado?", "", pendente=True),
        Campo("Emite NFC-e atualmente?", dados.get("nfce", ""), pendente=True),
        Campo("Sistema de gestão / PDV", dados.get("sistema", ""), pendente=True),
        Campo("Possui inscrição estadual?", dados.get("ie", ""), pendente=True),
    ])


def gerar_formulario_abertura(
    perfil: str,
    dados_empresa: dict | None = None,
    dados_endereco: dict | None = None,
    socios: list[dict] | None = None,
    dados_desenquadramento: dict | None = None,
    minimo_socios: int = 2,
) -> bytes:
    """Monta o formulário e devolve os bytes do ``.docx``.

    ``perfil`` = ``"PF"`` (abertura nova), ``"MEI"`` (desenquadramento) ou
    ``"PJ"`` (alteração cadastral). Muda o título e quais seções entram.
    """
    perfil = perfil.upper()
    dados_empresa = dados_empresa or {}
    dados_endereco = dados_endereco or {}
    socios = socios or []

    titulos = {
        "MEI": ("FICHA CADASTRAL — DESENQUADRAMENTO DE MEI",
                "Migração de MEI para Microempresa (ME) no Simples Nacional"),
        "PF": ("FICHA CADASTRAL — ABERTURA DE EMPRESA",
               "Constituição de nova sociedade"),
        "PJ": ("FICHA CADASTRAL — ALTERAÇÃO CONTRATUAL",
               "Atualização de dados cadastrais e societários"),
    }
    titulo, subtitulo = titulos.get(perfil, titulos["PF"])

    doc = Document()
    _configurar_pagina(doc)
    _cabecalho(doc, titulo, f"{subtitulo} · emitida em {date.today():%d/%m/%Y}")
    _legenda(doc)

    if perfil == "MEI" and dados_desenquadramento:
        secao = _secao_desenquadramento(dados_desenquadramento)
        _titulo_secao(doc, secao.titulo)
        _tabela_campos(doc, secao.campos)

    for secao in (_secao_empresa(dados_empresa), _secao_endereco(dados_endereco)):
        _titulo_secao(doc, secao.titulo)
        _tabela_campos(doc, secao.campos)

    # Sempre imprime ao menos ``minimo_socios`` blocos: o cliente pode incluir
    # sócio que a contabilidade ainda não conhece.
    total_socios = max(len(socios), minimo_socios)
    for i in range(total_socios):
        dados = socios[i] if i < len(socios) else {}
        secao = _secao_socio(i + 1, dados)
        _titulo_secao(doc, secao.titulo)
        _tabela_campos(doc, secao.campos)

    _titulo_secao(doc, "Documentos a anexar")
    for item in _documentos(perfil):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        _run(p, f"[   ]  {item}", tamanho=8.5)

    rodape_assinatura(doc, DECLARACAO,
                      "Assinatura do titular / sócio administrador")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _documentos(perfil: str) -> tuple[str, ...]:
    comuns = (
        "RG e CPF de todos os sócios (ou CNH)",
        "Comprovante de residência de cada sócio (últimos 3 meses)",
        "Comprovante de endereço do imóvel da empresa (IPTU ou conta de consumo)",
        "Contrato de locação do ponto, se alugado",
    )
    if perfil == "MEI":
        return (
            *comuns,
            "Certificado da Condição de MEI (CCMEI)",
            "Extrato do faturamento (relatório mensal de receitas do MEI)",
            "Últimos DAS-MEI pagos",
            "Declaração Anual do MEI (DASN-SIMEI) do último exercício",
            "Relatório de vendas por NCM/EAN do sistema de autoatendimento",
        )
    if perfil == "PJ":
        return (
            *comuns,
            "Contrato social e última alteração consolidada",
            "Cartão CNPJ atualizado",
            "Certificado digital e-CNPJ (A1 ou A3)",
        )
    return (
        *comuns,
        "Certidão de casamento, se casado(a)",
        "Consulta de viabilidade aprovada, se já solicitada",
    )


# --------------------------------------------------------------------------- #
# Ponte com os modelos do sistema                                              #
# --------------------------------------------------------------------------- #
def dados_de_contratante(contratante) -> tuple[dict, dict, list[dict]]:
    """Extrai do contratante o que já dá para preencher automaticamente.

    Devolve ``(dados_empresa, dados_endereco, socios)`` no formato que
    :func:`gerar_formulario_abertura` espera.
    """
    from ..core.pessoas import ContratantePJ

    endereco = contratante.endereco
    dados_endereco = {
        "logradouro": endereco.logradouro,
        "numero": endereco.numero,
        "complemento": endereco.complemento,
        "bairro": endereco.bairro,
        "municipio": endereco.municipio,
        "uf": endereco.uf,
        "cep": endereco.cep_formatado,
        "telefone": contratante.telefone,
        "email": contratante.email,
    }

    if isinstance(contratante, ContratantePJ):
        empresa = {
            "cnpj": formatar_cnpj(contratante.cnpj) if contratante.cnpj else "",
            "razao_social": contratante.razao_social,
            "nome_fantasia": contratante.nome_fantasia,
            "cnae": contratante.cnae_principal,
            "regime": contratante.regime,
        }
        rep = contratante.representante
        socios = [{
            "nome": rep.nome,
            "cpf": formatar_cpf(rep.cpf) if rep.cpf else "",
            "rg": rep.rg,
            "orgao": rep.orgao_emissor,
            "estado_civil": rep.estado_civil,
            "profissao": rep.profissao,
            "nacionalidade": rep.nacionalidade,
            "administrador": "Sim",
            **{k: dados_endereco[k] for k in
               ("logradouro", "numero", "bairro", "municipio", "uf", "cep")},
        }] if rep.nome else []
    else:
        empresa = {}
        socios = [{
            "nome": contratante.nome,
            "cpf": formatar_cpf(contratante.cpf) if contratante.cpf else "",
            "rg": contratante.rg,
            "orgao": contratante.orgao_emissor,
            "estado_civil": contratante.estado_civil,
            "profissao": contratante.profissao,
            "nacionalidade": contratante.nacionalidade,
            **{k: dados_endereco[k] for k in
               ("logradouro", "numero", "bairro", "municipio", "uf", "cep")},
            "telefone": contratante.telefone,
            "email": contratante.email,
        }] if contratante.nome else []

    return empresa, dados_endereco, socios


def capital_social_formatado(valor: float) -> tuple[str, str]:
    """``(numérico, por extenso)`` — usado quando o valor já foi definido."""
    if valor <= 0:
        return "", ""
    return moeda(valor), valor_extenso(valor)
