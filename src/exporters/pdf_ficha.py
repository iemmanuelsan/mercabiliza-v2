"""Ficha cadastral em PDF — preenchida ou em branco.

Dois modos, mesma diagramação:

* **Preenchida** — os dados que já temos (consulta de CNPJ + digitação) vão
  impressos, e o cliente assina *conferindo*. Usa-se quando há CNPJ.
* **Em branco** — os campos saem como linhas para preenchimento à mão ou em
  PDF. Usa-se quando **não há CNPJ para consultar** (pessoa física, ou
  empresa ainda não aberta): não existe base pública de CPF, então a única
  fonte legítima do dado é o próprio titular.

Em ambos os casos o rodapé traz a **declaração de veracidade** assinada. Isso
não é formalidade: é o que transfere a responsabilidade pela exatidão do dado
para quem efetivamente a tem, e é a proteção mais forte disponível quando não
há como validar o dado contra uma base oficial.
"""

from __future__ import annotations

from datetime import date

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from ..core.contrato import data_extenso
from ..core.pessoas import Contratada, ContratantePF, ContratantePJ
from .pdf_juridico import (
    LARGURA_UTIL,
    bloco_assinatura_dupla,
    construir_estilos,
    escapar,
    render_documento,
    tabela_dados,
)

DECLARACAO = (
    "Declaro, sob as penas da lei, que as informações prestadas nesta ficha "
    "cadastral são verdadeiras, completas e atuais, e assumo o compromisso de "
    "comunicar à contratada qualquer alteração no prazo de 10 (dez) dias. "
    "Autorizo o tratamento dos dados aqui informados para as finalidades de "
    "execução do contrato de prestação de serviços contábeis e de cumprimento "
    "de obrigações legais, nos termos da Lei nº 13.709/2018 (LGPD)."
)

NOTA_ORIGEM = (
    "Os dados cadastrais desta ficha foram obtidos de bases públicas de CNPJ "
    "(BrasilAPI, CNPJ.ws, ReceitaWS) e complementados com informações prestadas "
    "pelo titular. Confira cada campo antes de assinar."
)

NOTA_EM_BRANCO = (
    "Preencha todos os campos com letra legível. Os dados serão usados para "
    "elaborar o contrato de prestação de serviços e para o cadastro nos órgãos "
    "fiscais — divergências geram retrabalho e atraso na abertura ou migração."
)

CAMPOS_PF_BRANCO: tuple[tuple[str, str], ...] = (
    ("Nome completo", ""),
    ("CPF", ""),
    ("RG", ""),
    ("Órgão emissor / UF", ""),
    ("Data de nascimento", ""),
    ("Nacionalidade", ""),
    ("Estado civil", ""),
    ("Profissão", ""),
    ("Nome da mãe", ""),
    ("CEP", ""),
    ("Endereço (rua e número)", ""),
    ("Complemento", ""),
    ("Bairro", ""),
    ("Município / UF", ""),
    ("Telefone / WhatsApp", ""),
    ("E-mail", ""),
)

CAMPOS_PJ_BRANCO: tuple[tuple[str, str], ...] = (
    ("Razão social", ""),
    ("Nome fantasia", ""),
    ("CNPJ", ""),
    ("Inscrição estadual", ""),
    ("Inscrição municipal", ""),
    ("Regime tributário atual", ""),
    ("Faturamento médio mensal", ""),
    ("CEP", ""),
    ("Endereço (rua e número)", ""),
    ("Complemento", ""),
    ("Bairro", ""),
    ("Município / UF", ""),
    ("Telefone comercial", ""),
    ("E-mail financeiro", ""),
)

CAMPOS_REPRESENTANTE_BRANCO: tuple[tuple[str, str], ...] = (
    ("Nome completo", ""),
    ("CPF", ""),
    ("RG / Órgão emissor", ""),
    ("Estado civil", ""),
    ("Profissão", ""),
    ("Qualificação (sócio, titular, procurador)", ""),
    ("Telefone", ""),
    ("E-mail", ""),
)

CAMPOS_OPERACAO_BRANCO: tuple[tuple[str, str], ...] = (
    ("Quantidade de lojas / unidades", ""),
    ("Local das lojas (condomínio, empresa, rua)", ""),
    ("Sistema de gestão utilizado", ""),
    ("Emite NFC-e atualmente? (sim / não)", ""),
    ("Franquia ou licença (qual?)", ""),
    ("Nº de funcionários registrados", ""),
    ("Possui outros CNPJs? (quais?)", ""),
    ("Contador anterior (nome e contato)", ""),
)

_LINHA_VAZIA = " " * 60


def _tabela_branco(campos, estilos) -> Table:
    """Mesma tabela da versão preenchida, mas com a coluna de valor em branco.

    Reaproveitar :func:`tabela_dados` mantém as duas versões da ficha
    visualmente idênticas — o cliente reconhece o documento.
    """
    return tabela_dados([(rotulo, _LINHA_VAZIA) for rotulo, _ in campos], estilos)


def _cabecalho(estilos, titulo: str, subtitulo: str) -> list:
    return [
        Paragraph(escapar(titulo), estilos["titulo"]),
        Paragraph(escapar(subtitulo), estilos["subtitulo"]),
    ]


def _secao(estilos, texto: str) -> Paragraph:
    return Paragraph(escapar(texto), estilos["secao"])


def _bloco_declaracao(estilos, nome_titular: str, cidade: str = "") -> list:
    """Declaração de veracidade + assinatura do titular e do preposto."""
    local = f"{cidade}, " if cidade else ""
    return [
        Spacer(1, 6 * mm),
        KeepTogether([
            _secao(estilos, "Declaração de veracidade"),
            Paragraph(escapar(DECLARACAO), estilos["nota"]),
            Spacer(1, 4 * mm),
            Paragraph(escapar(f"{local}______ de _____________________ de ______."),
                      estilos["corpo"]),
            bloco_assinatura_dupla(
                (nome_titular or "", "Titular / Representante legal"),
                ("", "Mercabiliza — recebido por"),
                estilos,
            ),
        ]),
    ]


def _aviso_pendencias(estilos, pendencias: tuple[str, ...]) -> list:
    """Caixa destacando o que falta — evita mandar ficha incompleta ao cliente."""
    if not pendencias:
        return []
    texto = "CAMPOS PENDENTES: " + "; ".join(pendencias) + "."
    tabela = Table([[Paragraph(escapar(texto), estilos["nota"])]],
                   colWidths=[LARGURA_UTIL])
    tabela.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#DC3250")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF0F2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [Spacer(1, 4 * mm), tabela]


# --------------------------------------------------------------------------- #
# Ficha preenchida                                                             #
# --------------------------------------------------------------------------- #
def _linhas_condicoes(parametros) -> list[tuple[str, str]]:
    """Condições comerciais acordadas, para o cliente confirmar junto do cadastro."""
    from ..core.contrato import data_extenso as _data
    from ..core.formatters import moeda

    linhas = [
        ("Objeto", parametros.objeto),
        ("Honorário mensal", moeda(parametros.valor_mensal)),
    ]
    if parametros.valor_implantacao > 0:
        linhas.append(("Taxa de implantação (única)",
                       moeda(parametros.valor_implantacao)))
    linhas += [
        ("Vencimento", f"dia {parametros.dia_vencimento} de cada mês"),
        ("Forma de pagamento", parametros.forma_pagamento),
        ("Início dos serviços", _data(parametros.data_inicio)),
        ("Vigência", f"{parametros.vigencia_meses} meses"
                     if parametros.vigencia_meses else "prazo indeterminado"),
        ("Reajuste anual", parametros.indice_reajuste),
    ]
    return linhas


def gerar_ficha_preenchida(
    contratante: ContratantePF | ContratantePJ,
    contratada: Contratada | None = None,
    parametros=None,
    incluir_pendencias: bool = True,
) -> bytes:
    """Ficha com os dados já levantados, para o cliente conferir e assinar.

    Quando ``parametros`` é informado, acrescenta a seção de condições
    comerciais — assim o cliente confirma cadastro e valores no mesmo
    documento, antes de o contrato ser emitido.
    """
    def fabrica() -> list:
        estilos = construir_estilos()
        eh_pj = isinstance(contratante, ContratantePJ)

        itens = _cabecalho(
            estilos, "FICHA CADASTRAL",
            f"{'Pessoa Jurídica' if eh_pj else 'Pessoa Física'} · "
            f"emitida em {data_extenso(date.today())}",
        )
        itens.append(_secao(
            estilos, "1. Identificação " + ("da empresa" if eh_pj else "do cliente")))
        itens.append(tabela_dados(contratante.linhas_ficha(), estilos))

        if eh_pj:
            itens.append(_secao(estilos, "2. Representante legal (signatário)"))
            itens.append(tabela_dados(contratante.linhas_representante(), estilos))

        if parametros is not None:
            itens.append(_secao(estilos,
                                f"{3 if eh_pj else 2}. Condições comerciais acordadas"))
            itens.append(tabela_dados(_linhas_condicoes(parametros), estilos))

        itens.append(Spacer(1, 3 * mm))
        itens.append(Paragraph(escapar(NOTA_ORIGEM), estilos["nota"]))

        if incluir_pendencias:
            itens.extend(_aviso_pendencias(estilos, contratante.pendencias))

        itens.extend(_bloco_declaracao(
            estilos, contratante.nome_exibicao,
            contratante.endereco.municipio,
        ))
        return itens

    return render_documento("Ficha Cadastral", contratante.nome_exibicao, fabrica)


# --------------------------------------------------------------------------- #
# Ficha em branco                                                              #
# --------------------------------------------------------------------------- #
def gerar_ficha_em_branco(
    tipo: str = "PF",
    incluir_operacao: bool = True,
    contratada: Contratada | None = None,
) -> bytes:
    """Ficha vazia para o cliente preencher.

    É o caminho correto quando **não há CNPJ para consultar**: não existe base
    pública de CPF, e consultar bureau privado exige base legal própria. Pedir
    ao titular é mais rápido, mais barato e juridicamente mais sólido — a
    assinatura na declaração de veracidade vale mais que qualquer consulta.
    """
    tipo = tipo.upper()

    def fabrica() -> list:
        estilos = construir_estilos()
        eh_pj = tipo == "PJ"

        itens = _cabecalho(
            estilos, "FICHA CADASTRAL",
            f"{'Pessoa Jurídica' if eh_pj else 'Pessoa Física'} · "
            "preenchimento pelo cliente",
        )
        itens.append(Paragraph(escapar(NOTA_EM_BRANCO), estilos["nota"]))
        itens.append(Spacer(1, 4 * mm))

        numero = 1
        itens.append(_secao(
            estilos,
            f"{numero}. Identificação " + ("da empresa" if eh_pj else "do cliente")))
        itens.append(_tabela_branco(
            CAMPOS_PJ_BRANCO if eh_pj else CAMPOS_PF_BRANCO, estilos))
        numero += 1

        if eh_pj:
            itens.append(_secao(
                estilos, f"{numero}. Representante legal (quem assina o contrato)"))
            itens.append(_tabela_branco(CAMPOS_REPRESENTANTE_BRANCO, estilos))
            numero += 1

        if incluir_operacao:
            itens.append(_secao(estilos, f"{numero}. Dados da operação"))
            itens.append(_tabela_branco(CAMPOS_OPERACAO_BRANCO, estilos))
            numero += 1

        itens.append(_secao(estilos, f"{numero}. Documentos a anexar"))
        for doc in _documentos_necessarios(eh_pj):
            itens.append(Paragraph(f"[  ] {escapar(doc)}", estilos["item"]))

        itens.extend(_bloco_declaracao(estilos, ""))
        return itens

    return render_documento(
        "Ficha Cadastral — preenchimento",
        "Pessoa Jurídica" if tipo == "PJ" else "Pessoa Física",
        fabrica,
    )


def _documentos_necessarios(eh_pj: bool) -> tuple[str, ...]:
    comuns = (
        "Cópia do RG e do CPF (ou CNH) do titular / representante legal",
        "Comprovante de residência do titular / representante (últimos 3 meses)",
        "Comprovante de conta bancária (para cadastro de pagamentos)",
    )
    if not eh_pj:
        return (
            *comuns,
            "Certidão de casamento, se casado(a)",
            ("Comprovante de atividade atual, se houver (contrato de locação, "
             "contrato de franquia, notas de compra de mercadoria)"),
        )
    return (
        *comuns,
        "Contrato social e última alteração consolidada (ou Certificado MEI)",
        "Cartão CNPJ atualizado",
        "Inscrição estadual e municipal, se houver",
        "Certificado digital e-CNPJ (A1 ou A3) ou procuração eletrônica e-CAC",
        "Últimos 3 DAS pagos e o último PGDAS-D transmitido",
        "Relatório de vendas por NCM/EAN do sistema de autoatendimento",
        "Balanço e DRE do último exercício, se houver",
    )
