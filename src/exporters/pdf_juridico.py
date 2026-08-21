"""Engine de PDF para documentos jurídicos, com ReportLab Platypus.

## Por que ReportLab aqui e fpdf2 no resto do projeto

Não é inconsistência — são problemas diferentes:

* O dossiê e a proposta são **documentos de layout fixo**: sei exatamente
  quais campos existem e onde ficam. O fpdf2 resolve com pouco código.
* Contrato é **texto corrido de tamanho imprevisível**: o número de cláusulas
  e o comprimento da qualificação das partes variam por cliente. Isso exige
  parágrafo justificado com quebra automática, controle de viúvas e órfãs,
  blocos de assinatura que não podem partir entre páginas e numeração
  "Página X de Y" (que só é possível saber depois de paginar tudo). O
  Platypus do ReportLab faz isso nativamente; no fpdf2 seria manual e frágil.

WeasyPrint faria um trabalho ainda melhor de tipografia, mas depende de
bibliotecas de sistema (cairo, pango) que tornam o deploy no Streamlit Cloud
instável. ReportLab é Python puro com wheels prontas — instala e funciona.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable, Iterable, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..config import (
    ASSETS_DIR,
    settings,
)
from .pdf_base import _CAMINHOS_DEJAVU, _CAMINHOS_DEJAVU_BOLD, _primeira_existente
from .timbrado import Timbrado, timbrado_padrao

logger = logging.getLogger(__name__)

MARGEM = 20 * mm
MARGEM_TOPO = 26 * mm
MARGEM_RODAPE = 18 * mm
LARGURA_UTIL = A4[0] - 2 * MARGEM

MARCADOR_ASSINATURAS = "[[ASSINATURAS]]"
MARCADOR_QUEBRA = "[[QUEBRA]]"


# --------------------------------------------------------------------------- #
# Fontes                                                                       #
# --------------------------------------------------------------------------- #
_FONTES_REGISTRADAS = False
FONTE_NORMAL = "Helvetica"
FONTE_BOLD = "Helvetica-Bold"


def registrar_fontes() -> tuple[str, str]:
    """Registra a DejaVu quando disponível; cai para Helvetica se não estiver.

    Helvetica é uma das 14 fontes-base do PDF e cobre Latin-1, então acentos
    em português funcionam nos dois casos. A DejaVu é preferida por cobrir
    mais símbolos (§, —, ≥) sem risco de caractere faltando.
    """
    global _FONTES_REGISTRADAS, FONTE_NORMAL, FONTE_BOLD
    if _FONTES_REGISTRADAS:
        return FONTE_NORMAL, FONTE_BOLD

    regular = _primeira_existente(_CAMINHOS_DEJAVU)
    bold = _primeira_existente(_CAMINHOS_DEJAVU_BOLD)
    if regular:
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", str(regular)))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold or regular)))
            # SEM ISTO O <b> NÃO FUNCIONA. Para as 14 fontes-base o ReportLab
            # deduz a variante bold pelo nome; para TTF registrada é preciso
            # declarar a família explicitamente. Sem a chamada abaixo, o
            # negrito inline dos dados identificadores do contrato era
            # silenciosamente ignorado — o texto saía todo normal.
            pdfmetrics.registerFontFamily(
                "DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                italic="DejaVu", boldItalic="DejaVu-Bold",
            )
            FONTE_NORMAL, FONTE_BOLD = "DejaVu", "DejaVu-Bold"
        except Exception:
            logger.warning("Falha ao registrar DejaVu; usando Helvetica.",
                           exc_info=True)
    else:
        logger.info("DejaVu não encontrada; usando Helvetica (Latin-1).")

    _FONTES_REGISTRADAS = True
    return FONTE_NORMAL, FONTE_BOLD


# --------------------------------------------------------------------------- #
# Estilos                                                                      #
# --------------------------------------------------------------------------- #
def construir_estilos() -> dict[str, ParagraphStyle]:
    normal, bold = registrar_fontes()
    base = getSampleStyleSheet()

    return {
        "titulo": ParagraphStyle(
            "titulo", parent=base["Normal"], fontName=bold, fontSize=13,
            leading=17, alignment=TA_CENTER, spaceAfter=10, spaceBefore=2,
            textColor=colors.HexColor("#1A1D23"),
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo", parent=base["Normal"], fontName=normal, fontSize=9,
            leading=12, alignment=TA_CENTER, spaceAfter=12,
            textColor=colors.HexColor("#555B66"),
        ),
        "clausula": ParagraphStyle(
            "clausula", parent=base["Normal"], fontName=bold, fontSize=10,
            leading=14, alignment=TA_CENTER, spaceBefore=12, spaceAfter=6,
            textColor=colors.HexColor("#1A1D23"),
            keepWithNext=1,   # nunca deixa o título só no fim da página
        ),
        "corpo": ParagraphStyle(
            "corpo", parent=base["Normal"], fontName=normal, fontSize=10,
            leading=14.5, alignment=TA_JUSTIFY, spaceAfter=7, firstLineIndent=0,
        ),
        "paragrafo": ParagraphStyle(
            "paragrafo", parent=base["Normal"], fontName=normal, fontSize=10,
            leading=14.5, alignment=TA_JUSTIFY, spaceAfter=7,
            leftIndent=10 * mm, firstLineIndent=0,
        ),
        "item": ParagraphStyle(
            "item", parent=base["Normal"], fontName=normal, fontSize=10,
            leading=14, alignment=TA_JUSTIFY, spaceAfter=4,
            leftIndent=8 * mm, bulletIndent=3 * mm,
        ),
        "item_alfa": ParagraphStyle(
            "item_alfa", parent=base["Normal"], fontName=normal, fontSize=10,
            leading=14, alignment=TA_JUSTIFY, spaceAfter=3,
            leftIndent=10 * mm, firstLineIndent=-5 * mm,
        ),
        "secao": ParagraphStyle(
            "secao", parent=base["Normal"], fontName=bold, fontSize=10,
            leading=13, spaceBefore=10, spaceAfter=5, keepWithNext=1,
            textColor=colors.HexColor("#1A1D23"),
        ),
        "celula_rotulo": ParagraphStyle(
            "celula_rotulo", parent=base["Normal"], fontName=bold, fontSize=8.5,
            leading=11,
        ),
        "celula_valor": ParagraphStyle(
            "celula_valor", parent=base["Normal"], fontName=normal, fontSize=8.5,
            leading=11,
        ),
        "assinatura": ParagraphStyle(
            "assinatura", parent=base["Normal"], fontName=normal, fontSize=8.5,
            leading=11, alignment=TA_CENTER,
        ),
        "assinatura_nome": ParagraphStyle(
            "assinatura_nome", parent=base["Normal"], fontName=bold, fontSize=8.5,
            leading=11, alignment=TA_CENTER,
        ),
        "nota": ParagraphStyle(
            "nota", parent=base["Normal"], fontName=normal, fontSize=7.5,
            leading=10, alignment=TA_JUSTIFY, textColor=colors.HexColor("#555B66"),
        ),
        "rodape": ParagraphStyle(
            "rodape", parent=base["Normal"], fontName=normal, fontSize=7.5,
            leading=9, alignment=TA_RIGHT, textColor=colors.HexColor("#8A9099"),
        ),
    }


# --------------------------------------------------------------------------- #
# Documento com "Página X de Y"                                                #
# --------------------------------------------------------------------------- #
class DocumentoJuridico(BaseDocTemplate):
    """Template A4 com faixa da marca no topo e rodapé paginado.

    A numeração "Página X de Y" exige duas passagens: o total de páginas só é
    conhecido depois de paginar tudo. O ReportLab resolve isso com
    ``multiBuild`` + um contador guardado no próprio documento.
    """

    def __init__(self, buffer: io.BytesIO, titulo: str, subtitulo: str = "",
                 timbrado: Timbrado | None = None) -> None:
        # As margens vêm do timbrado: a arte define quanto espaço o texto tem
        # sem invadir o logo no topo nem o rodapé impresso.
        self.timbrado = timbrado if timbrado is not None else timbrado_padrao()
        margem_lat = self.timbrado.margem_lateral_mm * mm
        super().__init__(
            buffer, pagesize=A4,
            leftMargin=margem_lat, rightMargin=margem_lat,
            topMargin=self.timbrado.margem_topo_mm * mm,
            bottomMargin=self.timbrado.margem_base_mm * mm,
            title=titulo, author=settings.emissor.nome,
            subject=subtitulo, creator="Mercabiliza — Onboarding Contábil",
        )
        self.titulo_doc = titulo
        self.subtitulo_doc = subtitulo
        self.total_paginas = 0
        self._estilos = construir_estilos()

        frame = Frame(
            self.leftMargin, self.bottomMargin,
            self.width, self.height, id="corpo",
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self.addPageTemplates([
            PageTemplate(id="padrao", frames=[frame], onPage=self._decorar_pagina)
        ])

    # ------------------------------------------------------------------ #
    def afterFlowable(self, flowable) -> None:
        pass

    def _decorar_pagina(self, canvas, doc) -> None:
        """Delega o visual ao :class:`Timbrado` — fundo, cabeçalho e rodapé."""
        self.timbrado.desenhar(
            canvas, self.titulo_doc, doc.page, self.total_paginas or "?")

    def gerar(self, flowables: Sequence) -> None:
        """Build em duas passagens para fixar o total de páginas."""
        # 1ª passagem: descobre o total.
        self.multiBuild(list(flowables))


def render_documento(titulo: str, subtitulo: str, fabrica: Callable[[], list],
                     timbrado: Timbrado | None = None) -> bytes:
    """Renderiza em duas passagens: a primeira conta páginas, a segunda numera.

    Sem as duas passagens o rodapé mostraria "Página 1 de ?" — o ReportLab só
    conhece o total depois de paginar tudo.

    ``fabrica`` é um callable **sem argumentos** que devolve uma lista NOVA de
    flowables a cada chamada. Isso não é preciosismo: o Platypus consome e
    muta os flowables durante o build, então reaproveitar a mesma lista na
    segunda passagem produz um PDF corrompido ou vazio.
    """
    contador = io.BytesIO()
    doc_contagem = DocumentoJuridico(contador, titulo, subtitulo, timbrado)
    doc_contagem.gerar(fabrica())
    total = doc_contagem.page

    saida = io.BytesIO()
    doc = DocumentoJuridico(saida, titulo, subtitulo, timbrado)
    doc.total_paginas = total
    doc.gerar(fabrica())
    return saida.getvalue()


# --------------------------------------------------------------------------- #
# Conversão do markdown simplificado em flowables                              #
# --------------------------------------------------------------------------- #
_ESCAPES = ((("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")))


def escapar(texto: str) -> str:
    """O Platypus interpreta um mini-HTML nos parágrafos — dados vindos de
    API precisam ser escapados para não quebrar a marcação (ou injetar tags)."""
    for alvo, subst in _ESCAPES:
        texto = texto.replace(alvo, subst)
    return texto


_NEGRITO = re.compile(r"\*\*(.+?)\*\*")
_ITEM_ALFA = re.compile(r"^[a-z]\)\s")


def _inline(texto: str) -> str:
    """Escapa e converte ``**negrito**`` na tag que o Platypus entende."""
    return _NEGRITO.sub(r"<b>\1</b>", escapar(texto))


def markdown_para_flowables(
    texto: str, estilos: dict[str, ParagraphStyle],
    blocos_assinatura: Iterable | None = None,
) -> list:
    """Converte a minuta renderizada em flowables do Platypus.

    Convenções reconhecidas (documentadas no cabeçalho do template):
      ``## Título``      título de cláusula
      ``- item``         item de lista com marcador
      ``§ texto``        parágrafo com recuo
      ``[[ASSINATURAS]]``insere os blocos de assinatura
      ``[[QUEBRA]]``     quebra de página
    """
    flowables: list = []
    primeiro_titulo = True

    for bruto in texto.split("\n"):
        linha = bruto.strip()

        if not linha:
            continue

        if linha == MARCADOR_QUEBRA:
            flowables.append(PageBreak())
            continue

        if linha == MARCADOR_ASSINATURAS:
            flowables.extend(blocos_assinatura or [])
            continue

        if linha.startswith("### "):
            flowables.append(Paragraph(_inline(linha[4:].strip()),
                                       estilos["secao"]))
            continue

        # Itens alfabéticos do contrato ("a) ...", "b) ...") viram parágrafos
        # recuados: preservam a letra original, que é citada em outras
        # cláusulas ("conforme item 4.6, alínea c").
        if _ITEM_ALFA.match(linha):
            flowables.append(Paragraph(_inline(linha), estilos["item_alfa"]))
            continue

        if linha.startswith("## "):
            conteudo = linha[3:].strip()
            estilo = "titulo" if primeiro_titulo else "clausula"
            flowables.append(Paragraph(_inline(conteudo), estilos[estilo]))
            primeiro_titulo = False
            continue

        if linha.startswith("- "):
            flowables.append(Paragraph(_inline(linha[2:].strip()),
                                       estilos["item"], bulletText="•"))
            continue

        if linha.startswith("§"):
            conteudo = linha.lstrip("§").strip()
            flowables.append(
                Paragraph(f"<b>Parágrafo.</b> {_inline(conteudo)}",
                          estilos["paragrafo"]))
            continue

        flowables.append(Paragraph(_inline(linha), estilos["corpo"]))

    return flowables


# --------------------------------------------------------------------------- #
# Componentes reutilizáveis                                                    #
# --------------------------------------------------------------------------- #
def tabela_dados(
    linhas: Sequence[tuple[str, str]], estilos: dict[str, ParagraphStyle],
    largura_rotulo: float = 0.32,
) -> Table:
    """Tabela rótulo/valor com zebra, para fichas cadastrais."""
    dados = [
        [Paragraph(escapar(rotulo), estilos["celula_rotulo"]),
         Paragraph(escapar(str(valor)), estilos["celula_valor"])]
        for rotulo, valor in linhas
    ]
    tabela = Table(
        dados,
        colWidths=[LARGURA_UTIL * largura_rotulo,
                   LARGURA_UTIL * (1 - largura_rotulo)],
        hAlign="LEFT",
    )
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE1E6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F6F8")),
    ]
    for i in range(len(dados)):
        if i % 2:
            estilo.append(("BACKGROUND", (1, i), (1, i), colors.HexColor("#FAFBFC")))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def bloco_assinatura_dupla(
    esquerda: tuple[str, str], direita: tuple[str, str],
    estilos: dict[str, ParagraphStyle],
) -> KeepTogether:
    """Duas assinaturas lado a lado. ``KeepTogether`` impede que a linha de
    assinatura fique numa página e o nome na seguinte."""
    def celula(par: tuple[str, str]) -> list:
        nome, papel = par
        linhas = [
            Paragraph("_" * 42, estilos["assinatura"]),
            Paragraph(escapar(nome or " "), estilos["assinatura_nome"]),
        ]
        # "\n" no rótulo vira linha extra (usado para o CNPJ da parte).
        linhas += [Paragraph(escapar(linha), estilos["assinatura"])
                   for linha in str(papel).split("\n") if linha]
        return linhas

    tabela = Table(
        [[celula(esquerda), celula(direita)]],
        colWidths=[LARGURA_UTIL / 2, LARGURA_UTIL / 2],
        hAlign="CENTER",
    )
    tabela.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return KeepTogether([Spacer(1, 10 * mm), tabela])


def blocos_assinatura_contrato(
    nome_esquerda: str, nome_direita: str,
    estilos: dict[str, ParagraphStyle], com_testemunhas: bool = True,
    rotulo_esquerda: str = "CONTRATADA", rotulo_direita: str = "CONTRATANTE",
) -> list:
    """Assinaturas das partes e, opcionalmente, de duas testemunhas.

    A ordem segue o contrato modelo: CONTRATADA à esquerda, CONTRATANTE à
    direita. Os rótulos aceitam ``\n`` para levar o CNPJ na linha de baixo.
    """
    itens: list = [
        bloco_assinatura_dupla(
            (nome_esquerda, rotulo_esquerda),
            (nome_direita, rotulo_direita),
            estilos,
        )
    ]
    if com_testemunhas:
        itens.append(KeepTogether([
            Spacer(1, 6 * mm),
            Paragraph("Testemunhas:", estilos["secao"]),
            Table(
                [[
                    [Paragraph("_" * 42, estilos["assinatura"]),
                     Paragraph("Nome:", estilos["assinatura"]),
                     Paragraph("CPF:", estilos["assinatura"])],
                    [Paragraph("_" * 42, estilos["assinatura"]),
                     Paragraph("Nome:", estilos["assinatura"]),
                     Paragraph("CPF:", estilos["assinatura"])],
                ]],
                colWidths=[LARGURA_UTIL / 2, LARGURA_UTIL / 2],
                style=TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ]),
            ),
        ]))
    return itens


def logo_flowable() -> object | None:
    """Carrega ``assets/logo.png`` se existir. Sem logo, o documento sai só
    com a faixa colorida — não quebra."""
    from reportlab.platypus import Image

    caminho = ASSETS_DIR / "logo.png"
    if not caminho.exists():
        return None
    try:
        img = Image(str(caminho))
        proporcao = img.imageHeight / img.imageWidth
        img.drawWidth = 42 * mm
        img.drawHeight = 42 * mm * proporcao
        img.hAlign = "LEFT"
        return img
    except Exception:
        logger.warning("Logo em %s não pôde ser carregada.", caminho, exc_info=True)
        return None
