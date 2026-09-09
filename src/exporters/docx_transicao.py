"""Formulário de Entrada de Novos Clientes — Transição Contábil, em DOCX.

Substitui a planilha ``FORMULÁRIO DE ENTRADA DE NOVOS CLIENTES`` que a equipe
preenchia à mão. Mantém todos os campos dela, na mesma ordem e com os mesmos
agrupamentos por departamento, e acrescenta duas coisas que a planilha não
tinha:

1. **Prefill.** Razão social, CNPJ, segmento, regime, responsável legal e
   contatos saem da consulta de CNPJ já preenchidos e em negrito. Na planilha
   isso era digitação, com o risco de erro que digitação sempre tem.

2. **A seção de sucessão contábil.** A planilha pedia só o e-mail e o telefone
   da contabilidade anterior. Aqui o cliente também **vê a lista do que será
   solicitado** ao contador que está saindo.

   A lista é informativa de propósito: quem solicita é a Mercabiliza, não o
   cliente. Ela existe para o cliente entender o que vem pela frente e não se
   assustar quando o contador anterior o procurar. Levantamento de documento é
   a etapa que mais atrasa transição, e quase sempre porque o cliente não sabia
   que precisava autorizar.

## Por que um formulário separado do de abertura

Parecem o mesmo documento e não são. Na abertura **não existe empresa** — todo
o bloco cadastral é decisão a tomar (razão social em três opções, capital
social, distribuição de quotas). Na transição a empresa existe há anos: o
cadastral é conferência, e o que interessa é o operacional que nenhuma API
traz — quantos funcionários, se tem pró-labore, qual sistema de notas, quem era
o contador anterior.

Juntar os dois num só produziria um documento com metade dos campos sempre
inaplicáveis, e a experiência com a planilha é justamente que campo
inaplicável não é ignorado: é preenchido errado.
"""

from __future__ import annotations

import io
from datetime import date

from docx import Document
from docx.shared import Pt

from ..core.cnpj import formatar as formatar_cnpj
from ..core.cpf import formatar as formatar_cpf
from .docx_base import (
    COR_CINZA,
    MARCADOR_PENDENTE,
    Campo,
    Secao,
    cabecalho,
    configurar_pagina,
    legenda,
    rodape_declaracao,
    run,
    tabela_campos,
    titulo_secao,
)

__all__ = [
    "CAMPOS_POR_BLOCO",
    "DOCUMENTOS_A_SOLICITAR",
    "MARCADOR_PENDENTE",
    "CampoDesconhecidoError",
    "dados_de_contratante",
    "gerar_formulario_transicao",
]


class CampoDesconhecidoError(ValueError):
    """Chave que este formulário não conhece.

    ⚠️ Por que isto é erro em vez de ser ignorado.

    As seções leem os dados com ``.get(chave, "")``. Uma chave escrita errada
    — ``tem_funcionario`` sem o "s" — não estoura: o ``.get`` devolve vazio, o
    campo sai como ``[ PREENCHER AQUI ]``, e o documento chega ao cliente com
    uma pergunta que a equipe já tinha respondido. Ninguém descobre, porque um
    formulário com campo em branco é indistinguível de um formulário com campo
    em branco de propósito.

    É a mesma classe de falha do ``valor_mesal`` no schema do contrato, e a
    resposta é a mesma: falhar alto, na hora, apontando a chave.
    """


# Fonte única das chaves aceitas por bloco. Serve a três coisas: validar a
# entrada, documentar o contrato para quem chama, e permitir que o teste
# compare com o schema da API — sem isso os dois divergem no primeiro campo
# novo, e a divergência só aparece no documento gerado.
CAMPOS_POR_BLOCO: dict[str, frozenset[str]] = {
    "iniciais": frozenset({
        "modelo_entrada", "competencia", "razao_social", "cnpj", "nome_fantasia",
        "inscricao_estadual", "segmento", "regime", "faturamento", "tem_filiais",
        "cnpj_filiais", "qtd_socios", "responsavel", "cpf_responsavel",
        "email1", "email2", "telefone1", "telefone2",
    }),
    "pessoal": frozenset({
        "tem_funcionarios", "qtd_funcionarios", "pro_labore", "adiantamento",
        "fechamento_folha", "sindicato",
    }),
    "fiscal": frozenset({
        "certificado", "validade_certificado", "sistema_notas",
        "tipo_empresa", "regime_tributario", "nfce",
    }),
    "sucessao": frozenset({
        "contador_anterior", "email_anterior", "telefone_anterior",
    }),
}


def _validar(bloco: str, dados: dict) -> dict:
    """Recusa chave desconhecida, sugerindo a mais parecida."""
    conhecidas = CAMPOS_POR_BLOCO[bloco]
    intrusas = sorted(set(dados) - conhecidas)
    if intrusas:
        import difflib

        detalhes = []
        for chave in intrusas:
            perto = difflib.get_close_matches(chave, conhecidas, n=1, cutoff=0.6)
            detalhes.append(f"{chave!r}" + (f" (quis dizer {perto[0]!r}?)" if perto else ""))
        raise CampoDesconhecidoError(
            f"Campo desconhecido no bloco {bloco!r}: {', '.join(detalhes)}. "
            f"Aceitos: {', '.join(sorted(conhecidas))}."
        )
    return dados

# ⚠️ Redação ajustada quando a assinatura saiu do documento (revisão de
# 09/09/2026). A versão anterior dizia "declaro... e AUTORIZO a Mercabiliza a
# solicitar...". Sem linha de assinatura não há quem declare nem quem autorize,
# e um documento que afirma conceder uma autorização que ninguém assinou é pior
# que um documento sem o texto: o contador anterior pode recusar a entrega, e
# aí a transição trava justamente onde este formulário deveria destravar.
#
# Agora o texto INFORMA em vez de declarar. A autorização formal continua
# existindo — ela está no contrato de prestação de serviços, que é assinado.
DECLARACAO = (
    "as informações deste formulário serão usadas para a execução dos serviços "
    "contábeis contratados e para a solicitação, junto à contabilidade "
    "anterior, dos documentos e arquivos digitais relacionados acima, nos "
    "termos da Lei nº 13.709/2018 (LGPD). A autorização para essa solicitação "
    "consta do contrato de prestação de serviços firmado com a Mercabiliza."
)


# --------------------------------------------------------------------------- #
# O que se pede à contabilidade anterior                                       #
# --------------------------------------------------------------------------- #
# Agrupado por quem responde do outro lado: é assim que o pedido sai por
# e-mail, e assim que dá para cobrar parcialmente ("o fiscal chegou, falta o
# pessoal") em vez de tratar a transição como um bloco de tudo-ou-nada.
#
# O corte de 5 anos não é arbitrário: é o prazo de decadência e prescrição
# tributária do CTN (arts. 173 e 174). Documento mais antigo que isso o Fisco
# já não pode exigir, e pedir "tudo desde a abertura" é o tipo de pedido amplo
# que o contador anterior demora a atender ou simplesmente ignora.
DOCUMENTOS_A_SOLICITAR: dict[str, tuple[str, ...]] = {
    "Contábil": (
        "Balancetes mensais e Balanço Patrimonial dos últimos exercícios",
        "DRE dos últimos exercícios",
        "Livro Diário e Livro Razão",
        "ECD e ECF transmitidas (arquivos e recibos)",
        "Composição dos saldos: caixa, bancos, clientes, fornecedores e "
        "empréstimos na data da transferência",
        "Relação do ativo imobilizado com depreciação acumulada",
    ),
    "Fiscal": (
        "SPED Fiscal (EFD ICMS/IPI) e SPED Contribuições dos últimos 5 anos",
        "PGDAS-D e DEFIS dos últimos 5 anos, se optante pelo Simples Nacional",
        "XMLs das notas fiscais emitidas e recebidas",
        "Guias pagas: DAS, DARF, ICMS e demais tributos",
        "Parcelamentos ativos, com número, saldo e situação",
        "Certidões negativas (federal, estadual e municipal)",
    ),
    "Pessoal": (
        "Folha de pagamento dos últimos 12 meses",
        "Fichas de registro dos empregados e contratos de trabalho",
        "Guias de FGTS e INSS pagas",
        "eSocial, DCTFWeb e RAIS/CAGED transmitidos",
        "Rescisões e férias em aberto, com provisões",
        "Convenção coletiva aplicável à categoria",
    ),
    "Societário e acessos": (
        "Contrato social e todas as alterações",
        "Cartão CNPJ, inscrições estadual e municipal, alvarás e licenças",
        "Procuração eletrônica no e-CAC (ou certificado digital e-CNPJ válido)",
        "Acessos aos portais estadual e municipal",
        "Senha do Simples Nacional e do DTE (Domicílio Tributário Eletrônico)",
    ),
}


# --------------------------------------------------------------------------- #
# Seções                                                                       #
# --------------------------------------------------------------------------- #
def _secao_iniciais(dados: dict) -> Secao:
    """Bloco INFORMAÇÕES INICIAIS da planilha."""
    return Secao("Informações iniciais", [
        Campo("Modelo de entrada", dados.get("modelo_entrada", "Transição contábil")),
        Campo("Competência de entrada", dados.get("competencia", ""), pendente=True,
              dica="Mês/ano em que assumimos a escrita — ex.: 09/2026"),
        Campo("Razão social", dados.get("razao_social", "")),
        Campo("CNPJ", dados.get("cnpj", "")),
        Campo("Nome fantasia", dados.get("nome_fantasia", "")),
        Campo("Inscrição estadual", dados.get("inscricao_estadual", "")),
        Campo("Segmento da empresa", dados.get("segmento", ""), pendente=True,
              dica="Ex.: supermercado, minimercado autônomo, salão de beleza"),
        Campo("Regime tributário atual", dados.get("regime", "")),
        Campo("Faturamento mensal médio", dados.get("faturamento", ""), pendente=True),
        Campo("Tem filiais?", dados.get("tem_filiais", ""), pendente=True),
        Campo("CNPJ das filiais", dados.get("cnpj_filiais", ""),
              dica="Uma por linha, se houver"),
        Campo("Quantos sócios?", dados.get("qtd_socios", ""), pendente=True),
        Campo("Responsável legal", dados.get("responsavel", "")),
        Campo("CPF do responsável", dados.get("cpf_responsavel", "")),
        Campo("E-mail 1", dados.get("email1", "")),
        Campo("E-mail 2", dados.get("email2", "")),
        Campo("Telefone 1", dados.get("telefone1", "")),
        Campo("Telefone 2", dados.get("telefone2", "")),
    ])


def _secao_pessoal(dados: dict) -> Secao:
    return Secao("Departamento pessoal", [
        Campo("Tem funcionários?", dados.get("tem_funcionarios", ""), pendente=True),
        Campo("Se sim, quantos?", dados.get("qtd_funcionarios", "")),
        Campo("Terá pró-labore?", dados.get("pro_labore", ""), pendente=True),
        Campo("Terá adiantamento salarial?", dados.get("adiantamento", ""),
              pendente=True),
        Campo("Data de fechamento da folha", dados.get("fechamento_folha", ""),
              dica="Dia do mês em que a folha é fechada"),
        Campo("Sindicato / convenção coletiva", dados.get("sindicato", "")),
    ])


def _secao_fiscal(dados: dict) -> Secao:
    return Secao("Departamento fiscal", [
        Campo("Possui certificado digital válido?", dados.get("certificado", ""),
              pendente=True),
        Campo("Validade do certificado", dados.get("validade_certificado", "")),
        Campo("Sistema de notas utilizado", dados.get("sistema_notas", ""),
              pendente=True),
        Campo("Tipo de empresa", dados.get("tipo_empresa", ""), pendente=True,
              dica="Comércio, indústria ou serviços"),
        Campo("Regime tributário", dados.get("regime_tributario", ""), pendente=True),
        Campo("Emite NFC-e / cupom fiscal?", dados.get("nfce", "")),
    ])


def _bloco_sucessao(doc, dados: dict) -> None:
    """Contato da contabilidade anterior + o que será pedido a ela.

    A metade de cima é formulário (a equipe precisa do contato). A de baixo é
    informativa: quem solicita é a Mercabiliza. A distinção está escrita no
    documento porque, sem ela, o cliente lê a lista como tarefa dele e trava.
    """
    titulo_secao(doc, "Sucessão contábil — contabilidade anterior")

    tabela_campos(doc, [
        Campo("Nome do escritório / contador", dados.get("contador_anterior", ""),
              pendente=True),
        Campo("E-mail", dados.get("email_anterior", ""), pendente=True),
        Campo("Telefone", dados.get("telefone_anterior", ""), pendente=True),
    ])

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    run(p, "O que faremos a seguir — você não precisa providenciar nada disto. ",
        negrito=True, tamanho=8.5)
    run(p,
        "Com o contrato firmado e este formulário devolvido, nós mesmos "
        "entramos em contato com a contabilidade anterior e solicitamos os "
        "itens abaixo. Estamos listando para que você acompanhe o processo e "
        "saiba o que esperar — é comum o contador anterior procurar você para "
        "confirmar a autorização, que já consta do contrato assinado.",
        tamanho=8.5)

    for grupo, itens in DOCUMENTOS_A_SOLICITAR.items():
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(1)
        run(p, grupo, negrito=True, tamanho=8.5)
        for item in itens:
            linha = doc.add_paragraph()
            linha.paragraph_format.space_after = Pt(0)
            linha.paragraph_format.left_indent = Pt(12)
            run(linha, f"•  {item}", tamanho=8)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    run(p,
        "Prazo: pedimos os documentos dos últimos 5 exercícios, que é o "
        "período em que o Fisco ainda pode exigi-los. O levantamento costuma "
        "levar de 15 a 30 dias, e é a etapa que mais atrasa uma transição — "
        "por isso ela começa no primeiro dia.",
        tamanho=8, italico=True, cor=COR_CINZA)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


# --------------------------------------------------------------------------- #
# Entrada pública                                                              #
# --------------------------------------------------------------------------- #
def gerar_formulario_transicao(
    dados_iniciais: dict | None = None,
    dados_pessoal: dict | None = None,
    dados_fiscal: dict | None = None,
    dados_sucessao: dict | None = None,
) -> bytes:
    """Monta o formulário de transição e devolve os bytes do ``.docx``.

    Todo argumento é opcional: sem nenhum dado, sai o formulário em branco —
    equivalente à planilha atual, e utilizável como impresso.
    """
    doc = Document()
    configurar_pagina(doc)
    cabecalho(
        doc,
        "FORMULÁRIO DE ENTRADA DE NOVOS CLIENTES",
        f"Transição contábil · emitido em {date.today():%d/%m/%Y}",
    )
    legenda(doc)

    secoes = [
        _secao_iniciais(_validar("iniciais", dados_iniciais or {})),
        _secao_pessoal(_validar("pessoal", dados_pessoal or {})),
        _secao_fiscal(_validar("fiscal", dados_fiscal or {})),
    ]
    for secao in secoes:
        titulo_secao(doc, secao.titulo)
        tabela_campos(doc, secao.campos, secao.colunas)

    _bloco_sucessao(doc, _validar("sucessao", dados_sucessao or {}))

    rodape_declaracao(doc, DECLARACAO)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def dados_de_contratante(contratante) -> dict:
    """Extrai do contratante consultado o que já dá para preencher sozinho.

    Devolve o dicionário de ``dados_iniciais``. Só entra aqui o que vem de
    fonte oficial — o resto é decisão ou apuração da equipe e sai como
    ``[ PREENCHER AQUI ]``.
    """
    from ..core.pessoas import ContratantePJ

    if not isinstance(contratante, ContratantePJ):
        # Transição contábil pressupõe empresa constituída. Para PF só dá para
        # aproveitar o contato — o resto do formulário não se aplica.
        return {
            "responsavel": getattr(contratante, "nome", ""),
            "cpf_responsavel": (
                formatar_cpf(contratante.cpf) if getattr(contratante, "cpf", "") else ""
            ),
            "email1": getattr(contratante, "email", ""),
            "telefone1": getattr(contratante, "telefone", ""),
        }

    rep = contratante.representante
    return {
        "razao_social": contratante.razao_social,
        "cnpj": formatar_cnpj(contratante.cnpj) if contratante.cnpj else "",
        "nome_fantasia": contratante.nome_fantasia,
        "inscricao_estadual": getattr(contratante, "inscricao_estadual", "") or "",
        "regime": contratante.regime,
        # O CNAE é a melhor aproximação de "segmento" que a Receita dá, mas
        # NÃO é a resposta: a planilha quer "minimercado autônomo", e o CNAE
        # diz "comércio varejista de mercadorias em geral". Vai como dica para
        # a equipe confirmar, não como valor preenchido — daí o campo seguir
        # pendente na seção.
        "responsavel": rep.nome if rep and rep.nome else "",
        "cpf_responsavel": formatar_cpf(rep.cpf) if rep and rep.cpf else "",
        "email1": contratante.email,
        "telefone1": contratante.telefone,
    }
