"""Papel timbrado: imagem de fundo em página inteira, com fallback.

## Como funciona

O timbrado oficial da Mercabiliza é uma imagem A4 (logo no topo, marca-d'água
da letra M ao fundo). Ela é desenhada **antes** do conteúdo, ocupando a página
inteira, e o texto flui por cima respeitando margens folgadas o suficiente para
não invadir o logo nem o rodapé do desenho.

## Regra de fallback

1. Existe `assets/timbrado/mercabiliza_a4.png`? Usa como fundo de todas as
   páginas.
2. Não existe, mas existe `assets/logo.png`? Desenha o logo no canto superior
   esquerdo com os dados institucionais ao lado.
3. Nenhum dos dois? Desenha a faixa colorida da marca. O documento nunca
   deixa de ser gerado por falta de imagem.

## Por que a imagem e não um PDF de fundo

Sobrepor PDFs (via pypdf/`merge_page`) funciona, mas exige uma segunda etapa
de composição depois do build e quebra a numeração "Página X de Y" que já
depende de duas passagens. Desenhar a imagem no `canvas` durante o build é uma
etapa só e o resultado impresso é idêntico — o timbrado é uma arte rasterizada
de qualquer forma.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from ..config import ASSETS_DIR, settings

logger = logging.getLogger(__name__)

TIMBRADO_DIR = ASSETS_DIR / "timbrado"
TIMBRADO_PADRAO = TIMBRADO_DIR / "mercabiliza_a4.png"
LOGO_PADRAO = ASSETS_DIR / "logo.png"


@dataclass(frozen=True, slots=True)
class Timbrado:
    """Configuração visual do documento.

    As margens existem para o texto não invadir a arte. Os valores padrão
    foram medidos sobre o timbrado da Mercabiliza: o logo ocupa os primeiros
    ~3,2 cm e a marca-d'água central é clara o bastante para texto passar por
    cima sem perder legibilidade.
    """

    imagem: Path | None = None
    margem_topo_mm: float = 34.0
    margem_base_mm: float = 22.0
    margem_lateral_mm: float = 22.0
    mostrar_rodape_texto: bool = True

    @property
    def tem_imagem(self) -> bool:
        return self.imagem is not None and self.imagem.exists()

    def desenhar(self, canvas, titulo_doc: str, pagina: int, total: int | str) -> None:
        """Pinta o fundo e o rodapé de uma página."""
        canvas.saveState()
        largura, altura = A4

        if self.tem_imagem:
            self._desenhar_imagem(canvas, largura, altura)
        elif LOGO_PADRAO.exists():
            self._desenhar_logo(canvas, largura, altura, titulo_doc)
        else:
            self._desenhar_faixa(canvas, largura, altura, titulo_doc)

        if self.mostrar_rodape_texto:
            self._desenhar_rodape(canvas, largura, pagina, total)
        canvas.restoreState()

    # ------------------------------------------------------------------ #
    def _desenhar_imagem(self, canvas, largura: float, altura: float) -> None:
        try:
            canvas.drawImage(str(self.imagem), 0, 0, width=largura, height=altura,
                             preserveAspectRatio=False, anchor="c", mask=None)
        except Exception:
            logger.warning("Timbrado %s não pôde ser desenhado.", self.imagem,
                           exc_info=True)
            self._desenhar_faixa(canvas, largura, altura, "")

    def _desenhar_logo(self, canvas, largura: float, altura: float,
                       titulo: str) -> None:
        from ..config import (
            CONTRATADA_EMAIL,
            CONTRATADA_NOME_FANTASIA,
            CONTRATADA_TELEFONE,
        )
        try:
            canvas.drawImage(str(LOGO_PADRAO), self.margem_lateral_mm * mm,
                             altura - 24 * mm, width=45 * mm, height=14 * mm,
                             preserveAspectRatio=True, anchor="sw", mask="auto")
        except Exception:
            logger.warning("Logo não pôde ser desenhada.", exc_info=True)

        canvas.setFillColor(colors.HexColor("#555B66"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(largura - self.margem_lateral_mm * mm,
                               altura - 15 * mm, CONTRATADA_NOME_FANTASIA)
        canvas.drawRightString(largura - self.margem_lateral_mm * mm,
                               altura - 19 * mm,
                               f"{CONTRATADA_TELEFONE} · {CONTRATADA_EMAIL}")
        canvas.setStrokeColor(colors.HexColor("#DDE1E6"))
        canvas.setLineWidth(0.5)
        canvas.line(self.margem_lateral_mm * mm, altura - 27 * mm,
                    largura - self.margem_lateral_mm * mm, altura - 27 * mm)

    def _desenhar_faixa(self, canvas, largura: float, altura: float,
                        titulo: str) -> None:
        from ..config import CONTRATADA_NOME_FANTASIA
        r, g, b = settings.emissor.cor_marca
        canvas.setFillColorRGB(r / 255, g / 255, b / 255)
        canvas.rect(0, altura - 12 * mm, largura, 12 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(self.margem_lateral_mm * mm, altura - 8 * mm,
                          CONTRATADA_NOME_FANTASIA.upper())
        if titulo:
            canvas.setFont("Helvetica", 7.5)
            canvas.drawRightString(largura - self.margem_lateral_mm * mm,
                                   altura - 8 * mm, titulo.upper()[:60])

    def _desenhar_rodape(self, canvas, largura: float, pagina: int,
                         total: int | str) -> None:
        canvas.setFillColor(colors.HexColor("#8A9099"))
        canvas.setFont("Helvetica", 7.5)
        y = 12 * mm
        canvas.drawRightString(largura - self.margem_lateral_mm * mm, y,
                               f"Página {pagina} de {total}")
        if not self.tem_imagem:
            # Com timbrado, o contato já está impresso na arte.
            from ..config import CONTRATADA_EMAIL, CONTRATADA_TELEFONE
            canvas.drawString(self.margem_lateral_mm * mm, y,
                              f"{CONTRATADA_EMAIL} · {CONTRATADA_TELEFONE}")


def timbrado_padrao(usar_timbrado: bool = True) -> Timbrado:
    """Timbrado oficial se o arquivo existir e o usuário quiser.

    ``usar_timbrado=False`` é útil para minuta de conferência interna: gasta
    menos tinta e deixa claro que não é a via final.
    """
    if usar_timbrado and TIMBRADO_PADRAO.exists():
        return Timbrado(imagem=TIMBRADO_PADRAO)
    return Timbrado(imagem=None, margem_topo_mm=30.0)


def listar_timbrados() -> list[Path]:
    """Permite ter mais de uma arte (contábil, RH, proposta)."""
    if not TIMBRADO_DIR.is_dir():
        return []
    return sorted(
        p for p in TIMBRADO_DIR.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
