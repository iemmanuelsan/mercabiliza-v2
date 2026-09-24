import pytest

from src.core.models import (
    AtividadeCNAE,
    Empresa,
    Endereco,
    SituacaoCadastral,
    Socio,
)
from src.core.pessoas import (
    ContratantePF,
    ContratantePJ,
    RepresentanteLegal,
    contratada_padrao,
    de_empresa,
)
from src.core.tributario import classificar_cnae

END = Endereco(
    logradouro="Rua Anchieta",
    numero="204",
    bairro="Vila Boaventura",
    municipio="Jundiaí",
    uf="SP",
    cep="13201804",
)


# --------------------------------------------------------------------------- #
# Endereço                                                                     #
# --------------------------------------------------------------------------- #
def test_cep_formatado():
    assert END.cep_formatado == "13201-804"


def test_cep_invalido_devolve_como_veio():
    assert Endereco(cep="132").cep_formatado == "132"


def test_complemento_entra_no_logradouro():
    end = Endereco(logradouro="Rua A", numero="10", complemento="sala 3")
    assert end.logradouro_numero == "Rua A, 10, sala 3"


def test_linha_juridica():
    assert END.linha_juridica == (
        "Rua Anchieta, 204, Vila Boaventura, Jundiaí/SP, CEP 13201-804"
    )


def test_endereco_vazio_nao_esta_preenchido():
    assert not Endereco().esta_preenchido
    assert END.esta_preenchido


# --------------------------------------------------------------------------- #
# Concordância de gênero                                                       #
# --------------------------------------------------------------------------- #
def test_pf_masculino():
    pf = ContratantePF(
        nome="João Souza",
        cpf="11144477735",
        rg="1",
        orgao_emissor="SSP/SP",
        estado_civil="solteiro",
        profissao="comerciante",
        endereco=END,
    )
    texto = pf.qualificacao_contratual
    assert "portador da" in texto
    assert "inscrito no CPF" in texto
    assert "domiciliado na" in texto
    assert "denominado simplesmente CONTRATANTE" in texto


def test_pf_feminino():
    pf = ContratantePF(
        nome="Maria Silva",
        cpf="52998224725",
        rg="1",
        orgao_emissor="SSP/SP",
        estado_civil="casada",
        nacionalidade="brasileira",
        profissao="comerciante",
        endereco=END,
        genero_feminino=True,
    )
    texto = pf.qualificacao_contratual
    assert "portadora da" in texto
    assert "inscrita no CPF" in texto
    assert "domiciliada na" in texto
    assert "denominada simplesmente CONTRATANTE" in texto


def test_cpf_aparece_formatado_na_qualificacao():
    pf = ContratantePF(nome="X", cpf="52998224725")
    assert "529.982.247-25" in pf.qualificacao_contratual


# --------------------------------------------------------------------------- #
# Pendências                                                                   #
# --------------------------------------------------------------------------- #
def test_pf_vazia_lista_pendencias():
    pend = ContratantePF().pendencias
    assert "nome completo" in pend and "CPF" in pend


def test_pf_completa_sem_pendencias():
    pf = ContratantePF(
        nome="João",
        cpf="11144477735",
        estado_civil="solteiro",
        profissao="comerciante",
        endereco=END,
    )
    assert pf.pendencias == ()


def test_pj_exige_representante():
    pj = ContratantePJ(
        razao_social="X Ltda", cnpj="11222333000181", endereco=END, email="a@b.com"
    )
    assert any("representante" in p for p in pj.pendencias)


def test_pj_completa_sem_pendencias():
    pj = ContratantePJ(
        razao_social="X Ltda",
        cnpj="11222333000181",
        endereco=END,
        email="a@b.com",
        representante=RepresentanteLegal(nome="Ana", cpf="52998224725"),
    )
    assert pj.pendencias == ()


# --------------------------------------------------------------------------- #
# Qualificação PJ                                                              #
# --------------------------------------------------------------------------- #
def test_pj_qualificacao_traz_cnpj_formatado_e_representante():
    pj = ContratantePJ(
        razao_social="Mercadinho São João Ltda",
        cnpj="11222333000181",
        endereco=END,
        representante=RepresentanteLegal(
            nome="Ana Costa",
            cpf="52998224725",
            qualificacao="sócia administradora",
            genero_feminino=True,
        ),
    )
    texto = pj.qualificacao_contratual
    assert "MERCADINHO SÃO JOÃO LTDA" in texto
    assert "11.222.333/0001-81" in texto
    assert "neste ato representada por **ANA COSTA**" in texto
    assert "sócia administradora" in texto
    assert texto.endswith("doravante denominada simplesmente CONTRATANTE")


def test_representante_sem_cpf_nao_deixa_lacuna():
    """Campo não preenchido não aparece — nem como linha para preencher.

    A versão anterior imprimia "inscrito no CPF sob o nº ______________". Um
    contrato com lacuna tem cara de rascunho indo para o cliente, e sugere que
    alguém pode completá-la DEPOIS da assinatura — que é exatamente o que não
    se quer num instrumento particular.
    """
    rep = RepresentanteLegal(nome="Ana")
    texto = rep.qualificacao_texto

    assert "______" not in texto
    assert "CPF" not in texto
    # O que foi informado continua saindo.
    assert "ANA" in texto
    assert "na qualidade de sócio administrador" in texto


def test_representante_com_cpf_mostra_o_cpf():
    """O outro lado da mesma regra: informado, aparece."""
    rep = RepresentanteLegal(nome="Ana", cpf="52998224725")
    assert "529.982.247-25" in rep.qualificacao_texto


# --------------------------------------------------------------------------- #
# Ponte com o dossiê                                                           #
# --------------------------------------------------------------------------- #
def _empresa() -> Empresa:
    return Empresa(
        cnpj="11222333000181",
        razao_social="Mercadinho São João Ltda",
        nome_fantasia="Mercadinho",
        endereco=END,
        emails=("financeiro@saojoao.com.br",),
        telefones=("(19) 3333-4444", "(19) 99999-8888"),
        # `optante_mei=False` explícito: a empresa é comprovadamente NÃO-MEI.
        # Antes o padrão do campo era `False` e bastava omitir; agora o padrão
        # é `None` (ninguém informou), e omitir aqui significaria outra coisa.
        optante_simples=True,
        optante_mei=False,
        situacao=SituacaoCadastral("ATIVA"),
        atividade_principal=AtividadeCNAE(
            "4712100", "Minimercados", classificar_cnae("4712100")
        ),
        socios=(
            Socio("MARIA DA SILVA", "Sócio-Administrador"),
            Socio("JOAO DA SILVA", "Sócio"),
        ),
        inscricoes_estaduais=("123456789 (SP) - [Ativa]",),
        data_abertura="2019-03-14",
    )


def test_de_empresa_reaproveita_dados_do_dossie():
    pj = de_empresa(_empresa())
    assert pj.razao_social == "Mercadinho São João Ltda"
    assert pj.cnpj == "11222333000181"
    assert pj.email == "financeiro@saojoao.com.br"
    assert pj.regime == "Simples Nacional"
    assert pj.endereco.municipio == "Jundiaí"


def test_de_empresa_usa_primeiro_telefone_apenas():
    """Contrato não pode levar dois telefones concatenados num campo só."""
    assert de_empresa(_empresa()).telefone == "(19) 3333-4444"


def test_de_empresa_seleciona_socio_do_qsa():
    pj = de_empresa(_empresa(), socio_escolhido="MARIA DA SILVA")
    assert pj.representante.nome == "MARIA DA SILVA"
    assert pj.representante.qualificacao == "Sócio-Administrador"


def test_de_empresa_nome_fora_do_qsa_vira_procurador():
    pj = de_empresa(_empresa(), socio_escolhido="Carlos Procurador")
    assert pj.representante.nome == "Carlos Procurador"
    assert pj.representante.qualificacao == "procurador(a)"


def test_de_empresa_sem_socio_escolhido_deixa_representante_vazio():
    assert not de_empresa(_empresa()).representante.esta_preenchido


def test_inscricao_municipal_placeholder_nao_vaza():
    """O dossiê usa 'Não identificada em busca pública' como padrão — isso não
    pode aparecer como se fosse um número de inscrição no contrato."""
    emp = _empresa()
    pj = de_empresa(emp)
    assert pj.inscricao_municipal == ""


# --------------------------------------------------------------------------- #
# Contratada                                                                    #
# --------------------------------------------------------------------------- #
def test_contratada_traz_dados_reais_da_mercabiliza():
    c = contratada_padrao()
    assert c.cnpj == "62350925000110"
    assert "MERCABILIZA" in c.razao_social
    assert c.endereco.municipio == "Jundiaí"


def test_contratada_sinaliza_pendencias_de_crc_e_cpf():
    """CRC e CPF do signatário não constam do cartão CNPJ — devem aparecer
    como pendência explícita, não sumir."""
    pend = contratada_padrao().pendencias
    assert any("CRC" in p for p in pend)
    assert any("CPF" in p for p in pend)


def test_contratada_sem_crc_omite_o_trecho():
    """Mesma regra da qualificação do representante, aplicada à CONTRATADA.

    Lembrando que a qualificação usada NO CONTRATO é o texto fixo da
    diretoria, que já traz o CRC por extenso. Esta propriedade alimenta a
    ficha cadastral.
    """
    texto = contratada_padrao().qualificacao_contratual
    assert "______" not in texto


# --------------------------------------------------------------------------- #
# Negrito nos dados identificadores                                            #
# --------------------------------------------------------------------------- #
def _pj() -> ContratantePJ:
    """PJ com todos os campos identificadores preenchidos."""
    return ContratantePJ(
        razao_social="Mercadinho São João Ltda",
        cnpj="11222333000181",
        natureza_juridica="Sociedade Empresária Limitada",
        endereco=END,
        representante=RepresentanteLegal(
            nome="Ana Costa",
            cpf="52998224725",
            rg="11.222.333",
            orgao_emissor="SSP/SP",
            estado_civil="casado",
            profissao="contador",
            qualificacao="sócio administrador",
            genero_feminino=True,
        ),
    )


def test_dados_identificadores_saem_em_negrito():
    """O contrato modelo destaca razão social, CNPJ, endereço e CEP. Isso não é
    estética: é o que faz o conferente achar os campos críticos de relance."""
    texto = _pj().qualificacao_contratual
    assert "**MERCADINHO SÃO JOÃO LTDA**" in texto
    assert "**11.222.333/0001-81**" in texto
    assert "**Rua Anchieta, 204, Vila Boaventura**" in texto
    assert "**CEP 13201-804**" in texto


def test_prosa_juridica_fica_sem_negrito():
    """Só o dado é destacado; o texto que liga os dados fica normal."""
    texto = _pj().qualificacao_contratual
    for termo in (
        "pessoa jurídica de direito privado",
        "inscrita no CNPJ sob o nº",
        "com sede na",
        "doravante denominada simplesmente CONTRATANTE",
    ):
        assert f"**{termo}**" not in texto
        assert termo in texto


def test_documentos_do_representante_em_negrito():
    texto = _pj().qualificacao_contratual
    assert "**529.982.247-25**" in texto  # CPF
    assert "**11.222.333**" in texto  # RG


def test_pf_destaca_nome_cpf_e_endereco():
    from src.core.pessoas import ContratantePF

    pf = ContratantePF(
        nome="Vinicius Almeida",
        cpf="11144477735",
        rg="98.765.432",
        orgao_emissor="SSP/RJ",
        estado_civil="solteiro",
        profissao="comerciante",
        endereco=Endereco(
            logradouro="Rua das Flores",
            numero="45",
            bairro="Centro",
            municipio="Macaé",
            uf="RJ",
            cep="27910000",
        ),
    )
    texto = pf.qualificacao_contratual
    assert "**VINICIUS ALMEIDA**" in texto
    assert "**111.444.777-35**" in texto
    assert "**Rua das Flores, 45, Centro**" in texto
    assert "**CEP 27910-000**" in texto
    # a qualificação civil digitada pelo usuário não é destacada
    assert "**comerciante**" not in texto


def test_campo_vazio_nao_gera_marcador_solto():
    """``n("")`` não pode devolver ``****``, que apareceria como asteriscos."""
    from src.core.pessoas import n

    assert n("") == ""
    assert n(None) == ""
    assert n("  ") == ""
    assert n("X") == "**X**"


def _fonte_de(pagina, trecho: str) -> str:
    """Fonte usada para renderizar ``trecho`` na página.

    Verificar "existe alguma fonte bold na página" é fraco: os títulos de
    cláusula já são bold e o teste passaria mesmo com o negrito inline
    quebrado — foi exatamente o que aconteceu antes de descobrir que faltava
    ``registerFontFamily``. Aqui casamos a fonte do caractere específico.
    """
    alvo = trecho.replace(" ", "")
    seq = "".join(c["text"] for c in pagina.chars).replace(" ", "")
    idx = seq.find(alvo)
    assert idx >= 0, f"trecho não encontrado no PDF: {trecho}"
    # reconstrói o índice ignorando espaços para achar o caractere certo
    vistos = 0
    for ch in pagina.chars:
        if ch["text"].strip() == "":
            continue
        if vistos == idx:
            return ch["fontname"]
        vistos += 1
    raise AssertionError("caractere não localizado")


def test_negrito_sobrevive_a_geracao_do_pdf():
    """O marcador ``**`` precisa virar ``<b>`` no PDF, não sair literal.

    Checa o texto extraído, não os bytes: o stream do PDF é binário e ``**``
    pode aparecer por coincidência dentro dele.
    """
    import io

    from src.core.contrato import ParametrosContrato
    from src.core.pessoas import contratada_padrao
    from src.exporters.pdf_contrato import gerar_contrato

    pdfplumber = pytest.importorskip("pdfplumber")

    pdf = gerar_contrato(
        _pj(), contratada_padrao(), ParametrosContrato(valor_mensal=350.0, foro="Campinas/SP")
    )
    assert pdf.startswith(b"%PDF")

    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        pagina = doc.pages[0]
        texto = pagina.extract_text() or ""
        fontes = {c["fontname"] for c in pagina.chars}

    assert "**" not in texto, "marcador markdown vazou para o texto do PDF"
    assert "MERCADINHO SÃO JOÃO LTDA" in texto
    assert any("bold" in f.lower() for f in fontes), (
        "nenhuma fonte em negrito foi usada na primeira página"
    )


def test_razao_social_e_cnpj_saem_em_fonte_negrito_no_pdf():
    """Regressão do bug do ``registerFontFamily``: sem ele, o ReportLab
    ignorava ``<b>`` para fonte TTF e o dado saía em peso normal."""
    import io

    from src.core.contrato import ParametrosContrato
    from src.core.pessoas import contratada_padrao
    from src.exporters.pdf_contrato import gerar_contrato

    pdfplumber = pytest.importorskip("pdfplumber")

    pdf = gerar_contrato(
        _pj(), contratada_padrao(), ParametrosContrato(valor_mensal=350.0, foro="Campinas/SP")
    )
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        pagina = doc.pages[0]
        fonte_razao = _fonte_de(pagina, "MERCADINHO")
        fonte_cnpj = _fonte_de(pagina, "11.222.333/0001-81")
        fonte_prosa = _fonte_de(pagina, "pessoa jurídica de direito privado")

    assert "bold" in fonte_razao.lower(), f"razão social em {fonte_razao}"
    assert "bold" in fonte_cnpj.lower(), f"CNPJ em {fonte_cnpj}"
    assert "bold" not in fonte_prosa.lower(), (
        f"prosa jurídica não deveria estar em negrito ({fonte_prosa})"
    )


# =========================================================================== #
# Limpeza do complemento vindo da Receita                                     #
# =========================================================================== #
# O campo `complemento` da base da Receita traz lixo de digitação de quem
# preencheu o cadastro. Um caso real, encontrado num contrato já emitido:
#     "CASA CASA CASA CASA ;CASA TERREO ;CASA TERREO"
# que saía assim mesmo no PDF, com o ";" colado na palavra seguinte.
@pytest.mark.parametrize(
    "bruto,esperado",
    [
        # O caso que motivou a correção
        ("CASA CASA CASA CASA ;CASA TERREO ;CASA TERREO", "CASA TERREO"),
        # Separador colado — a origem do "palavra ;palavra"
        ("FUNDOS ;FUNDOS", "FUNDOS"),
        ("LOJA;SOBRELOJA", "LOJA, SOBRELOJA"),
        # Repetição consecutiva
        ("LOJA LOJA 3", "LOJA 3"),
        ("CASA CASA", "CASA"),
        # Trecho contido em outro
        ("CASA;CASA TERREO;TERREO", "CASA TERREO"),
        # Vazio
        ("", ""),
        ("   ", ""),
        (";;", ""),
    ],
)
def test_complemento_limpo(bruto, esperado):
    from src.core.models import Endereco

    assert Endereco(complemento=bruto).complemento_limpo == esperado


@pytest.mark.parametrize(
    "intacto",
    [
        "SALA 102",
        "BLOCO A APTO 12",
        "ANDAR 3 SALA 5",
        "QUADRA 2 LOTE 7",
        "GALPAO",
    ],
)
def test_complemento_legitimo_nao_e_alterado(intacto):
    """A limpeza não pode comer complemento de verdade.

    Errar para o lado de limpar demais é pior que deixar sujo: um endereço
    incompleto no contrato pode inviabilizar a entrega de citação.
    """
    from src.core.models import Endereco

    assert Endereco(complemento=intacto).complemento_limpo == intacto


def test_numeros_parecidos_nao_se_engolem():
    """A comparação é por CONJUNTO DE PALAVRAS, não por prefixo de texto.

    Por prefixo, "SALA 1" seria engolido por "SALA 10" — endereços diferentes.
    """
    from src.core.models import Endereco

    assert Endereco(complemento="SALA 1;SALA 10").complemento_limpo == "SALA 1, SALA 10"


def test_complemento_sujo_nao_chega_ao_contrato():
    """Fecha o ciclo: da entrada suja até a linha que sai no PDF."""
    from src.core.models import Endereco

    e = Endereco(
        logradouro="RUA MARCOS MARCONDES",
        numero="95",
        complemento="CASA CASA CASA CASA ;CASA TERREO ;CASA TERREO",
        bairro="JARDIM AUDIR",
        municipio="Barueri",
        uf="SP",
        cep="06433050",
    )
    linha = e.linha_juridica_negrito
    assert " ;" not in linha
    assert "CASA CASA" not in linha
    assert "CASA TERREO" in linha
    assert "**Barueri/SP**" in linha


# --------------------------------------------------------------------------- #
# Regime tributário — ausência de informação não é negativa                    #
# --------------------------------------------------------------------------- #
def test_mei_confirmado_e_mei():
    e = Empresa(
        cnpj="11222333000181", razao_social="X", optante_simples=True, optante_mei=True
    )
    assert e.regime == "MEI"
    assert e.mei_confirmado


def test_simples_sim_e_mei_desconhecido_nao_vira_simples_puro():
    """O caso real: um MEI apareceu como "Simples Nacional / Anexo I / 4%".

    Todo MEI é optante do Simples. Então "Simples = sim, MEI = ?" é exatamente
    o formato que um MEI assume quando a base do provedor está desatualizada —
    comum em CNPJ aberto há pouco. Afirmar "Simples Nacional" aí é escolher no
    chute a resposta que erra por ordem de grandeza: 4% da receita contra DAS
    fixo de pouco mais de R$ 80 por mês.
    """
    e = Empresa(
        cnpj="11222333000181", razao_social="X", optante_simples=True, optante_mei=None
    )
    assert e.regime == "Simples Nacional (confirmar se é MEI)"
    assert e.regime_incerto
    assert not e.mei_confirmado


def test_nada_informado_nao_vira_lucro_presumido():
    """Era o comportamento antigo: os dois flags falsos caíam no último ramo
    do encadeamento, inclusive quando a razão era ausência de dado."""
    e = Empresa(cnpj="11222333000181", razao_social="X")
    assert e.regime == "Regime não informado pelos provedores"
    assert "Lucro" not in e.regime
    assert e.regime_incerto


def test_negativa_afirmativa_continua_valendo():
    e = Empresa(
        cnpj="11222333000181", razao_social="X", optante_simples=False, optante_mei=False
    )
    assert e.regime == "Lucro Presumido / Real"
    assert not e.regime_incerto


# --------------------------------------------------------------------------- #
# Representante informado só com o nome                                        #
# --------------------------------------------------------------------------- #
# O defeito: na aba Documentos dava para digitar "Gilberto Villela" no
# Representante legal, gerar o contrato, e a qualificação da CONTRATANTE sair
# SEM nenhuma menção a ele. Nenhum aviso, nenhum campo em branco — o nome
# simplesmente não aparecia, e a leitura natural era "esse campo não é usado".
#
# Causa: o portão era `representante.esta_preenchido`, que exige nome E CPF.
# Sem o CPF, o bloco inteiro era pulado. E era desnecessário: o texto que ele
# protegia já sabia lidar com CPF ausente, imprimindo uma lacuna.
def test_representante_so_com_nome_entra_na_qualificacao():
    pj = ContratantePJ(
        razao_social="63.506.742 LARISSA RIBEIRO DE SOUZA",
        cnpj="63506742000103",
        natureza_juridica="Empresário (Individual)",
        endereco=END,
        representante=RepresentanteLegal(nome="Gilberto Villela"),
    )
    texto = pj.qualificacao_contratual

    assert "GILBERTO VILLELA" in texto
    assert "neste ato representado por" in texto
<<<<<<< Updated upstream
    # A lacuna do CPF fica visível, para preencher à mão na assinatura.
    assert "______" in texto
=======
    # E sem lacuna: o CPF que ele não preencheu simplesmente não é mencionado.
    assert "______" not in texto
    assert "CPF" not in texto.split("representado por")[1]
>>>>>>> Stashed changes


def test_sem_nome_nenhum_o_bloco_continua_fora():
    """O portão ficou mais frouxo, não inexistente: sem nome não há quem
    assine, e inventar 'representado por (não informado)' seria pior."""
    pj = ContratantePJ(
        razao_social="Mercadinho São João Ltda",
        cnpj="11222333000181",
        endereco=END,
        representante=RepresentanteLegal(cpf="52998224725"),
    )
    assert "neste ato" not in pj.qualificacao_contratual


def test_nome_em_branco_nao_conta_como_preenchido():
    pj = ContratantePJ(
        razao_social="Mercadinho São João Ltda",
        cnpj="11222333000181",
        endereco=END,
        representante=RepresentanteLegal(nome="   "),
    )
    assert "neste ato" not in pj.qualificacao_contratual


def test_falta_do_cpf_vira_pendencia_propria():
    """Nome e CPF são pendências separadas: uma impede, a outra só atrasa."""
    pj = ContratantePJ(
        razao_social="Mercadinho São João Ltda",
        cnpj="11222333000181",
        endereco=END,
        email="a@b.com",
        representante=RepresentanteLegal(nome="Gilberto Villela"),
    )
    pendencias = pj.pendencias
    assert any("CPF do representante" in p for p in pendencias)
    assert not any("nome do representante" in p for p in pendencias)
