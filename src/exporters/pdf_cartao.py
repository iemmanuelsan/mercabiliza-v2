"""Comprovante de Inscrição e de Situação Cadastral — leiaute da Receita.

## Por que existe um módulo só para isto

A versão anterior era uma lista de ``RÓTULO: valor`` em caixas de largura
inteira. Legível, mas não é o documento que o contador reconhece de relance:
o comprovante da Receita tem uma grade fixa, e a posição de cada campo é
parte da leitura. Quem confere "número de inscrição / matriz / data de
abertura" olha para o canto superior, não lê a página.

Este módulo reproduz essa grade — mesma ordem de campos, mesmos rótulos,
mesmos agrupamentos por linha.

## O que ele deliberadamente NÃO reproduz

Duas coisas do documento oficial ficam de fora, e a ausência é o ponto:

* a linha "Aprovado pela Instrução Normativa RFB nº 2.119" — afirmar
  aprovação normativa num papel que a Receita não emitiu seria falso;
* o brasão e a assinatura digital do órgão.

E entra uma tarja de origem, em vermelho, logo abaixo do título. O objetivo
é um documento que se **lê** como o comprovante, mas que ninguém confunde
**com** o comprovante. Se um dia esse arquivo aparecer num processo, tem que
estar escrito nele mesmo de onde ele veio.

## De onde vêm os dados

Das APIs públicas (BrasilAPI, CNPJ.ws, ReceitaWS), que espelham a base do
CNPJ com atraso variável. Campos que essas bases não entregam — EFR, motivo
de situação cadastral, situação especial — saem como ``********``, que é
exatamente o que o comprovante oficial imprime quando o campo é vazio.
"""

from __future__ import annotations

from datetime import datetime

from fpdf.enums import XPos, YPos

from ..core.cnpj import formatar as formatar_cnpj
from ..core.models import Empresa
from .pdf_base import DocumentoPDF

# Largura útil: A4 (210mm) menos as margens de 10mm.
LARGURA = 190.0

#: O que o comprovante oficial imprime em campo vazio.
VAZIO = "*" * 8


def _data_br(iso: str) -> str:
    """``2025-08-22`` → ``22/08/2025``.

    As APIs devolvem ISO; o comprovante usa o formato brasileiro. A versão
    anterior imprimia o ISO cru, que é a diferença que mais salta aos olhos
    de quem está acostumado com o documento.
    """
    texto = (iso or "").strip()
    if not texto:
        return VAZIO
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(texto[:19], formato).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return texto


def _telefone_br(texto: str) -> str:
    """``(19) 33270038`` → ``(19) 3327-0038``."""
    digitos = "".join(c for c in (texto or "") if c.isdigit())
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return texto or VAZIO


def _cep_br(cep: str) -> str:
    digitos = "".join(c for c in (cep or "") if c.isdigit())
    return f"{digitos[:2]}.{digitos[2:5]}-{digitos[5:]}" if len(digitos) == 8 else (cep or VAZIO)


class _Cartao(DocumentoPDF):
    """DocumentoPDF com o desenho de caixa rotulada do comprovante."""

    ROTULO = 6.5
    RECUO = 1.5

    def caixa(
        self,
        largura: float,
        rotulo: str,
        valor: object,
        *,
        fim_da_linha: bool = True,
        altura_valor: float = 5.0,
        centralizar: bool = False,
    ) -> None:
        """Uma célula do comprovante: rótulo pequeno em cima, valor embaixo.

        ``fim_da_linha=False`` deixa o cursor à direita, para a próxima caixa
        entrar na mesma linha — é assim que se montam as linhas de 2, 3 e 4
        colunas.
        """
        x, y = self.get_x(), self.get_y()
        altura = self.ROTULO + altura_valor
        self.rect(x, y, largura, altura)

        alinhamento = "C" if centralizar else "L"

        self.set_xy(x + self.RECUO, y + 0.8)
        self.fonte("", 6)
        self.cell(largura - 2 * self.RECUO, 3, self.txt(rotulo), align=alinhamento)

        self.set_xy(x + self.RECUO, y + self.ROTULO - 1)
        self.fonte("B", 8)
        self.cell(
            largura - 2 * self.RECUO,
            altura_valor,
            self.txt(valor),
            align=alinhamento,
        )

        if fim_da_linha:
            self.set_xy(self.l_margin, y + altura)
        else:
            self.set_xy(x + largura, y)

    def cabecalho_tripartite(self, cnpj: str, matriz_filial: str, abertura: str) -> None:
        """A primeira faixa do comprovante: três colunas de altura dupla.

        Não dá para montar com ``caixa()``: as três colunas têm alturas
        iguais mas conteúdos de números de linhas diferentes — a da esquerda
        traz inscrição E a marcação MATRIZ, a do meio traz o título do
        documento em duas linhas centralizadas verticalmente, e a da direita
        traz só a data. Tentar empilhar caixas deixa um retângulo vazio
        sobrando à direita da MATRIZ, e o título estoura a coluna do meio e
        invade a data.
        """
        x0, y0 = self.get_x(), self.get_y()
        altura = 16.0
        larguras = (LARGURA * 0.30, LARGURA * 0.44, LARGURA * 0.26)

        x = x0
        for largura in larguras:
            self.rect(x, y0, largura, altura)
            x += largura

        # ---- coluna 1: inscrição + matriz/filial
        self.set_xy(x0 + self.RECUO, y0 + 0.8)
        self.fonte("", 6)
        self.cell(larguras[0], 3, self.txt("NÚMERO DE INSCRIÇÃO"))
        self.set_xy(x0 + self.RECUO, y0 + 4.5)
        self.fonte("B", 9)
        self.cell(larguras[0], 4, self.txt(cnpj))
        self.set_xy(x0 + self.RECUO, y0 + 10.5)
        self.fonte("B", 8)
        self.cell(larguras[0], 4, self.txt(matriz_filial))

        # ---- coluna 2: título, duas linhas centralizadas
        meio_x = x0 + larguras[0]
        self.fonte("B", 9)
        self.set_xy(meio_x, y0 + 4.0)
        self.cell(larguras[1], 4, self.txt("COMPROVANTE DE INSCRIÇÃO E DE"), align="C")
        self.set_xy(meio_x, y0 + 8.5)
        self.cell(larguras[1], 4, self.txt("SITUAÇÃO CADASTRAL"), align="C")

        # ---- coluna 3: data de abertura
        dir_x = meio_x + larguras[1]
        self.set_xy(dir_x + self.RECUO, y0 + 0.8)
        self.fonte("", 6)
        self.cell(larguras[2], 3, self.txt("DATA DE ABERTURA"))
        self.set_xy(dir_x + self.RECUO, y0 + 4.5)
        self.fonte("B", 9)
        self.cell(larguras[2], 4, self.txt(abertura))

        self.set_xy(self.l_margin, y0 + altura)

    def _cortar(self, texto: str, largura: float) -> str:
        """Corta o texto para caber em UMA linha da largura dada.

        ⚠️ Isto não é capricho: ``multi_cell`` **não recorta** ao chegar na
        altura reservada, ele continua desenhando por cima do que vier
        abaixo. Uma empresa de minimercado com 12 CNAEs secundários fazia a
        lista escorrer por dentro das caixas de natureza jurídica e
        logradouro — e a página continuava sendo uma só, então nem a
        contagem de páginas denunciava. Só olhando o PDF renderizado.
        """
        limpo = self.txt(texto)
        if self.get_string_width(limpo) <= largura:
            return limpo
        while limpo and self.get_string_width(limpo + "…") > largura:
            limpo = limpo[:-1]
        return limpo + "…"

    def caixa_lista(
        self, largura: float, rotulo: str, itens: list[str], maximo: int = 8
    ) -> None:
        """Caixa de altura previsível para uma lista — atividades secundárias.

        Cada item ocupa exatamente uma linha (cortado se preciso) e a lista
        inteira é limitada a ``maximo`` linhas. Numa grade, caixa que cresce
        com o conteúdo empurra tudo abaixo dela e o documento deixa de ser
        reconhecível; pior, transborda por cima.

        O que não coube vira uma linha final dizendo quantos ficaram de fora
        — silenciar a diferença seria pior do que exibir menos.
        """
        linhas = list(itens) or ["Não informada"]
        if len(linhas) > maximo:
            sobra = len(linhas) - (maximo - 1)
            linhas = linhas[: maximo - 1] + [
                f"(+{sobra} atividade(s) — lista completa no dossiê)"
            ]

        x, y = self.get_x(), self.get_y()
        altura = self.ROTULO + 3.6 * len(linhas)
        self.rect(x, y, largura, altura)

        self.set_xy(x + self.RECUO, y + 0.8)
        self.fonte("", 6)
        self.cell(largura - 2 * self.RECUO, 3, self.txt(rotulo))

        self.fonte("B", 7)
        util = largura - 2 * self.RECUO
        for indice, item in enumerate(linhas):
            self.set_xy(x + self.RECUO, y + self.ROTULO - 1.2 + 3.6 * indice)
            self.cell(util, 3.6, self._cortar(item, util))

        self.set_xy(self.l_margin, y + altura)


def gerar_cartao_cnpj(empresa: Empresa) -> bytes:
    """Comprovante de Inscrição e de Situação Cadastral, em PDF."""
    pdf = _Cartao()
    pdf.add_page()

    # ---- Cabeçalho -------------------------------------------------- #
    pdf.fonte("B", 10)
    pdf.linha(5, "REPÚBLICA FEDERATIVA DO BRASIL", align="C")
    pdf.fonte("B", 11)
    pdf.linha(6, "CADASTRO NACIONAL DA PESSOA JURÍDICA", align="C")

    # A tarja fica AQUI, e não no rodapé, de propósito: quem recebe o papel
    # lê o topo. No rodapé, uma cópia cortada esconderia a origem.
    pdf.set_text_color(178, 34, 34)
    pdf.fonte("B", 7)
    pdf.linha(
        4,
        "REPRODUÇÃO A PARTIR DE BASES PÚBLICAS — NÃO É O COMPROVANTE OFICIAL DA RECEITA FEDERAL",
        align="C",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1.5)

    # ---- Linha 1: inscrição | título | abertura ---------------------- #
    pdf.cabecalho_tripartite(
        formatar_cnpj(empresa.cnpj),
        empresa.matriz_filial,
        _data_br(empresa.data_abertura),
    )

    # ---- Identificação ----------------------------------------------- #
    pdf.caixa(LARGURA, "NOME EMPRESARIAL", empresa.razao_social or VAZIO)

    pdf.caixa(
        LARGURA * 0.72,
        "TÍTULO DO ESTABELECIMENTO (NOME DE FANTASIA)",
        empresa.nome_fantasia or VAZIO,
        fim_da_linha=False,
    )
    pdf.caixa(LARGURA * 0.28, "PORTE", empresa.porte or VAZIO)

    # ---- Atividades --------------------------------------------------- #
    pdf.caixa_lista(
        LARGURA,
        "CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÔMICA PRINCIPAL",
        [empresa.cnae_principal_str or VAZIO],
        maximo=1,
    )

    pdf.caixa_lista(
        LARGURA,
        "CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS",
        [str(a) for a in empresa.atividades_secundarias],
        maximo=9,
    )

    pdf.caixa(
        LARGURA,
        "CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA",
        empresa.natureza_juridica or VAZIO,
    )

    # ---- Endereço ------------------------------------------------------ #
    endereco = empresa.endereco
    pdf.caixa(LARGURA * 0.58, "LOGRADOURO", endereco.logradouro or VAZIO, fim_da_linha=False)
    pdf.caixa(LARGURA * 0.14, "NÚMERO", endereco.numero or VAZIO, fim_da_linha=False)
    pdf.caixa(LARGURA * 0.28, "COMPLEMENTO", endereco.complemento_limpo or VAZIO)

    pdf.caixa(LARGURA * 0.18, "CEP", _cep_br(endereco.cep), fim_da_linha=False)
    pdf.caixa(
        LARGURA * 0.34, "BAIRRO/DISTRITO", endereco.bairro or VAZIO, fim_da_linha=False
    )
    pdf.caixa(LARGURA * 0.36, "MUNICÍPIO", endereco.municipio or VAZIO, fim_da_linha=False)
    pdf.caixa(LARGURA * 0.12, "UF", endereco.uf or VAZIO)

    pdf.caixa(
        LARGURA * 0.66,
        "ENDEREÇO ELETRÔNICO",
        empresa.email_str or VAZIO,
        fim_da_linha=False,
    )
    pdf.caixa(LARGURA * 0.34, "TELEFONE", _telefone_br(empresa.telefone_str))

    # EFR não vem de nenhuma das três APIs. Sai vazio, como no original de
    # quem não é órgão público — e não como "não informado", que sugeriria
    # falha de consulta.
    pdf.caixa(LARGURA, "ENTE FEDERATIVO RESPONSÁVEL (EFR)", VAZIO)

    # ---- Situação ------------------------------------------------------ #
    pdf.caixa(
        LARGURA * 0.62,
        "SITUAÇÃO CADASTRAL",
        empresa.situacao.situacao_receita or VAZIO,
        fim_da_linha=False,
    )
    pdf.caixa(
        LARGURA * 0.38,
        "DATA DA SITUAÇÃO CADASTRAL",
        _data_br(empresa.situacao.data_situacao),
    )

    pdf.caixa(LARGURA, "MOTIVO DE SITUAÇÃO CADASTRAL", VAZIO)

    pdf.caixa(
        LARGURA * 0.62, "SITUAÇÃO ESPECIAL", VAZIO, fim_da_linha=False
    )
    pdf.caixa(LARGURA * 0.38, "DATA DA SITUAÇÃO ESPECIAL", VAZIO)

    # ---- Procedência --------------------------------------------------- #
    pdf.ln(3)
    pdf.fonte("", 7)
    fontes = ", ".join(empresa.fontes) or "bases públicas"
    pdf.paragrafo(
        3.6,
        f"Documento gerado pela Mercabiliza em {datetime.now():%d/%m/%Y às %H:%M} a partir de "
        f"{fontes}. Essas bases espelham o CNPJ com atraso variável, então divergências com a "
        "situação do dia são possíveis. Para efeito de prova, use o comprovante emitido no site "
        "da Receita Federal.",
    )

    return pdf.bytes()
