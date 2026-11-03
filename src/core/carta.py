"""Carta de Responsabilidade da Administração.

## O que este documento é

É a declaração em que o administrador da CONTRATANTE assume, por escrito e por
exercício, a responsabilidade pelos controles internos, pela guarda dos
documentos e pela completude do que entregou à contabilidade. Sem ela, a
fronteira entre "a administração omitiu" e "a contabilidade errou" é discutida
depois do problema, com as duas partes lembrando a conversa de um jeito
diferente.

A cláusula 4.6 do contrato é o que lhe dá efeito prático: as demonstrações
anuais não são concluídas nem assinadas sem a carta do respectivo exercício.

## Por que o texto das dez alíneas não é parametrizável

As alíneas (a) a (j) são literais no template. É a redação delas que delimita
o que está sendo declarado — deixá-las variáveis convidaria a uma edição
silenciosa que mudaria o alcance jurídico da carta sem ninguém perceber. O que
varia são só os identificadores: empresa, exercício, administrador, cidade e
data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jinja2 import TemplateNotFound

from .cnpj import formatar as formatar_cnpj
from .contrato import (
    TEMPLATES_DIR,
    TemplateContratoAusente,
    _ambiente,
    data_extenso,
)
from .cpf import formatar as formatar_cpf

TEMPLATE_CARTA = "carta_responsabilidade.md.j2"


@dataclass(frozen=True, slots=True)
class ParametrosCarta:
    """O que varia de uma carta para outra.

    ``exercicio`` é ``int`` na entrada e vira texto no template: o ano aparece
    no título e nas duas pontas do período-base, e formatar número em três
    lugares diferentes é onde nasceria uma divergência como "2025" x "2.025".
    """

    exercicio: int
    cidade: str = ""
    uf: str = "SP"
    data_emissao: date | None = None

    def __post_init__(self) -> None:
        if not (2000 <= self.exercicio <= 2100):
            raise ValueError(
                f"Exercício {self.exercicio} fora da faixa aceita (2000–2100). "
                "A carta se refere a um ano-calendário."
            )

    @property
    def periodo_inicio(self) -> str:
        return f"01/01/{self.exercicio}"

    @property
    def periodo_fim(self) -> str:
        return f"31/12/{self.exercicio}"

    def como_dict_template(self) -> dict[str, object]:
        return {
            "exercicio": str(self.exercicio),
            "periodo_inicio": self.periodo_inicio,
            "periodo_fim": self.periodo_fim,
            "cidade": self.cidade.strip() or "_____",
            "uf": (self.uf or "").strip().upper() or "SP",
            "data_extenso": data_extenso(self.data_emissao or date.today()),
        }


def _empresa_do_contratante(contratante) -> dict[str, str]:
    razao = getattr(contratante, "razao_social", None) or getattr(contratante, "nome", "")
    documento = getattr(contratante, "cnpj", "") or getattr(contratante, "cpf", "")
    formatado = (
        formatar_cnpj(documento)
        if getattr(contratante, "cnpj", "")
        else formatar_cpf(documento)
        if documento
        else "(não informado)"
    )
    return {
        "razao_social": razao.strip().upper() or "(RAZÃO SOCIAL NÃO INFORMADA)",
        "cnpj_formatado": formatado,
        "municipio": getattr(contratante.endereco, "municipio", ""),
    }


def _administrador(contratante) -> dict[str, str]:
    """Nome, CPF e qualificação de quem assina pela empresa.

    Vem do representante legal do cadastro — que, no CRM, é preenchido a
    partir do primeiro sócio do QSA e pode ser trocado antes de gerar.

    ⚠️ Sem nome não há carta: uma declaração de responsabilidade sem declarante
    identificado não declara nada. Por isso aqui é erro, e não um campo em
    branco que passaria despercebido até a hora da assinatura.
    """
    rep = getattr(contratante, "representante", None)
    nome = (getattr(rep, "nome", "") or "").strip()
    if not nome:
        nome = (getattr(contratante, "nome", "") or "").strip()
    if not nome:
        raise ValueError(
            "A Carta de Responsabilidade precisa do nome do administrador que "
            "assina. Preencha o representante legal no cadastro do cliente."
        )

    cpf = (getattr(rep, "cpf", "") or getattr(contratante, "cpf", "") or "").strip()
    qualificacao = (getattr(rep, "qualificacao", "") or "administrador").strip()

    partes = [nome.upper()]
    if cpf:
        partes.append(f"CPF {formatar_cpf(cpf)}")
    partes.append(qualificacao)

    return {
        "nome": nome.upper(),
        "cpf_formatado": formatar_cpf(cpf) if cpf else "",
        "qualificacao": qualificacao,
        # Campo pronto para o template: evita montar pontuação em Jinja, onde
        # um `{% if %}` mal fechado vira vírgula solta no documento final.
        "linha_qualificacao": " — ".join(partes),
    }


def renderizar_carta(contratante, parametros: ParametrosCarta) -> str:
    """Texto da carta em markdown simplificado, pronto para o gerador de PDF."""
    try:
        tpl = _ambiente().get_template(TEMPLATE_CARTA)
    except TemplateNotFound as exc:
        raise TemplateContratoAusente(
            f"Modelo '{TEMPLATE_CARTA}' não encontrado em {TEMPLATES_DIR}."
        ) from exc

    from ..config import CARTA_DESTINATARIO_FIXO

    empresa = _empresa_do_contratante(contratante)
    carta = parametros.como_dict_template()
    if carta["cidade"] == "_____" and empresa["municipio"]:
        carta["cidade"] = empresa["municipio"].title()

    return tpl.render(
        contratada_fixa=CARTA_DESTINATARIO_FIXO,
        e=empresa,
        adm=_administrador(contratante),
        c=carta,
    )
