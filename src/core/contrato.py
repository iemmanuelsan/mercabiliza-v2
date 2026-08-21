"""Parâmetros contratuais e renderização da minuta.

O texto jurídico vive em ``templates/*.md.j2`` — fora do código, para que
possa ser revisado por advogado e editado sem risco de quebrar a aplicação.
Este módulo cuida de: validar os parâmetros, converter números em texto
(valor por extenso, prazos) e renderizar o template.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from ..config import BASE_DIR
from .formatters import moeda

TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATE_CONTRATO = "contrato_mercabiliza.md.j2"

# Completa a frase "...a prestação dos serviços de {objeto}." — por isso NÃO
# começa com "serviços de", que sairia duplicado no contrato.
OBJETO_PADRAO = (
    "contabilidade, escrituração fiscal e assessoria tributária, com foco na "
    "operação de minimercado autônomo"
)

INDICES_REAJUSTE: tuple[str, ...] = ("IPCA", "IGP-M", "INPC")

FORMAS_PAGAMENTO: tuple[str, ...] = (
    "boleto bancário",
    "PIX",
    "transferência bancária",
    "débito automático",
)

MESES_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


# --------------------------------------------------------------------------- #
# Números por extenso                                                          #
# --------------------------------------------------------------------------- #
_UNIDADES = ("", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
             "oito", "nove", "dez", "onze", "doze", "treze", "quatorze",
             "quinze", "dezesseis", "dezessete", "dezoito", "dezenove")
_DEZENAS = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
            "setenta", "oitenta", "noventa")
_CENTENAS = ("", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
             "seiscentos", "setecentos", "oitocentos", "novecentos")


def _ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    partes = []
    centena, resto = divmod(n, 100)
    if centena:
        partes.append(_CENTENAS[centena])
    if resto < 20:
        if resto:
            partes.append(_UNIDADES[resto])
    else:
        dezena, unidade = divmod(resto, 10)
        partes.append(_DEZENAS[dezena])
        if unidade:
            partes.append(_UNIDADES[unidade])
    return " e ".join(partes)


def numero_extenso(n: int) -> str:
    """Inteiros de 0 a 999.999 por extenso, em português."""
    n = int(n)
    if n < 0:
        return f"menos {numero_extenso(-n)}"
    if n == 0:
        return "zero"
    if n < 1000:
        return _ate_999(n)

    milhares, resto = divmod(n, 1000)
    cabeca = "mil" if milhares == 1 else f"{_ate_999(milhares)} mil"
    if resto == 0:
        return cabeca
    ligacao = " e " if (resto < 100 or resto % 100 == 0) else " "
    return f"{cabeca}{ligacao}{_ate_999(resto)}"


def valor_extenso(valor: float) -> str:
    """``1234.56`` -> ``'mil duzentos e trinta e quatro reais e cinquenta e
    seis centavos'``."""
    reais = int(abs(valor))
    centavos = round((abs(valor) - reais) * 100)
    if centavos == 100:          # arredondamento de 0,999...
        reais += 1
        centavos = 0

    partes = []
    if reais:
        unidade = "real" if reais == 1 else "reais"
        partes.append(f"{numero_extenso(reais)} {unidade}")
    if centavos:
        unidade = "centavo" if centavos == 1 else "centavos"
        partes.append(f"{numero_extenso(centavos)} {unidade}")
    if not partes:
        return "zero reais"
    return " e ".join(partes)


def data_extenso(d: date) -> str:
    return f"{d.day} de {MESES_PT[d.month - 1]} de {d.year}"


# --------------------------------------------------------------------------- #
# Parâmetros                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ParametrosContrato:
    """Tudo o que muda de um contrato para outro."""

    objeto: str = OBJETO_PADRAO
    valor_mensal: float = 0.0
    valor_implantacao: float = 0.0
    dia_vencimento: int = 10
    forma_pagamento: str = "boleto bancário"
    data_inicio: date = field(default_factory=date.today)
    vigencia_meses: int = 12           # o contrato modelo usa 12 meses
    indice_reajuste: str = "IPCA"
    prazo_rescisao_dias: int = 30
    multa_atraso_pct: float = 2.0
    juros_mora_mes_pct: float = 1.0
    foro: str = ""
    cidade_assinatura: str = ""
    data_assinatura: date = field(default_factory=date.today)
    incluir_dp: bool = True            # área trabalhista/previdenciária
    incluir_monofasico: bool = True     # segregação de monofásicos
    clausulas_particulares: tuple[str, ...] = ()

    # ------------------------------------------------------------------ #
    @property
    def pendencias(self) -> tuple[str, ...]:
        faltando = []
        if self.valor_mensal <= 0:
            faltando.append("valor mensal dos honorários")
        if not self.objeto.strip():
            faltando.append("objeto do contrato")
        if not self.foro.strip():
            faltando.append("foro (comarca)")
        if not 1 <= self.dia_vencimento <= 31:
            faltando.append("dia de vencimento entre 1 e 31")
        return tuple(faltando)

    def como_dict_template(self) -> dict[str, object]:
        """Achata os parâmetros no formato que o template Jinja2 espera."""
        cidade = self.cidade_assinatura.strip() or self.foro.strip() or "_____"
        return {
            "objeto": self.objeto.strip(),
            "valor_mensal_fmt": moeda(self.valor_mensal),
            "honorarios_extenso": valor_extenso(self.valor_mensal),
            "valor_implantacao_fmt": (
                f"{moeda(self.valor_implantacao)} "
                f"({valor_extenso(self.valor_implantacao)})"
                if self.valor_implantacao > 0 else ""
            ),
            "dia_vencimento": self.dia_vencimento,
            "forma_pagamento": self.forma_pagamento,
            "data_inicio_fmt": data_extenso(self.data_inicio),
            "vigencia_meses": self.vigencia_meses or 12,
            "vigencia_meses_extenso": (
                numero_extenso(self.vigencia_meses or 12)
            ),
            "indice_reajuste": self.indice_reajuste,
            "prazo_rescisao_dias": self.prazo_rescisao_dias,
            "prazo_rescisao_extenso": numero_extenso(self.prazo_rescisao_dias),
            "multa_atraso_pct": f"{self.multa_atraso_pct:.0f}".replace(".", ","),
            "juros_mora_mes_pct": f"{self.juros_mora_mes_pct:.0f}".replace(".", ","),
            "foro": self.foro.strip() or "_____",
            "clausulas_particulares": [
                c.strip() for c in self.clausulas_particulares if c.strip()
            ],
            "data_inicio_curta": f"{self.data_inicio:%d/%m/%Y}",
            "multa_atraso_extenso": numero_extenso(int(self.multa_atraso_pct)),
            "juros_mora_extenso": numero_extenso(int(self.juros_mora_mes_pct)),
            "incluir_dp": self.incluir_dp,
            "incluir_monofasico": self.incluir_monofasico,
            "local_data": f"{cidade}, {data_extenso(self.data_assinatura)}.",
        }


# --------------------------------------------------------------------------- #
# Renderização                                                                 #
# --------------------------------------------------------------------------- #
def _ambiente() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,   # falha alto em variável ausente
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,            # saída é texto puro, não HTML
    )


class TemplateContratoAusente(FileNotFoundError):
    """A minuta não foi encontrada em ``templates/``."""


def renderizar_minuta(
    contratante,
    contratada,
    parametros: ParametrosContrato,
    template: str = TEMPLATE_CONTRATO,
) -> str:
    """Devolve o texto da minuta em markdown simplificado.

    ``StrictUndefined`` é deliberado: se o template referenciar uma variável
    que não existe, queremos um erro imediato e visível — não um contrato
    entregue ao cliente com um trecho silenciosamente em branco.
    """
    try:
        tpl = _ambiente().get_template(template)
    except TemplateNotFound as exc:
        raise TemplateContratoAusente(
            f"Minuta '{template}' não encontrada em {TEMPLATES_DIR}. "
            "Confirme se a pasta templates/ foi versionada."
        ) from exc

    from ..config import CONTRATADA_QUALIFICACAO_FIXA, CONTRATO_NOTA_RODAPE

    return tpl.render(
        contratante=contratante,
        contratada=contratada,
        contratada_fixa=CONTRATADA_QUALIFICACAO_FIXA,
        nota_rodape=CONTRATO_NOTA_RODAPE,
        p=parametros.como_dict_template(),
    )


def listar_minutas() -> list[str]:
    """Templates disponíveis — permite ter mais de um modelo de contrato."""
    if not Path(TEMPLATES_DIR).is_dir():
        return []
    return sorted(p.name for p in TEMPLATES_DIR.glob("*.md.j2"))
