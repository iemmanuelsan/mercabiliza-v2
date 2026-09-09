"""API de documentos — contrato, ficha cadastral e formulário de abertura.

## Por que este arquivo existe

O front-end web (Next.js na Netlify) não consegue gerar estes documentos. O
ReportLab Platypus faz coisas sem equivalente direto em JavaScript: texto
jurídico justificado com controle de viúvas e órfãs, ``KeepTogether`` para não
partir cláusula entre páginas, "Página X de Y" com build em duas passadas e o
papel timbrado como fundo de página inteira.

Esse código já existe, está testado e gera os documentos que a Mercabiliza
manda para cliente hoje. Reescrever seria trocar código provado por código
novo na parte mais delicada do sistema. Então em vez disso ele é exposto como
API, e a web chama.

## O que este arquivo NÃO faz

Nada de novo. Ele é uma casca fina em volta de ``src/exporters``: recebe JSON,
monta os mesmos objetos que a aba Streamlit monta, chama as mesmas funções e
devolve os bytes. Se o documento sai errado aqui, sai errado no Streamlit
também — e é lá que se corrige.

## Rodar local

    pip install -r requirements.txt -r requirements-api.txt
    DOCUMENTOS_API_KEY=chave-de-teste uvicorn api:app --reload --port 8000

    curl -s -X POST http://localhost:8000/v1/ficha \\
      -H "X-API-Key: chave-de-teste" -H "Content-Type: application/json" \\
      -d @exemplo.json --output ficha.pdf

## Deploy

Render, com o mesmo repositório do app Streamlit. Ver DEPLOY_API.md.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from src.core.contrato import ParametrosContrato, TemplateContratoAusente
from src.core.models import Endereco
from src.core.pessoas import (
    Contratada,
    ContratantePF,
    ContratantePJ,
    RepresentanteLegal,
    contratada_padrao,
)
from src.exporters.docx_abertura import (
    dados_de_contratante,
    gerar_formulario_abertura,
)
from src.exporters.docx_transicao import (
    dados_de_contratante as dados_de_contratante_transicao,
    gerar_formulario_transicao,
)
from src.exporters.pdf_documentos import gerar_contrato, gerar_ficha_cadastral

logging.basicConfig(level=os.getenv("MERCABILIZA_LOG_LEVEL", "INFO"))
logger = logging.getLogger("api.documentos")

app = FastAPI(
    title="Mercabiliza — API de documentos",
    version="1.0.0",
    description="Gera contrato, ficha cadastral e os formulários de abertura e de transição contábil.",
)


# --------------------------------------------------------------------------- #
# Autenticação                                                                #
# --------------------------------------------------------------------------- #
# Chave compartilhada, não OAuth. A razão: quem chama esta API é o SERVIDOR do
# Next.js, nunca um navegador. Não há usuário para autenticar aqui — a
# identidade de quem pediu o documento já foi verificada pelo Clerk antes.
#
# O que esta chave impede é alguém que descobriu a URL da API gerar documentos
# com o timbrado da Mercabiliza. Sem ela, a API seria uma fábrica aberta de
# documentos com a marca da empresa.
def exigir_chave(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    esperada = os.getenv("DOCUMENTOS_API_KEY", "")
    if not esperada:
        # Falha fechada: sem chave configurada a API não atende ninguém.
        # O contrário — abrir por falta de configuração — seria a pior falha
        # possível num serviço que estampa o timbrado da empresa.
        logger.error("DOCUMENTOS_API_KEY não configurada; recusando tudo.")
        raise HTTPException(503, "Serviço não configurado.")

    # compare_digest em vez de ==: a comparação ingênua para no primeiro byte
    # diferente, e a diferença de tempo permite descobrir a chave.
    if not x_api_key or not hmac.compare_digest(x_api_key, esperada):
        raise HTTPException(401, "Chave de API inválida ou ausente.")


Protegido = Depends(exigir_chave)


# --------------------------------------------------------------------------- #
# Schemas de entrada                                                          #
# --------------------------------------------------------------------------- #
class Estrito(BaseModel):
    """Base de todos os schemas: campo desconhecido é ERRO, não é ignorado.

    O padrão do Pydantic é ignorar em silêncio, e para uma API pública isso é
    resiliência. Aqui é o contrário: quem chama é um cliente só (o servidor do
    Next.js), sob nosso controle, e o que sai daqui é documento com valor
    jurídico.

    Nesse cenário, ignorar campo desconhecido significa que um nome digitado
    errado — ``valor_mesal`` em vez de ``valor_mensal`` — gera um contrato com
    o valor PADRÃO, sem erro nenhum, e ninguém descobre até o cliente
    questionar a cobrança. É a mesma classe de falha do ``incluir_dp``.

    Com ``extra="forbid"`` o erro aparece na hora, como 422, apontando o campo.
    """

    model_config = ConfigDict(extra="forbid")


class EnderecoIn(Estrito):
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    cep: str = ""

    def para_dominio(self) -> Endereco:
        return Endereco(
            logradouro=self.logradouro, numero=self.numero,
            complemento=self.complemento, bairro=self.bairro,
            municipio=self.municipio, uf=self.uf, cep=self.cep,
        )


class RepresentanteIn(Estrito):
    nome: str = ""
    cpf: str = ""
    rg: str = ""
    orgao_emissor: str = ""
    nacionalidade: str = "brasileiro"
    estado_civil: str = ""
    profissao: str = ""
    qualificacao: str = "sócio administrador"
    genero_feminino: bool = False

    def para_dominio(self) -> RepresentanteLegal:
        return RepresentanteLegal(
            nome=self.nome, cpf=self.cpf, rg=self.rg,
            orgao_emissor=self.orgao_emissor, nacionalidade=self.nacionalidade,
            estado_civil=self.estado_civil, profissao=self.profissao,
            qualificacao=self.qualificacao, genero_feminino=self.genero_feminino,
        )


class ContratantePJIn(Estrito):
    tipo: Literal["PJ"] = "PJ"
    razao_social: str
    nome_fantasia: str = ""
    cnpj: str
    cnae_principal: str = ""
    endereco: EnderecoIn = Field(default_factory=EnderecoIn)
    telefone: str = ""
    email: str = ""
    inscricao_estadual: str = ""
    inscricao_municipal: str = ""
    representante: RepresentanteIn = Field(default_factory=RepresentanteIn)
    regime: str = ""
    data_abertura: str = ""
    natureza_juridica: str = ""

    def para_dominio(self) -> ContratantePJ:
        return ContratantePJ(
            razao_social=self.razao_social, nome_fantasia=self.nome_fantasia,
            cnpj=self.cnpj, cnae_principal=self.cnae_principal,
            endereco=self.endereco.para_dominio(),
            telefone=self.telefone, email=self.email,
            inscricao_estadual=self.inscricao_estadual,
            inscricao_municipal=self.inscricao_municipal,
            representante=self.representante.para_dominio(),
            regime=self.regime, data_abertura=self.data_abertura,
            natureza_juridica=self.natureza_juridica,
        )


class ContratantePFIn(Estrito):
    tipo: Literal["PF"] = "PF"
    nome: str
    cpf: str
    rg: str = ""
    orgao_emissor: str = ""
    nacionalidade: str = "brasileiro"
    estado_civil: str = ""
    profissao: str = ""
    endereco: EnderecoIn = Field(default_factory=EnderecoIn)
    telefone: str = ""
    email: str = ""
    genero_feminino: bool = False

    def para_dominio(self) -> ContratantePF:
        return ContratantePF(
            nome=self.nome, cpf=self.cpf, rg=self.rg,
            orgao_emissor=self.orgao_emissor, nacionalidade=self.nacionalidade,
            estado_civil=self.estado_civil, profissao=self.profissao,
            endereco=self.endereco.para_dominio(),
            telefone=self.telefone, email=self.email,
            genero_feminino=self.genero_feminino,
        )


ContratanteIn = ContratantePJIn | ContratantePFIn


class ParametrosIn(Estrito):
    """Parâmetros do contrato. **Todo campo é opcional, e o default é None.**

    ⚠️ Não escreva valor padrão nenhum aqui. Isso não é preferência de estilo:
       a primeira versão deste schema repetia os padrões à mão e errou dois —
       ``incluir_dp`` e ``incluir_monofasico`` ficaram ``False`` quando o
       padrão real é ``True``. O efeito foi que o contrato gerado pela API
       saía **sem a cláusula trabalhista/previdenciária e sem a de
       monofásico**, silenciosamente, diferente do que a Mercabiliza manda
       para cliente hoje. Um documento com valor jurídico, com cláusula
       faltando, e nada acusando.

       Com ``None`` em tudo e ``exclude_none``, o dataclass
       ``ParametrosContrato`` volta a ser a ÚNICA fonte da verdade dos
       padrões. Se um padrão mudar lá, este arquivo acompanha sozinho.

       O teste ``test_api_e_streamlit_geram_o_MESMO_contrato`` existe para
       impedir que essa divergência volte.
    """

    objeto: str | None = None
    valor_mensal: float | None = None
    valor_implantacao: float | None = None
    dia_vencimento: int | None = None
    forma_pagamento: str | None = None
    data_inicio: date | None = None
    vigencia_meses: int | None = None
    indice_reajuste: str | None = None
    prazo_rescisao_dias: int | None = None
    multa_atraso_pct: float | None = None
    juros_mora_mes_pct: float | None = None
    foro: str | None = None
    cidade_assinatura: str | None = None
    data_assinatura: date | None = None
    incluir_dp: bool | None = None
    incluir_monofasico: bool | None = None
    clausulas_particulares: list[str] | None = None

    def para_dominio(self) -> ParametrosContrato:
        # exclude_none: o que o chamador não mandou simplesmente não vai, e o
        # dataclass aplica o próprio padrão.
        campos = self.model_dump(exclude_none=True)
        if "clausulas_particulares" in campos:
            campos["clausulas_particulares"] = tuple(campos["clausulas_particulares"])
        return ParametrosContrato(**campos)


class PedidoContrato(Estrito):
    contratante: ContratanteIn
    parametros: ParametrosIn = Field(default_factory=ParametrosIn)
    # False por padrão: o modelo da Mercabiliza não usa mais testemunhas
    # (revisão de 01/09/2026).
    com_testemunhas: bool = False
    template: str | None = None


class PedidoFicha(Estrito):
    contratante: ContratanteIn
    incluir_pendencias: bool = True


class DesenquadramentoIn(Estrito):
    cnpj: str = ""
    razao_atual: str = ""
    abertura: str = ""
    ie: str = ""


class PedidoFormulario(Estrito):
    """Formulário DOCX de abertura ou desenquadramento.

    ``perfil`` define o que o documento pede:
      * ``PJ``  — empresa já constituída (alteração cadastral)
      * ``MEI`` — desenquadramento, ganha o bloco específico
      * ``PF``  — abertura: não há empresa ainda, o bloco todo é do cliente
    """

    contratante: ContratanteIn
    perfil: Literal["PJ", "MEI", "PF"]
    desenquadramento: DesenquadramentoIn | None = None


class BlocoTransicao(Estrito):
    """Base dos blocos de resposta do formulário de transição.

    ⚠️ Duas regras valem para TODAS as subclasses:

    1. **Nenhum campo pode ter valor padrão — todos são ``None``.** É a mesma
       regra do ``ParametrosIn``, e pelo mesmo motivo: quando o schema da API
       repete um padrão que já existe no domínio, os dois divergem no primeiro
       dia em que alguém muda um lado, e o documento gerado pela API passa a
       sair diferente do gerado pela tela, sem ninguém perceber. O
       ``modelo_entrada`` é o caso concreto: "Transição contábil" mora no
       exportador, e escrevê-lo aqui criaria a segunda fonte.

    2. **Os nomes dos campos são exatamente as chaves de
       ``CAMPOS_POR_BLOCO``**, do exportador. Há teste comparando os dois
       conjuntos: um campo novo em um lado sem o outro quebra o teste em vez
       de virar um campo que não aparece no documento.
    """

    def para_dicionario(self) -> dict:
        # exclude_none + descarte de string vazia: o que não veio simplesmente
        # não chega ao exportador, e o padrão aplicado é sempre o dele.
        return {k: v for k, v in self.model_dump(exclude_none=True).items()
                if str(v).strip() != ""}


class IniciaisIn(BlocoTransicao):
    modelo_entrada: str | None = None
    competencia: str | None = None
    razao_social: str | None = None
    cnpj: str | None = None
    nome_fantasia: str | None = None
    inscricao_estadual: str | None = None
    segmento: str | None = None
    regime: str | None = None
    faturamento: str | None = None
    tem_filiais: str | None = None
    cnpj_filiais: str | None = None
    qtd_socios: str | None = None
    responsavel: str | None = None
    cpf_responsavel: str | None = None
    email1: str | None = None
    email2: str | None = None
    telefone1: str | None = None
    telefone2: str | None = None


class PessoalIn(BlocoTransicao):
    tem_funcionarios: str | None = None
    qtd_funcionarios: str | None = None
    pro_labore: str | None = None
    adiantamento: str | None = None
    fechamento_folha: str | None = None
    sindicato: str | None = None


class FiscalIn(BlocoTransicao):
    certificado: str | None = None
    validade_certificado: str | None = None
    sistema_notas: str | None = None
    tipo_empresa: str | None = None
    regime_tributario: str | None = None
    nfce: str | None = None


class SucessaoIn(BlocoTransicao):
    contador_anterior: str | None = None
    email_anterior: str | None = None
    telefone_anterior: str | None = None


class PedidoTransicao(Estrito):
    """Formulário DOCX de entrada de novo cliente por transição contábil.

    ``contratante`` é opcional: sem ele o documento sai em branco, que é
    exatamente o impresso que a equipe usava antes na planilha. Com ele, o
    bloco cadastral já vem preenchido e o cliente só confere.
    """

    contratante: ContratanteIn | None = None
    iniciais: IniciaisIn = Field(default_factory=IniciaisIn)
    pessoal: PessoalIn = Field(default_factory=PessoalIn)
    fiscal: FiscalIn = Field(default_factory=FiscalIn)
    sucessao: SucessaoIn = Field(default_factory=SucessaoIn)


# --------------------------------------------------------------------------- #
# Auxiliares                                                                  #
# --------------------------------------------------------------------------- #
def _contratada() -> Contratada:
    return contratada_padrao()


def _arquivo(conteudo: bytes, nome: str, mime: str) -> Response:
    return Response(
        content=conteudo,
        media_type=mime,
        headers={
            # `attachment` para o navegador baixar em vez de tentar exibir.
            # O nome do arquivo importa: o cliente recebe "contrato-mercado
            # -teste.pdf", não "download.pdf".
            "Content-Disposition": f'attachment; filename="{nome}"',
            "Cache-Control": "no-store",
        },
    )


def _slug(texto: str) -> str:
    import re
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", texto or "documento")
    sem_acento = sem_acento.encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower()
    return limpo[:60] or "documento"


PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# --------------------------------------------------------------------------- #
# Rotas                                                                       #
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, object]:
    """Sem autenticação de propósito: é o que a plataforma consulta.

    Reporta se a chave está configurada — assim um deploy sem a variável é
    detectável sem precisar tentar gerar um documento.
    """
    return {
        "ok": True,
        "chave_configurada": bool(os.getenv("DOCUMENTOS_API_KEY", "")),
    }


@app.post("/v1/contrato", dependencies=[Protegido])
def contrato(pedido: PedidoContrato) -> Response:
    contratante = pedido.contratante.para_dominio()
    try:
        pdf = gerar_contrato(
            contratante,
            _contratada(),
            pedido.parametros.para_dominio(),
            com_testemunhas=pedido.com_testemunhas,
            template=pedido.template,
        )
    except TemplateContratoAusente as exc:
        # 500 e não 400: o pedido estava certo, o servidor está mal instalado
        # (pasta templates/ não versionada). A distinção evita o front culpar
        # o usuário por um problema de deploy.
        raise HTTPException(500, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, f"Dados insuficientes para o contrato: {exc}") from exc

    nome = getattr(contratante, "razao_social", None) or getattr(contratante, "nome", "")
    logger.info("Contrato gerado para %s (%d bytes)", nome, len(pdf))
    return _arquivo(pdf, f"contrato-{_slug(nome)}.pdf", PDF)


@app.post("/v1/ficha", dependencies=[Protegido])
def ficha(pedido: PedidoFicha) -> Response:
    contratante = pedido.contratante.para_dominio()
    try:
        pdf = gerar_ficha_cadastral(
            contratante, incluir_pendencias=pedido.incluir_pendencias
        )
    except ValueError as exc:
        raise HTTPException(422, f"Dados insuficientes para a ficha: {exc}") from exc

    nome = getattr(contratante, "razao_social", None) or getattr(contratante, "nome", "")
    logger.info("Ficha gerada para %s (%d bytes)", nome, len(pdf))
    return _arquivo(pdf, f"ficha-cadastral-{_slug(nome)}.pdf", PDF)


@app.post("/v1/formulario", dependencies=[Protegido])
def formulario(pedido: PedidoFormulario) -> Response:
    contratante = pedido.contratante.para_dominio()
    empresa, endereco, socios = dados_de_contratante(contratante)

    desenq = pedido.desenquadramento.model_dump() if pedido.desenquadramento else None

    # Mesma regra da aba Streamlit (`_gerar_docx`): na abertura (PF) não há
    # razão social nem CNAE definidos — é tudo decisão do cliente, então o
    # bloco da empresa sai inteiro para preencher.
    if pedido.perfil == "PF":
        empresa = {}

    # MEI é empresário individual: exigir dois sócios geraria uma seção vazia
    # que o cliente não sabe o que fazer com.
    minimo_socios = 1 if pedido.perfil == "MEI" else 2

    try:
        docx = gerar_formulario_abertura(
            pedido.perfil, empresa, endereco, socios, desenq,
            minimo_socios=minimo_socios,
        )
    except ValueError as exc:
        raise HTTPException(422, f"Dados insuficientes: {exc}") from exc

    nome = getattr(contratante, "razao_social", None) or getattr(contratante, "nome", "")
    logger.info("Formulário %s gerado para %s (%d bytes)",
                pedido.perfil, nome, len(docx))
    return _arquivo(docx, f"formulario-{pedido.perfil.lower()}-{_slug(nome)}.docx", DOCX)


@app.post("/v1/transicao", dependencies=[Protegido])
def transicao(pedido: PedidoTransicao) -> Response:
    """Formulário de entrada de novo cliente — transição contábil.

    Substitui a planilha que a equipe preenchia à mão. O bloco cadastral vem da
    consulta de CNPJ; o operacional (departamento pessoal, contábil, fiscal e
    financeiro) vem da tela, porque nenhuma API o conhece.
    """
    iniciais = pedido.iniciais.para_dicionario()

    if pedido.contratante is not None:
        contratante = pedido.contratante.para_dominio()
        # O prefill entra POR BAIXO do que veio na requisição: se a equipe
        # corrigiu um dado na tela, a correção manda. O contrário faria a
        # consulta sobrescrever a conferência humana — que é o oposto do
        # objetivo do documento.
        iniciais = {**dados_de_contratante_transicao(contratante), **iniciais}
    else:
        contratante = None

    docx = gerar_formulario_transicao(
        dados_iniciais=iniciais,
        dados_pessoal=pedido.pessoal.para_dicionario(),
        dados_fiscal=pedido.fiscal.para_dicionario(),
        dados_sucessao=pedido.sucessao.para_dicionario(),
    )

    nome = (
        iniciais.get("razao_social")
        or (getattr(contratante, "razao_social", "") if contratante else "")
        or (getattr(contratante, "nome", "") if contratante else "")
        or "em-branco"
    )
    logger.info("Formulário de transição gerado para %s (%d bytes)",
                nome, len(docx))
    return _arquivo(docx, f"transicao-contabil-{_slug(nome)}.docx", DOCX)
