"""Carta de Responsabilidade da Administração em PDF.

Reaproveita a engenharia de :mod:`pdf_juridico` — mesma fonte, mesmo timbrado,
mesma paginação do contrato. O que muda é **quem assina de que lado**.

⚠️ A ordem das assinaturas é invertida em relação ao contrato, e isso não é
detalhe: no contrato, a CONTRATADA assina à esquerda porque é quem propõe o
instrumento. Aqui quem declara é a **Administração da CONTRATANTE** — a
Mercabiliza assina à direita, e só para dar ciência do recebimento. Trocar os
lados transformaria uma declaração do cliente em algo que parece emitido pela
contabilidade, que é exatamente o contrário da função da carta.
"""

from __future__ import annotations

from ..core.carta import ParametrosCarta, renderizar_carta
from .pdf_juridico import (
    blocos_assinatura_contrato,
    construir_estilos,
    markdown_para_flowables,
    render_documento,
)


def gerar_carta_responsabilidade(
    contratante,
    parametros: ParametrosCarta,
) -> bytes:
    """Renderiza a carta do exercício e devolve o PDF em bytes."""
    texto = renderizar_carta(contratante, parametros)

    from ..config import (
        CONTRATADA_ASSINATURA_CNPJ,
        CONTRATADA_ASSINATURA_NOME,
        CONTRATADA_CRC_ORGANIZACAO,
    )

    representante = getattr(contratante, "representante", None)
    signatario = (getattr(representante, "nome", "") or "").strip() or getattr(
        contratante, "nome", ""
    )

    def fabrica() -> list:
        estilos = construir_estilos()
        assinaturas = blocos_assinatura_contrato(
            signatario,
            CONTRATADA_ASSINATURA_NOME,
            estilos,
            com_testemunhas=False,
            rotulo_esquerda="ADMINISTRAÇÃO DA CONTRATANTE",
            rotulo_direita=(
                f"CIÊNCIA / RECEBIMENTO\n"
                f"CNPJ: {CONTRATADA_ASSINATURA_CNPJ} | CRC/SP {CONTRATADA_CRC_ORGANIZACAO}"
            ),
        )
        return markdown_para_flowables(texto, estilos, assinaturas)

    return render_documento(
        f"Carta de Responsabilidade da Administração — {parametros.exercicio}",
        getattr(contratante, "nome_exibicao", ""),
        fabrica,
    )
