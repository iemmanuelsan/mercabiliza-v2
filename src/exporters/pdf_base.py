"""Infraestrutura comum de PDF.

[CORRIGIDO] A versão anterior rodava ``tratar_texto_pdf`` em tudo, trocando
'ç'->'c' e 'ã'->'a'. Uma proposta comercial saía escrita "PROPOSTA DE
PRESTACAO DE SERVICOS CONTABEIS" — péssimo para um documento que vai ao
cliente. Aqui registramos uma fonte TrueType Unicode (DejaVu, presente na
maioria das imagens Linux e instalável via pip) e só caímos na transliteração
se ela realmente não existir.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from ..config import ASSETS_DIR
from ..core.formatters import sem_acento

logger = logging.getLogger(__name__)

_CAMINHOS_DEJAVU = (
    ASSETS_DIR / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path("/Library/Fonts/DejaVuSans.ttf"),
)
_CAMINHOS_DEJAVU_BOLD = (
    ASSETS_DIR / "fonts" / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    Path("/Library/Fonts/DejaVuSans-Bold.ttf"),
)


def _primeira_existente(caminhos) -> Path | None:
    return next((c for c in caminhos if c.exists()), None)


# Blocos Unicode de emoji, símbolos e pictogramas.
_FAIXAS_EMOJI = (
    (0x1F300, 0x1FAFF),   # pictogramas, emoticons, símbolos suplementares
    (0x2190, 0x21FF),     # setas
    (0x2600, 0x27BF),     # símbolos diversos e dingbats
    (0x2B00, 0x2BFF),     # símbolos e setas adicionais
    (0xFE00, 0xFE0F),     # seletores de variação (o "️" invisível pós-emoji)
)


def _sem_emoji(texto: str) -> str:
    limpo = "".join(
        c for c in texto
        if not any(inicio <= ord(c) <= fim for inicio, fim in _FAIXAS_EMOJI)
    )
    # Colapsa espaços duplos deixados pela remoção, PRESERVANDO as quebras de
    # linha — o multi_cell depende delas para separar os tópicos das dicas.
    return "\n".join(" ".join(linha.split()) for linha in limpo.split("\n"))


class DocumentoPDF(FPDF):
    """FPDF com suporte a UTF-8 e helpers que evitam a API depreciada ``ln=``."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(10, 10, 10)
        self.unicode = False
        self._registrar_fonte()

    def _registrar_fonte(self) -> None:
        regular = _primeira_existente(_CAMINHOS_DEJAVU)
        bold = _primeira_existente(_CAMINHOS_DEJAVU_BOLD)
        if regular:
            self.add_font("DejaVu", "", str(regular))
            self.add_font("DejaVu", "B", str(bold or regular))
            self.add_font("DejaVu", "I", str(regular))
            self.familia = "DejaVu"
            self.unicode = True
        else:
            logger.warning(
                "Fonte DejaVu não encontrada — PDFs sairão sem acentuação. "
                "Rode: pip install fonttools && coloque DejaVuSans.ttf em assets/fonts/"
            )
            self.familia = "Helvetica"

    # ------------------------------------------------------------------ #
    def txt(self, valor: object) -> str:
        """Prepara o texto conforme a fonte disponível.

        Emojis são removidos sempre: nem a DejaVu nem a Helvetica possuem
        esses glifos, e o fpdf2 os renderiza como caixas vazias além de
        poluir o log com avisos de "missing glyph". Acentos, esses sim, são
        preservados quando a fonte Unicode está disponível.
        """
        texto = _sem_emoji("" if valor is None else str(valor))
        return texto if self.unicode else sem_acento(texto)

    def fonte(self, estilo: str = "", tamanho: int = 9) -> None:
        self.set_font(self.familia, estilo, tamanho)

    def linha(self, altura: float, texto: object, **kwargs) -> None:
        """Substitui ``cell(..., ln=True)``, depreciado no fpdf2 ≥ 2.7.6."""
        self.cell(kwargs.pop("largura", 0), altura, self.txt(texto),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kwargs)

    def paragrafo(self, altura: float, texto: object, **kwargs) -> None:
        """Bloco de texto com quebra automática.

        ``new_x=LMARGIN`` é obrigatório: o padrão do fpdf2 para ``multi_cell``
        é ``XPos.RIGHT``, que com largura 0 (até a margem direita) deixa o
        cursor encostado na borda — o parágrafo seguinte então falha com
        "Not enough horizontal space to render a single character".
        """
        self.multi_cell(kwargs.pop("largura", 0), altura, self.txt(texto),
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kwargs)

    def secao(self, titulo: str, tamanho: int = 10) -> None:
        self.fonte("B", tamanho)
        self.set_fill_color(240, 240, 240)
        self.linha(6, titulo, fill=True)
        self.fonte("", 9)

    def bytes(self) -> bytes:
        saida = self.output()
        return bytes(saida) if isinstance(saida, (bytes, bytearray)) \
            else bytes(saida, encoding="latin-1")
