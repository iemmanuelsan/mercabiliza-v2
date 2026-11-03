from datetime import date

import pytest

from src.core.contrato import (
    OBJETO_PADRAO,
    ParametrosContrato,
    data_extenso,
    numero_extenso,
    renderizar_minuta,
    valor_extenso,
)
from src.core.models import Endereco
from src.core.pessoas import (
    ContratantePF,
    ContratantePJ,
    RepresentanteLegal,
    contratada_padrao,
)

END = Endereco(
    logradouro="Rua Anchieta",
    numero="204",
    bairro="Vila Boaventura",
    municipio="Jundiaí",
    uf="SP",
    cep="13201804",
)


# --------------------------------------------------------------------------- #
# Números e datas por extenso                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "n,esperado",
    [
        (0, "zero"),
        (1, "um"),
        (15, "quinze"),
        (21, "vinte e um"),
        (30, "trinta"),
        (100, "cem"),
        (101, "cento e um"),
        (200, "duzentos"),
        (350, "trezentos e cinquenta"),
        (999, "novecentos e noventa e nove"),
        (1000, "mil"),
        (1001, "mil e um"),
        (2000, "dois mil"),
        (15000, "quinze mil"),
        (100000, "cem mil"),
    ],
)
def test_numero_extenso(n, esperado):
    assert numero_extenso(n) == esperado


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (350.0, "trezentos e cinquenta reais"),
        (1.0, "um real"),
        (2.50, "dois reais e cinquenta centavos"),
        (0.99, "noventa e nove centavos"),
        (1600.0, "mil e seiscentos reais"),
        (0.0, "zero reais"),
    ],
)
def test_valor_extenso(valor, esperado):
    assert valor_extenso(valor) == esperado


def test_valor_extenso_arredonda_centavos():
    """0,999 não pode virar '100 centavos'."""
    assert valor_extenso(1.999) == "dois reais"


def test_data_extenso():
    assert data_extenso(date(2026, 8, 17)) == "17 de agosto de 2026"
    assert data_extenso(date(2026, 3, 1)) == "1 de março de 2026"


# --------------------------------------------------------------------------- #
# Parâmetros                                                                   #
# --------------------------------------------------------------------------- #
def test_parametros_vazios_listam_pendencias():
    pend = ParametrosContrato().pendencias
    assert any("valor mensal" in p for p in pend)
    assert any("foro" in p for p in pend)


def test_parametros_completos_sem_pendencias():
    p = ParametrosContrato(valor_mensal=550.0, foro="Jundiaí/SP")
    assert p.pendencias == ()


def test_dia_de_vencimento_fora_da_faixa_e_pendencia():
    assert any(
        "vencimento" in p
        for p in ParametrosContrato(valor_mensal=1, foro="X", dia_vencimento=45).pendencias
    )


def test_dict_template_formata_em_pt_br():
    p = ParametrosContrato(valor_mensal=550.0, foro="Jundiaí/SP", data_inicio=date(2026, 9, 1))
    d = p.como_dict_template()
    assert d["valor_mensal_fmt"] == "R$ 550,00"
    assert d["honorarios_extenso"] == "quinhentos e cinquenta reais"
    assert d["data_inicio_fmt"] == "1 de setembro de 2026"


def test_implantacao_zero_nao_gera_texto():
    """Cláusula de implantação só deve existir se houver valor."""
    p = ParametrosContrato(valor_mensal=350.0, foro="X", valor_implantacao=0.0)
    assert p.como_dict_template()["valor_implantacao_fmt"] == ""


def test_clausulas_particulares_vazias_sao_descartadas():
    p = ParametrosContrato(
        valor_mensal=1, foro="X", clausulas_particulares=("  ", "", "válida")
    )
    assert p.como_dict_template()["clausulas_particulares"] == ["válida"]


# --------------------------------------------------------------------------- #
# Renderização da minuta                                                       #
# --------------------------------------------------------------------------- #
def _pj() -> ContratantePJ:
    return ContratantePJ(
        razao_social="Mercadinho São João Ltda",
        cnpj="11222333000181",
        endereco=END,
        email="a@b.com",
        representante=RepresentanteLegal(
            nome="Ana Costa",
            cpf="52998224725",
            qualificacao="sócia administradora",
            genero_feminino=True,
        ),
    )


def _params(**kw) -> ParametrosContrato:
    base = {
        "valor_mensal": 550.0,
        "foro": "Jundiaí/SP",
        "cidade_assinatura": "Jundiaí",
        "data_inicio": date(2026, 9, 1),
        "data_assinatura": date(2026, 9, 1),
    }
    return ParametrosContrato(**{**base, **kw})


def test_minuta_renderiza_com_as_partes():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "MERCADINHO SÃO JOÃO LTDA" in texto
    assert "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA" in texto
    assert "CLÁUSULA 1 - DO OBJETO" in texto
    assert "[[ASSINATURAS]]" in texto


def test_minuta_tem_todas_as_clausulas_essenciais():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    # Títulos da versão final da diretoria (out/2026), com 10 cláusulas.
    for termo in (
        "DO OBJETO E DO ESCOPO DOS SERVIÇOS",
        "DOS HONORÁRIOS E DAS CONDIÇÕES DE EXECUÇÃO",
        "DOS DEVERES E DA RESPONSABILIDADE DA CONTRATADA",
        "DOS DEVERES DA CONTRATANTE",
        "DA REVISÃO DE HONORÁRIOS",
        "DA VIGÊNCIA, SUSPENSÃO E RESCISÃO",
        "DA PROTEÇÃO DE DADOS E CONFIDENCIALIDADE",
        "DAS OBRIGAÇÕES LEGAIS E REGULATÓRIAS",
        "DAS COMUNICAÇÕES",
        "DO FORO",
    ):
        assert termo in texto, f"cláusula ausente: {termo}"


def test_valor_aparece_formatado_e_por_extenso():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "R$ 550,00" in texto
    assert "quinhentos e cinquenta reais" in texto


def test_objeto_nao_duplica_a_palavra_servicos():
    """O template diz 'dos serviços de {objeto}' — o objeto padrão não pode
    começar com 'serviços de', senão sai 'serviços de serviços de'."""
    assert not OBJETO_PADRAO.lower().startswith("serviços de")
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "serviços de serviços" not in texto.lower()


def test_sem_implantacao_nao_menciona_taxa():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params(valor_implantacao=0.0))
    assert "título de implantação" not in texto


def test_com_implantacao_menciona_taxa():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params(valor_implantacao=350.0))
    assert "título de implantação" in texto
    assert "R$ 350,00" in texto


def test_vigencia_zero_cai_no_padrao_de_12_meses():
    """O contrato modelo da Mercabiliza é sempre por prazo determinado. Deixar
    a vigência em zero não pode gerar cláusula vazia — assume os 12 meses."""
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params(vigencia_meses=0))
    assert "12 (doze) meses" in texto


def test_vigencia_definida_aparece_por_extenso():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params(vigencia_meses=12))
    assert "12 (doze) meses" in texto


def test_clausulas_particulares_criam_secao_e_renumeram_o_foro():
    sem = renderizar_minuta(_pj(), contratada_padrao(), _params())
    com = renderizar_minuta(
        _pj(), contratada_padrao(), _params(clausulas_particulares=("Desconto de 20%.",))
    )
    assert "DISPOSIÇÕES PARTICULARES" not in sem
    assert "CLÁUSULA 10 - DO FORO" in sem
    assert "DISPOSIÇÕES PARTICULARES" in com
    assert "Desconto de 20%." in com
    assert "CLÁUSULA 11 - DO FORO" in com


def test_minuta_funciona_para_pessoa_fisica():
    pf = ContratantePF(
        nome="João Souza",
        cpf="11144477735",
        estado_civil="solteiro",
        profissao="comerciante",
        endereco=END,
    )
    texto = renderizar_minuta(pf, contratada_padrao(), _params())
    assert "JOÃO SOUZA" in texto
    assert "denominado simplesmente CONTRATANTE" in texto


def test_local_e_data_no_fecho():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "Jundiaí, 1 de setembro de 2026." in texto


# --------------------------------------------------------------------------- #
# Bloco fixo da CONTRATADA (duas empresas do grupo)                            #
# --------------------------------------------------------------------------- #
def test_contratada_traz_as_duas_empresas_do_grupo():
    """A qualificação da CONTRATADA é texto fixo definido pela diretoria:
    as duas empresas, sem CRC e sem nomear pessoa física."""
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA" in texto
    assert "62.350.925/0001-10" in texto
    # A empresa de TECNOLOGIA saiu do contrato na revisão de 01/09/2026:
    # o serviço passou a ser exclusivamente contábil.
    assert "MERCABILIZA SOLUCOES EM TECNOLOGIA E GESTAO" not in texto
    assert "62.291.063" not in texto


def test_contratada_nomeia_o_responsavel_tecnico_e_o_crc():
    """Inverte a regra anterior — e a inversão é deliberada.

    Até 01/09/2026 a diretoria queria a CONTRATADA sem CRC e sem nomear pessoa
    física, e havia um teste travando exatamente isso. A revisão inverteu:
    contrato contábil sem o CRC do responsável técnico é frágil perante o CFC,
    e o sócio administrador precisa constar como quem representa a empresa.

    O teste antigo virou este. Se alguém precisar voltar atrás, é decisão de
    negócio nova — não um bug para "corrigir" silenciosamente.
    """
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    cabecalho = texto[: texto.index("CONTRATANTE:")]
    assert "CRC SP sob o nº" in cabecalho
    assert "SP323775/O-2" in cabecalho
    assert "LUIS FELIPE PEDI SILVA" in cabecalho
    assert "sócio Administrador" in cabecalho


def test_escopo_de_dp_e_monofasico_e_opcional():
    """Cliente sem funcionário não recebe a cláusula trabalhista."""
    com_dp = renderizar_minuta(_pj(), contratada_padrao(), _params(incluir_dp=True))
    sem_dp = renderizar_minuta(_pj(), contratada_padrao(), _params(incluir_dp=False))
    assert "ÁREA TRABALHISTA E PREVIDENCIÁRIA" in com_dp
    assert "ÁREA TRABALHISTA E PREVIDENCIÁRIA" not in sem_dp

    com_mono = renderizar_minuta(_pj(), contratada_padrao(), _params(incluir_monofasico=True))
    sem_mono = renderizar_minuta(_pj(), contratada_padrao(), _params(incluir_monofasico=False))
    # A SEÇÃO de escopo é que some. A palavra "monofásica" continua no
    # contrato, na cláusula de acesso aos sistemas (7.3.2), onde descreve uma
    # das finalidades do acesso — não o escopo contratado.
    assert "SEGREGAÇÃO DE RECEITAS" in com_mono
    assert "SEGREGAÇÃO DE RECEITAS" not in sem_mono


def test_nota_de_rodape_cita_o_codigo_civil_correto():
    """O modelo em uso cita 'Lei 10.402/2002'; o Código Civil é a 10.406/2002."""
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "10.406/2002" in texto
    assert "10.402/2002" not in texto


# =========================================================================== #
# Revisão contratual de 01/09/2026                                            #
# =========================================================================== #
# Cada item aqui veio de uma marcação feita à mão pela diretoria num contrato
# impresso: vermelho = remover, amarelo = modificar. Fixar em teste é o que
# impede a revisão de ser desfeita por acidente numa edição futura do template.
def _texto_do_contrato(**kwargs) -> str:
    """Gera um contrato e devolve o texto extraído do PDF."""
    import io

    import pdfplumber

    from src.exporters.pdf_documentos import gerar_contrato

    pdf = gerar_contrato(_pj(), contratada_padrao(), _params(), **kwargs)
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join((p.extract_text() or "") for p in doc.pages)


def _trechos_em_negrito(pdf_bytes: bytes) -> str:
    """Concatena tudo que está em fonte Bold, para checar destaque."""
    import io

    import pdfplumber

    trechos: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        for pagina in doc.pages:
            atual, ligado = "", False
            for ch in pagina.chars:
                bold = "Bold" in ch["fontname"]
                if bold and not ligado:
                    atual, ligado = ch["text"], True
                elif bold:
                    atual += ch["text"]
                elif ligado:
                    trechos.append(atual.strip())
                    atual, ligado = "", False
            if ligado:
                trechos.append(atual.strip())
    return " | ".join(trechos)


@pytest.mark.parametrize(
    "removido",
    [
        "MERCABILIZA SOLUCOES EM TECNOLOGIA E GESTAO",  # empresa fora do contrato
        "62.291.063",  # CNPJ dela
        "E DE SOFTWARE",  # título acompanhou
        "Testemunhas",  # seção removida
        "testemunhas instrumentais",  # frase de fecho ajustada
        "JUNDIAI/PR",  # era erro de digitação
    ],
)
def test_revisao_removeu(removido):
    assert removido not in _texto_do_contrato()


@pytest.mark.parametrize(
    "presente",
    [
        "JUNDIAI/SP",
        "LUIS FELIPE PEDI SILVA",
        "49514166",
        "378.007.638-11",
        "SP323775/O-2",
        "sócio Administrador",
    ],
)
def test_revisao_acrescentou(presente):
    assert presente in _texto_do_contrato()


@pytest.mark.parametrize(
    "destacado",
    [
        "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA",
        "62.350.925/0001-10",
        "LUIS FELIPE PEDI SILVA",
        "49514166",
        "378.007.638-11",
        "SP323775/O-2",
    ],
)
def test_negritos_exigidos_pela_diretoria(destacado):
    """A lista de itens em negrito foi definida pela diretoria, item a item."""
    from src.exporters.pdf_documentos import gerar_contrato

    negrito = _trechos_em_negrito(gerar_contrato(_pj(), contratada_padrao(), _params()))
    assert destacado in negrito, f"'{destacado}' deveria sair em negrito"


def test_cidade_da_contratante_sai_em_negrito():
    """Cidade define foro e competência — quem confere procura por ela."""
    from src.exporters.pdf_documentos import gerar_contrato

    negrito = _trechos_em_negrito(gerar_contrato(_pj(), contratada_padrao(), _params()))
    pj = _pj()
    cidade = f"{pj.endereco.municipio}/{pj.endereco.uf}"
    assert cidade in negrito


def test_testemunhas_so_aparecem_se_pedidas_explicitamente():
    """O padrão virou False; o bloco continua existindo para outros modelos."""
    assert "Testemunhas" not in _texto_do_contrato()
    assert "Testemunhas" in _texto_do_contrato(com_testemunhas=True)


# --------------------------------------------------------------------------- #
# Numeração da CLÁUSULA 2                                                      #
# --------------------------------------------------------------------------- #
def _subitens_da_clausula_2(**kw) -> list[str]:
    """Itens 2.1.x na ordem em que aparecem, sem repetição."""
    import re

    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params(**kw)).split())
    vistos: set[str] = set()
    ordem: list[str] = []
    for item in re.findall(r"(?<![\d.])2\.1(?:\.\d)?\.", texto):
        if item not in vistos:
            vistos.add(item)
            ordem.append(item)
    return ordem


def test_numeracao_da_clausula_2_nao_tem_buraco():
    """A minuta pulava de 2.1.1 para 2.1.3 — não existia 2.1.2.

    O item que faltava era o do honorário adicional anual do modelo original,
    removido em algum momento. Ficou o buraco, e ficou a 2.1.3 falando de "a
    parcela adicional" sem antecedente. Um contrato com numeração salteada é
    a primeira coisa que o advogado do outro lado comenta.
    """
    assert _subitens_da_clausula_2(valor_implantacao=500.0) == [
        "2.1.", "2.1.1.", "2.1.2.", "2.1.3.",
    ]


def test_sem_implantacao_a_numeracao_continua_sequencial():
    """⚠️ O caso que a correção do buraco fixo NÃO resolvia sozinha.

    O 2.1.1 (implantação) vive dentro de um `{% if %}`: só existe quando há
    valor de implantação — e na maioria dos contratos não há. Com números
    escritos à mão, esses contratos voltavam a pular de 2.1 para 2.1.2.

    Era pior que o buraco original, porque aparecia num contrato e sumia no
    seguinte, dependendo de um campo do formulário. Por isso a numeração dos
    subitens é calculada no template.
    """
    itens = _subitens_da_clausula_2(valor_implantacao=0.0)

    assert itens == ["2.1.", "2.1.1.", "2.1.2."]
    # E o texto da implantação realmente não está lá.
    texto = renderizar_minuta(
        _pj(), contratada_padrao(), _params(valor_implantacao=0.0)
    )
    assert "título de implantação" not in texto


def test_as_referencias_cruzadas_do_contrato_existem():
    """Cláusula que cita outra pelo número tem de citar número que existe.

    A versão final amarra a cláusula de acesso aos sistemas (7.3) nos itens
    2.2.5, 4.2.8, 2.4.3 e 2.4.4 — e essa amarração não é decorativa: sem ela,
    autorizar o acesso ao PDV do cliente poderia ser lido como transferência à
    CONTRATADA do ônus de descobrir o que ele não informou.
    """
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())

    for citado in ("2.2.5", "4.2.8", "2.4.3", "2.4.4", "2.1-A", "cláusula 4.7"):
        assert citado in texto, f"referência cruzada a {citado} sumiu"
    assert "Anexo II" in texto

    # E os itens citados realmente existem como itens do contrato.
    for item in ("2.2.5.", "4.2.8.", "2.4.3.", "2.4.4."):
        assert item in texto, f"o item {item} é citado mas não existe"


def test_demonstracoes_intermediarias_exigem_60_dias_nas_duas_minutas():
    """O prazo de 60 dias para demonstração intermediária vale nas duas.

    A redação difere: a minuta principal, na versão final da diretoria, diz
    "antecedência mínima"; a segunda minuta mantém "preferencialmente com
    prazo não inferior a". O que não pode faltar em nenhuma é o prazo.
    """
    from src.core.contrato import TEMPLATE_CONTRATO

    for template in (TEMPLATE_CONTRATO, "contrato_servicos_contabeis.md.j2"):
        texto = " ".join(
            renderizar_minuta(
                _pj(), contratada_padrao(), _params(), template=template
            ).split()
        )
        assert "60 (sessenta) dias" in texto, f"prazo ausente em {template}"
        assert "períodos intermediários" in texto, f"regra ausente em {template}"
        # A redação antiga não pode ter sobrado em nenhuma das duas.
        assert "balanço anual de demonstrativo" not in texto


def test_o_termo_de_acesso_e_anexo_e_nao_clausula_do_corpo():
    """Decisão da diretoria: o termo de aceite fica SEPARADO do contrato.

    A primeira versão trazia o texto como cláusula 7.3, no meio do corpo. O
    gerente pediu para recuar: como anexo com aceite próprio, o cliente é
    obrigado a ler e assinar aquele bloco, em vez de o consentimento passar
    despercebido entre as cláusulas de proteção de dados.
    """
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())

    # O corpo só REMETE ao anexo.
    assert "constante do **Anexo II**" in texto
    assert "ANEXO II - TERMO DE AUTORIZAÇÃO E ACEITE DE ACESSO" in texto

    # E o conteúdo está no anexo, não na cláusula 7.
    corpo, anexo = texto.split("ANEXO II", 1)
    assert "TouchPay" not in corpo, "o termo voltou para o corpo do contrato"
    assert "TouchPay" in anexo and "AMLabs" in anexo


def test_o_anexo_tem_aceite_proprio():
    """É o que faz o cliente ter de ler e assinar — o pedido do gerente."""
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())
    anexo = texto.split("ANEXO II", 1)[1]

    assert "DO ACEITE" in anexo
    assert "li o presente Termo" in anexo
    assert "**aceito**" in anexo
    # Assinatura própria, além da do contrato.
    assert "responsável legal ou administrador de sistemas" in anexo


def test_o_anexo_comeca_em_pagina_nova():
    """Anexo que começa no meio da página do contrato não parece anexo."""
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "[[QUEBRA]]" in texto
    assert texto.index("[[QUEBRA]]") < texto.index("ANEXO II")


def test_o_anexo_mantem_as_amarras_com_o_contrato():
    """Mudar de cláusula para anexo não pode soltar as referências cruzadas.

    Sem os itens 2.2.5 e 4.2.8, autorizar o acesso ao PDV poderia ser lido
    como transferência à CONTRATADA do ônus de descobrir o que o cliente não
    informou — exatamente o que aqueles itens afastam.
    """
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())
    anexo = texto.split("ANEXO II", 1)[1]

    for citado in ("2.2.5", "4.2.8", "2.4.3", "2.4.4"):
        assert citado in anexo, f"o anexo perdeu a referência ao item {citado}"
    assert "13.709/2018" in anexo


def test_carta_de_responsabilidade_e_condicao_do_fechamento():
    """A cláusula 4.6 é o que dá efeito prático à carta: sem ela, as
    demonstrações não são assinadas."""
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())

    assert "CARTA DE RESPONSABILIDADE DA ADMINISTRAÇÃO" in texto
    assert "ficarão condicionadas" in texto
    assert "não se presumindo renovada" in texto


def test_limite_de_responsabilidade_de_doze_mensalidades():
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())

    assert "12 (doze) mensalidades" in texto
    # A ressalva importa tanto quanto o limite: ele não afasta o que a lei não
    # deixa limitar.
    assert "não afasta responsabilidades profissionais" in texto


def test_faixas_de_honorario_saem_como_exemplo():
    """Decisão do Iago: as faixas entram para o cliente ficar ciente de como o
    valor se move, sem fixar total — que varia por competência."""
    texto = " ".join(renderizar_minuta(_pj(), contratada_padrao(), _params()).split())

    assert "valores apresentados são exemplificativos" in texto
    assert "1 a 3 pessoas, R$ 50,00" in texto
    assert "uma nova unidade representará acréscimo de R$ 50,00" in texto
