"""Contrato de prestação de serviços em PDF.

O texto vem da minuta em ``templates/`` (Jinja2) e é convertido em flowables
do Platypus. A engenharia está em :mod:`pdf_juridico`; aqui só se monta a
sequência do documento e os blocos de assinatura.
"""

from __future__ import annotations

from ..core.contrato import ParametrosContrato, renderizar_minuta
from ..core.pessoas import Contratada, ContratantePF, ContratantePJ
from .pdf_juridico import (
    blocos_assinatura_contrato,
    construir_estilos,
    markdown_para_flowables,
    render_documento,
)


def gerar_contrato(
    contratante: ContratantePF | ContratantePJ,
    contratada: Contratada,
    parametros: ParametrosContrato,
    com_testemunhas: bool = True,
    template: str | None = None,
) -> bytes:
    """Renderiza a minuta e devolve o PDF em bytes.

    O nome que vai sob a linha de assinatura da CONTRATANTE é o do
    **signatário**, não o da empresa: quem assina é pessoa natural. Para PJ
    isso é o representante legal; para PF, o próprio titular.
    """
    kwargs_minuta = {"template": template} if template else {}
    texto = renderizar_minuta(contratante, contratada, parametros, **kwargs_minuta)

    if isinstance(contratante, ContratantePJ):
        signatario_contratante = (
            contratante.representante.nome or contratante.razao_social
        )
    else:
        signatario_contratante = contratante.nome

    # A CONTRATADA assina pela razão social + CNPJ, sem nomear pessoa física
    # — decisão de negócio refletida no contrato modelo.
    from ..config import CONTRATADA_ASSINATURA_CNPJ, CONTRATADA_ASSINATURA_NOME
    signatario_contratada = CONTRATADA_ASSINATURA_NOME
    cnpj_contratada = CONTRATADA_ASSINATURA_CNPJ

    def fabrica() -> list:
        estilos = construir_estilos()
        rotulo_contratante = (
            f"CONTRATANTE\nCNPJ: {contratante.documento_principal}"
            if isinstance(contratante, ContratantePJ)
            else f"CONTRATANTE\nCPF: {contratante.documento_principal}"
        )
        assinaturas = blocos_assinatura_contrato(
            signatario_contratada, signatario_contratante,
            estilos, com_testemunhas=com_testemunhas,
            rotulo_esquerda=f"CONTRATADA\nCNPJ: {cnpj_contratada}",
            rotulo_direita=rotulo_contratante,
        )
        return markdown_para_flowables(texto, estilos, assinaturas)

    return render_documento(
        "Contrato de Prestação de Serviços Contábeis",
        contratante.nome_exibicao,
        fabrica,
    )


def previa_texto(
    contratante: ContratantePF | ContratantePJ,
    contratada: Contratada,
    parametros: ParametrosContrato,
    template: str | None = None,
) -> str:
    """Texto da minuta para pré-visualização em tela, sem gerar PDF.

    Permite conferir o conteúdo antes de produzir o arquivo — mais rápido e
    sem o custo das duas passagens de renderização.
    """
    kwargs = {"template": template} if template else {}
    return renderizar_minuta(contratante, contratada, parametros, **kwargs)
