"""Carta de Responsabilidade da Administração.

A carta é o que separa "a administração omitiu" de "a contabilidade errou".
Sem ela, essa fronteira é discutida DEPOIS do problema, com as duas partes
lembrando a conversa de um jeito diferente. É a cláusula 4.6 do contrato que
lhe dá efeito prático: sem a carta do exercício, as demonstrações não são
concluídas nem assinadas.
"""

from __future__ import annotations

import io
import warnings
from datetime import date

import pypdf
import pytest

from src.core.carta import ParametrosCarta, renderizar_carta
from src.core.contrato import listar_minutas
from src.core.models import Endereco
from src.core.pessoas import ContratantePF, ContratantePJ, RepresentanteLegal
from src.exporters.pdf_carta import gerar_carta_responsabilidade

warnings.filterwarnings("ignore")

END = Endereco(
    logradouro="RUA ANCHIETA",
    numero="204",
    bairro="VILA BOAVENTURA",
    municipio="CAMPINAS",
    uf="SP",
    cep="13201804",
)


def _pj(**troca) -> ContratantePJ:
    base = dict(
        razao_social="PHL ALIMENTOS LTDA",
        cnpj="66490201000122",
        endereco=END,
        representante=RepresentanteLegal(
            nome="Pedro Henrique Lima",
            cpf="52998224725",
            qualificacao="sócio administrador",
        ),
    )
    base.update(troca)
    return ContratantePJ(**base)


def _texto(**kw) -> str:
    return " ".join(
        renderizar_carta(
            kw.pop("contratante", _pj()),
            ParametrosCarta(exercicio=kw.pop("exercicio", 2025), **kw),
        ).split()
    )


# --------------------------------------------------------------------------- #
# As dez alíneas — o conteúdo que delimita a responsabilidade                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("letra", list("abcdefghij"))
def test_todas_as_dez_alineas_saem(letra: str):
    assert f" {letra}) " in _texto()


def test_as_alineas_sao_texto_fixo_e_nao_parametrizadas():
    """Mudar o exercício não pode mudar uma vírgula das declarações.

    O texto das alíneas é o que define o alcance do que está sendo declarado.
    Se ele variasse com os parâmetros, uma edição de rotina mudaria o efeito
    jurídico da carta sem ninguém perceber.
    """
    de_2024 = _texto(exercicio=2024)
    de_2025 = _texto(exercicio=2025)

    trecho = (
        "g) não tenho conhecimento de fraude, irregularidade, operação ilícita, "
        "contingência relevante ou fato material"
    )
    assert trecho in de_2024
    assert trecho in de_2025


def test_traz_a_ressalva_de_nao_renovacao_automatica():
    """Sem isso, a carta de 2024 seria invocada para o exercício de 2025."""
    assert "não se renova automaticamente" in _texto()


def test_nao_afasta_as_obrigacoes_da_contratada():
    """A carta delimita a responsabilidade da administração — não transfere a
    responsabilidade técnica da contabilidade para o cliente."""
    assert "sem afastar as obrigações profissionais" in _texto()


# --------------------------------------------------------------------------- #
# Identificação                                                                #
# --------------------------------------------------------------------------- #
def test_identifica_empresa_exercicio_e_periodo():
    texto = _texto(exercicio=2025)
    assert "PHL ALIMENTOS LTDA" in texto
    assert "66.490.201/0001-22" in texto
    assert "01/01/2025 a 31/12/2025" in texto


def test_o_periodo_base_acompanha_o_exercicio():
    assert "01/01/2023 a 31/12/2023" in _texto(exercicio=2023)


def test_administrador_sai_com_nome_cpf_e_qualificacao():
    texto = _texto()
    assert "PEDRO HENRIQUE LIMA" in texto
    assert "529.982.247-25" in texto
    assert "sócio administrador" in texto


def test_sem_cpf_a_linha_do_administrador_nao_fica_torta():
    """Mesma regra do contrato: dado não informado não vira lacuna."""
    texto = _texto(contratante=_pj(representante=RepresentanteLegal(nome="Ana Costa")))
    assert "ANA COSTA" in texto
    assert "CPF" not in texto.split("ADMINISTRADOR:")[1].split("DECLARAÇÃO")[0]
    assert "____" not in texto


def test_sem_administrador_e_erro_e_nao_carta_anonima():
    """⚠️ Declaração de responsabilidade sem declarante não declara nada.

    Deixar passar em branco produziria um PDF de aparência normal que não
    vincula ninguém — e o defeito só apareceria na hora de usar a carta.
    """
    sem_nome = _pj(representante=RepresentanteLegal(nome="  ", cpf="52998224725"))
    with pytest.raises(ValueError, match="nome do administrador"):
        renderizar_carta(sem_nome, ParametrosCarta(exercicio=2025))


def test_cidade_cai_no_municipio_da_empresa_quando_nao_informada():
    assert "Campinas/SP" in _texto()


def test_cidade_informada_vence_o_municipio():
    assert "Jundiaí/SP" in _texto(cidade="Jundiaí")


def test_exercicio_fora_da_faixa_e_recusado():
    """A carta se refere a um ano-calendário. 25 ou 20255 é digitação errada."""
    for ano in (25, 1999, 20255):
        with pytest.raises(ValueError, match="fora da faixa"):
            ParametrosCarta(exercicio=ano)


# --------------------------------------------------------------------------- #
# PDF                                                                          #
# --------------------------------------------------------------------------- #
def test_pdf_sai_com_as_assinaturas_do_lado_certo():
    """⚠️ A ordem é INVERTIDA em relação ao contrato.

    No contrato a CONTRATADA assina à esquerda, porque é quem propõe o
    instrumento. Aqui quem declara é a Administração da CONTRATANTE; a
    Mercabiliza só dá ciência. Trocar os lados faria a declaração do cliente
    parecer documento emitido pela contabilidade — o contrário da função dela.
    """
    pdf = gerar_carta_responsabilidade(
        _pj(), ParametrosCarta(exercicio=2025, data_emissao=date(2026, 10, 14))
    )
    texto = " ".join(
        "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages).split()
    )

    assert "ADMINISTRAÇÃO DA CONTRATANTE" in texto
    assert "CIÊNCIA / RECEBIMENTO" in texto
    # O CRC que vale aqui é o da ORGANIZAÇÃO contábil, não o do responsável
    # técnico pessoa física.
    assert "2SP053162/O-1" in texto


def test_pdf_de_pessoa_fisica_nao_quebra():
    pf = ContratantePF(nome="Maria da Silva", cpf="11144477735", endereco=END)
    pdf = gerar_carta_responsabilidade(pf, ParametrosCarta(exercicio=2025))
    assert len(pdf) > 1000


# --------------------------------------------------------------------------- #
# O seletor de minutas                                                         #
# --------------------------------------------------------------------------- #
def test_a_carta_nao_aparece_no_seletor_de_contratos():
    """⚠️ `listar_minutas()` fazia glob em `*.md.j2`.

    Com o glob aberto, a carta passaria a aparecer no seletor "Modelo de
    minuta" da aba de contratos — e escolhê-la geraria um "contrato" que é,
    na verdade, uma declaração do cliente, com os blocos de assinatura
    trocados. O filtro por `contrato_*` é o que impede isso.
    """
    minutas = listar_minutas()

    assert minutas, "nenhuma minuta encontrada — o filtro ficou restritivo demais"
    assert "carta_responsabilidade.md.j2" not in minutas
    assert all(m.startswith("contrato_") for m in minutas)
