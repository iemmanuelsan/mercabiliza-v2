"""Smoke tests da geração de PDF: os documentos precisam sair sem exceção,
com conteúdo, e com o número de páginas resolvido (build de duas passagens).
"""

from datetime import date

import pytest

from src.core.contrato import ParametrosContrato
from src.core.models import Endereco
from src.core.pessoas import (
    ContratantePF,
    ContratantePJ,
    RepresentanteLegal,
    contratada_padrao,
)
from src.exporters.pdf_contrato import gerar_contrato
from src.exporters.pdf_ficha import (
    gerar_ficha_em_branco,
)
from src.exporters.pdf_ficha import (
    gerar_ficha_preenchida as gerar_ficha_cadastral,
)

END = Endereco(logradouro="Rua Anchieta", numero="204", bairro="Vila Boaventura",
               municipio="Jundiaí", uf="SP", cep="13201804")

PJ = ContratantePJ(
    razao_social="Mercadinho São João Ltda", nome_fantasia="Mercadinho",
    cnpj="11222333000181", cnae_principal="4712100 - Minimercados",
    endereco=END, telefone="(19) 3333-4444", email="a@b.com",
    inscricao_estadual="123.456.789", regime="Simples Nacional",
    representante=RepresentanteLegal(
        nome="Ana Costa", cpf="52998224725", rg="11.222.333",
        orgao_emissor="SSP/SP", nacionalidade="brasileira",
        estado_civil="divorciada", profissao="empresária",
        qualificacao="sócia administradora", genero_feminino=True),
)

PF = ContratantePF(
    nome="João Pedro Souza", cpf="11144477735", rg="98.765.432",
    orgao_emissor="SSP/SP", estado_civil="solteiro", profissao="comerciante",
    endereco=END, telefone="(19) 99999-8888", email="joao@email.com",
)

PARAMS = ParametrosContrato(
    valor_mensal=550.0, valor_implantacao=350.0, data_inicio=date(2026, 9, 1),
    vigencia_meses=12, foro="Jundiaí/SP", cidade_assinatura="Jundiaí",
)


def _paginas(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page") or pdf.count(b"/Type/Page")


@pytest.mark.parametrize("contratante", [PJ, PF], ids=["PJ", "PF"])
def test_ficha_gera_pdf_valido(contratante):
    pdf = gerar_ficha_cadastral(contratante, contratada_padrao(), PARAMS)
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 5_000


@pytest.mark.parametrize("contratante", [PJ, PF], ids=["PJ", "PF"])
def test_contrato_gera_pdf_valido(contratante):
    pdf = gerar_contrato(contratante, contratada_padrao(), PARAMS)
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert _paginas(pdf) >= 3, "contrato completo deve ocupar várias páginas"


def test_ficha_sem_parametros_nao_quebra():
    """A ficha pode ser emitida antes de negociar valores."""
    pdf = gerar_ficha_cadastral(PJ, contratada_padrao(), None)
    assert pdf.startswith(b"%PDF")


def test_contratante_totalmente_vazio_nao_quebra():
    """Caso limite: usuário clica em gerar sem preencher nada."""
    pdf = gerar_contrato(ContratantePF(), contratada_padrao(),
                         ParametrosContrato())
    assert pdf.startswith(b"%PDF")


def test_contrato_sem_testemunhas():
    com = gerar_contrato(PJ, contratada_padrao(), PARAMS, com_testemunhas=True)
    sem = gerar_contrato(PJ, contratada_padrao(), PARAMS, com_testemunhas=False)
    assert len(sem) < len(com)


def test_clausulas_particulares_aumentam_o_documento():
    p2 = ParametrosContrato(
        valor_mensal=550.0, foro="Jundiaí/SP",
        clausulas_particulares=("Desconto de 20% nos três primeiros meses.",
                                "Atendimento presencial mensal incluído."),
    )
    base = gerar_contrato(PJ, contratada_padrao(),
                          ParametrosContrato(valor_mensal=550.0, foro="Jundiaí/SP"))
    assert len(gerar_contrato(PJ, contratada_padrao(), p2)) > len(base)


def test_texto_com_caractere_de_markup_nao_quebra_o_pdf():
    """Razão social com '&' ou '<' viraria marcação inválida no Platypus se
    não fosse escapada."""
    pj = ContratantePJ(
        razao_social="Silva & Cia <Comércio> Ltda", cnpj="11222333000181",
        endereco=END, email="a@b.com",
        representante=RepresentanteLegal(nome="Ana", cpf="52998224725"),
    )
    pdf = gerar_contrato(pj, contratada_padrao(), PARAMS)
    assert pdf.startswith(b"%PDF")


def test_duas_passagens_produzem_pdf_estavel():
    """Gerar duas vezes o mesmo contrato deve dar o mesmo número de páginas —
    prova de que o build de contagem não polui o build final."""
    a = gerar_contrato(PJ, contratada_padrao(), PARAMS)
    b = gerar_contrato(PJ, contratada_padrao(), PARAMS)
    assert _paginas(a) == _paginas(b)


@pytest.mark.parametrize("tipo", ["PF", "PJ"])
def test_ficha_em_branco_gera_pdf(tipo):
    """Caminho para o cliente sem CNPJ: não existe base pública de CPF, então
    a ficha sai vazia para o titular preencher e assinar."""
    pdf = gerar_ficha_em_branco(tipo)
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 5_000


def test_ficha_em_branco_pj_tem_mais_campos_que_pf():
    """PJ acrescenta a seção do representante legal."""
    assert len(gerar_ficha_em_branco("PJ")) > len(gerar_ficha_em_branco("PF"))


def test_ficha_em_branco_sem_operacao_e_menor():
    completa = gerar_ficha_em_branco("PF", incluir_operacao=True)
    enxuta = gerar_ficha_em_branco("PF", incluir_operacao=False)
    assert len(enxuta) < len(completa)


def test_ficha_com_condicoes_comerciais_e_maior():
    """Informar os parâmetros acrescenta a seção de condições acordadas."""
    sem = gerar_ficha_cadastral(PJ, contratada_padrao(), None)
    com = gerar_ficha_cadastral(PJ, contratada_padrao(), PARAMS)
    assert len(com) > len(sem)


def test_mei_e_qualificado_como_empresario_individual():
    """MEI/EI não é 'pessoa jurídica de direito privado' — a qualificação
    precisa refletir isso no contrato assinado."""
    mei = ContratantePJ(
        razao_social="ANDERSON ANDRADE MONTEIRO", cnpj="63435477000110",
        regime="MEI", natureza_juridica="Empresário (Individual)", endereco=END,
        representante=RepresentanteLegal(
            nome="ANDERSON ANDRADE MONTEIRO", cpf="52998224725",
            qualificacao="titular"),
    )
    texto = mei.qualificacao_contratual
    assert "empresário individual" in texto
    assert "pessoa jurídica de direito privado" not in texto
    assert "denominado simplesmente CONTRATANTE" in texto
