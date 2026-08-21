"""Partes contratuais: pessoa física, pessoa jurídica e representante legal.

A responsabilidade central deste módulo é produzir a **qualificação das
partes** — o parágrafo de abertura do contrato que identifica juridicamente
contratante e contratada. Como é texto que vai para documento assinado, ele
é gerado aqui (Python puro, testável) e não montado com f-strings espalhadas
pela camada de UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .cnpj import formatar as formatar_cnpj
from .cpf import formatar as formatar_cpf
from .models import Empresa, Endereco

ESTADOS_CIVIS: tuple[str, ...] = (
    "solteiro(a)",
    "casado(a)",
    "divorciado(a)",
    "viúvo(a)",
    "separado(a) judicialmente",
    "união estável",
)

QUALIFICACOES_SIGNATARIO: tuple[str, ...] = (
    "sócio(a) administrador(a)",
    "administrador(a)",
    "titular",
    "procurador(a)",
    "diretor(a)",
)


def _denominacao(genero_feminino: bool) -> str:
    """'denominada' ou 'denominado', conforme o gênero informado na ficha."""
    return "denominada" if genero_feminino else "denominado"


def _flexao(genero_feminino: bool) -> dict[str, str]:
    """Concordância de gênero nos termos fixos da qualificação.

    Sem isso o contrato sai com "brasileira, casada, portador(a) da cédula",
    misturando a flexão que o usuário digitou com a forma neutra do template.
    Em documento assinado isso passa impressão de descuido.
    """
    if genero_feminino:
        return {
            "portador": "portadora",
            "inscrito": "inscrita",
            "residente": "residente e domiciliada",
        }
    return {
        "portador": "portador",
        "inscrito": "inscrito",
        "residente": "residente e domiciliado",
    }


# Termos de texto livre que aparecem no padrão masculino nos defaults e nas
# listas de opções. Só estes são flexionados automaticamente — o resto o
# usuário digita já no gênero correto.
_FLEXOES_LIVRES: dict[str, str] = {
    "brasileiro": "brasileira",
    "sócio": "sócia",
    "sócio administrador": "sócia administradora",
    "administrador": "administradora",
    "titular": "titular",
    "procurador": "procuradora",
    "diretor": "diretora",
    "contador": "contadora",
    "empresário": "empresária",
    "comerciante": "comerciante",
    "solteiro": "solteira",
    "casado": "casada",
    "divorciado": "divorciada",
    "viúvo": "viúva",
}


def n(valor: object) -> str:
    """Envolve o valor em ``**`` para sair em NEGRITO no documento.

    Segue o padrão do contrato em uso da Mercabiliza: o dado que **identifica
    a parte** — razão social, CNPJ, documentos, endereço, CEP — vem destacado,
    enquanto a prosa jurídica que liga esses dados fica em texto normal. Isso
    faz o conferente achar os campos críticos de relance, que é justamente o
    momento em que erro de digitação precisa ser pego.

    O marcador ``**`` é entendido tanto pelo gerador de PDF (vira ``<b>``)
    quanto pelo ``st.markdown`` do preview — a tela mostra o mesmo que o papel.
    Valor vazio não recebe marcador, para não gerar ``****`` solto.
    """
    texto = str(valor or "").strip()
    return f"**{texto}**" if texto else ""


def _flexionar_livre(termo: str, genero_feminino: bool) -> str:
    """Flexiona termos conhecidos; devolve intacto o que não reconhece.

    Deliberadamente conservador: errar a flexão de uma palavra que o usuário
    digitou é pior que deixá-la como está. Só mexe no que está na tabela.
    """
    if not genero_feminino or not termo:
        return termo
    return _FLEXOES_LIVRES.get(termo.strip().casefold(), termo)


# --------------------------------------------------------------------------- #
# Representante legal (quem assina pela pessoa jurídica)                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RepresentanteLegal:
    nome: str = ""
    cpf: str = ""
    rg: str = ""
    orgao_emissor: str = ""
    nacionalidade: str = "brasileiro"
    estado_civil: str = ""
    profissao: str = ""
    qualificacao: str = "sócio administrador"
    genero_feminino: bool = False

    @property
    def esta_preenchido(self) -> bool:
        return bool(self.nome and self.cpf)

    @property
    def documento_str(self) -> str:
        flex = _flexao(self.genero_feminino)
        if self.rg and self.orgao_emissor:
            return (f"{flex['portador']} da cédula de identidade RG nº "
                    f"{n(self.rg)} expedida pelo {n(self.orgao_emissor)}")
        if self.rg:
            return (f"{flex['portador']} da cédula de identidade RG nº "
                    f"{n(self.rg)}")
        return ""

    @property
    def qualificacao_texto(self) -> str:
        """Ex.: 'MARIA DA SILVA, brasileira, casada, contadora, portadora da
        cédula de identidade RG nº 12.345.678 expedida pela SSP/SP, inscrita no
        CPF sob o nº 529.982.247-25, na qualidade de sócia administradora'."""
        flex = _flexao(self.genero_feminino)
        partes = [n(self.nome.strip().upper()) or "(REPRESENTANTE NÃO INFORMADO)"]
        for item in (_flexionar_livre(self.nacionalidade, self.genero_feminino),
                     _flexionar_livre(self.estado_civil, self.genero_feminino),
                     _flexionar_livre(self.profissao, self.genero_feminino)):
            if item:
                partes.append(item)
        if doc := self.documento_str:
            partes.append(doc)
        if self.cpf:
            partes.append(f"{flex['inscrito']} no CPF sob o nº "
                          f"{n(formatar_cpf(self.cpf))}")
        else:
            partes.append(f"{flex['inscrito']} no CPF sob o nº ______________")
        if self.qualificacao:
            partes.append("na qualidade de "
                          f"{_flexionar_livre(self.qualificacao, self.genero_feminino)}")
        return ", ".join(partes)


# --------------------------------------------------------------------------- #
# Contratantes                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ContratantePF:
    """Cliente pessoa física."""

    nome: str = ""
    cpf: str = ""
    rg: str = ""
    orgao_emissor: str = ""
    nacionalidade: str = "brasileiro"
    estado_civil: str = ""
    profissao: str = ""
    endereco: Endereco = field(default_factory=Endereco)
    telefone: str = ""
    email: str = ""
    genero_feminino: bool = False

    tipo: str = "PF"

    # ------------------------------------------------------------------ #
    @property
    def nome_exibicao(self) -> str:
        return self.nome.strip() or "(nome não informado)"

    @property
    def documento_principal(self) -> str:
        return formatar_cpf(self.cpf) if self.cpf else "(não informado)"

    @property
    def rotulo_documento(self) -> str:
        return "CPF"

    @property
    def pendencias(self) -> tuple[str, ...]:
        faltando = []
        if not self.nome.strip():
            faltando.append("nome completo")
        if not self.cpf:
            faltando.append("CPF")
        if not self.endereco.esta_preenchido:
            faltando.append("endereço (logradouro, município e UF)")
        if not self.estado_civil:
            faltando.append("estado civil")
        if not self.profissao:
            faltando.append("profissão")
        return tuple(faltando)

    @property
    def qualificacao_contratual(self) -> str:
        flex = _flexao(self.genero_feminino)
        partes = [n(self.nome.strip().upper()) or "(NOME NÃO INFORMADO)"]
        for item in (_flexionar_livre(self.nacionalidade, self.genero_feminino),
                     _flexionar_livre(self.estado_civil, self.genero_feminino),
                     _flexionar_livre(self.profissao, self.genero_feminino)):
            if item:
                partes.append(item)
        if self.rg and self.orgao_emissor:
            partes.append(f"{flex['portador']} da cédula de identidade RG nº "
                          f"{n(self.rg)} expedida pelo {n(self.orgao_emissor)}")
        elif self.rg:
            partes.append(f"{flex['portador']} da cédula de identidade RG nº "
                          f"{n(self.rg)}")
        if self.cpf:
            partes.append(f"{flex['inscrito']} no CPF sob o nº "
                          f"{n(formatar_cpf(self.cpf))}")
        if self.endereco.esta_preenchido:
            partes.append(f"{flex['residente']} na "
                          f"{self.endereco.linha_juridica_negrito}")
        partes.append(
            f"doravante {_denominacao(self.genero_feminino)} simplesmente CONTRATANTE")
        return ", ".join(partes)

    def linhas_ficha(self) -> list[tuple[str, str]]:
        return [
            ("Nome completo", self.nome_exibicao),
            ("CPF", self.documento_principal),
            ("RG / Órgão emissor",
             " / ".join(p for p in (self.rg, self.orgao_emissor) if p) or "—"),
            ("Nacionalidade", self.nacionalidade or "—"),
            ("Estado civil", self.estado_civil or "—"),
            ("Profissão", self.profissao or "—"),
            ("Endereço", self.endereco.logradouro_numero or "—"),
            ("Bairro", self.endereco.bairro or "—"),
            ("Município / UF",
             f"{self.endereco.municipio}/{self.endereco.uf}".strip("/") or "—"),
            ("CEP", self.endereco.cep_formatado or "—"),
            ("Telefone / WhatsApp", self.telefone or "—"),
            ("E-mail", self.email or "—"),
        ]


@dataclass(frozen=True, slots=True)
class ContratantePJ:
    """Cliente pessoa jurídica, normalmente preenchido pela consulta de CNPJ."""

    razao_social: str = ""
    nome_fantasia: str = ""
    cnpj: str = ""
    cnae_principal: str = ""
    endereco: Endereco = field(default_factory=Endereco)
    telefone: str = ""
    email: str = ""
    inscricao_estadual: str = ""
    inscricao_municipal: str = ""
    representante: RepresentanteLegal = field(default_factory=RepresentanteLegal)
    regime: str = ""
    data_abertura: str = ""
    natureza_juridica: str = ""

    tipo: str = "PJ"

    # ------------------------------------------------------------------ #
    @property
    def nome_exibicao(self) -> str:
        return self.razao_social.strip() or "(razão social não informada)"

    @property
    def documento_principal(self) -> str:
        return formatar_cnpj(self.cnpj) if self.cnpj else "(não informado)"

    @property
    def rotulo_documento(self) -> str:
        return "CNPJ"

    @property
    def pendencias(self) -> tuple[str, ...]:
        faltando = []
        if not self.razao_social.strip():
            faltando.append("razão social")
        if not self.cnpj:
            faltando.append("CNPJ")
        if not self.endereco.esta_preenchido:
            faltando.append("endereço da sede")
        if not self.representante.esta_preenchido:
            faltando.append("representante legal (nome e CPF)")
        if not self.email:
            faltando.append("e-mail financeiro")
        return tuple(faltando)

    @property
    def eh_empresario_individual(self) -> bool:
        """MEI, EI e EIRELI não são 'pessoa jurídica de direito privado'.

        Empresário individual é firma em nome da própria pessoa natural — a
        razão social **é** o nome dela. Tratar como sociedade na qualificação
        é impreciso e desnecessário: dá para acertar lendo a natureza jurídica
        ou o regime tributário.
        """
        alvo = f"{self.natureza_juridica} {self.regime}".lower()
        return any(t in alvo for t in ("individual", "mei", "eireli", "empresário"))

    @property
    def qualificacao_contratual(self) -> str:
        eh_ei = self.eh_empresario_individual
        partes = [
            n(self.razao_social.strip().upper()) or "(RAZÃO SOCIAL NÃO INFORMADA)",
            "empresário individual" if eh_ei else "pessoa jurídica de direito privado",
        ]
        flexao = "inscrito" if eh_ei else "inscrita"
        if self.cnpj:
            partes.append(f"{flexao} no CNPJ sob o nº "
                          f"{n(formatar_cnpj(self.cnpj))}")
        if self.inscricao_estadual:
            partes.append(f"inscrição estadual nº {n(self.inscricao_estadual)}")
        if self.endereco.esta_preenchido:
            sede = "com estabelecimento na" if eh_ei else "com sede na"
            partes.append(f"{sede} {self.endereco.linha_juridica_negrito}")
        if self.representante.esta_preenchido:
            # Para EI, quem assina é o próprio titular — não faz sentido dizer
            # "neste ato representada por" se for a mesma pessoa.
            mesmo_titular = (
                self.representante.nome.strip().casefold()
                == self.razao_social.strip().casefold()
            )
            if eh_ei and mesmo_titular:
                partes.append(f"neste ato assinando na qualidade de "
                              f"{self.representante.qualificacao}")
                if self.representante.cpf:
                    partes.append("inscrito no CPF sob o nº "
                                  f"{n(formatar_cpf(self.representante.cpf))}")
            else:
                verbo = "representado por" if eh_ei else "representada por"
                partes.append(f"neste ato {verbo} "
                              f"{self.representante.qualificacao_texto}")
        denominado = "denominado" if eh_ei else "denominada"
        partes.append(f"doravante {denominado} simplesmente CONTRATANTE")
        return ", ".join(partes)

    def linhas_ficha(self) -> list[tuple[str, str]]:
        return [
            ("Razão social", self.nome_exibicao),
            ("Nome fantasia", self.nome_fantasia or "—"),
            ("CNPJ", self.documento_principal),
            ("Data de abertura", self.data_abertura or "—"),
            ("CNAE principal", self.cnae_principal or "—"),
            ("Regime tributário", self.regime or "—"),
            ("Inscrição estadual", self.inscricao_estadual or "Isento / não informado"),
            ("Inscrição municipal", self.inscricao_municipal or "—"),
            ("Endereço", self.endereco.logradouro_numero or "—"),
            ("Bairro", self.endereco.bairro or "—"),
            ("Município / UF",
             f"{self.endereco.municipio}/{self.endereco.uf}".strip("/") or "—"),
            ("CEP", self.endereco.cep_formatado or "—"),
            ("Telefone comercial", self.telefone or "—"),
            ("E-mail financeiro", self.email or "—"),
        ]

    def linhas_representante(self) -> list[tuple[str, str]]:
        r = self.representante
        return [
            ("Nome", r.nome or "—"),
            ("CPF", formatar_cpf(r.cpf) if r.cpf else "—"),
            ("RG / Órgão emissor",
             " / ".join(p for p in (r.rg, r.orgao_emissor) if p) or "—"),
            ("Estado civil", r.estado_civil or "—"),
            ("Profissão", r.profissao or "—"),
            ("Qualificação", r.qualificacao or "—"),
        ]


Contratante = ContratantePF | ContratantePJ


# --------------------------------------------------------------------------- #
# Ponte com o módulo de dossiê                                                 #
# --------------------------------------------------------------------------- #
def de_empresa(empresa: Empresa, socio_escolhido: str | None = None) -> ContratantePJ:
    """Converte o resultado da consulta de CNPJ em contratante PJ.

    É o ponto que faz o módulo de contratos valer a pena: os dados cadastrais
    já levantados no dossiê alimentam o contrato sem redigitação. O QSA vira a
    lista de candidatos a signatário — ``socio_escolhido`` seleciona um deles
    pelo nome.
    """
    representante = RepresentanteLegal()
    if socio_escolhido:
        for socio in empresa.socios:
            if socio.nome == socio_escolhido:
                representante = RepresentanteLegal(
                    nome=socio.nome,
                    qualificacao=(socio.qualificacao or "sócio(a) administrador(a)"),
                )
                break
        else:
            # Nome digitado manualmente (procurador que não consta do QSA).
            representante = RepresentanteLegal(
                nome=socio_escolhido, qualificacao="procurador(a)")

    return ContratantePJ(
        razao_social=empresa.razao_social,
        nome_fantasia=empresa.nome_fantasia,
        cnpj=empresa.cnpj,
        cnae_principal=empresa.cnae_principal_str,
        endereco=replace(empresa.endereco),
        telefone=empresa.telefone_principal,
        email=empresa.emails[0] if empresa.emails else "",
        inscricao_estadual=(empresa.inscricoes_estaduais[0]
                            if empresa.inscricoes_estaduais else ""),
        inscricao_municipal=(
            empresa.inscricao_municipal
            if "não identificada" not in empresa.inscricao_municipal.lower() else ""
        ),
        representante=representante,
        regime=empresa.regime,
        data_abertura=empresa.data_abertura,
        natureza_juridica=empresa.natureza_juridica,
    )


# --------------------------------------------------------------------------- #
# Contratada (a Mercabiliza)                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Contratada:
    """Dados da Mercabiliza como prestadora dos serviços.

    Os valores vêm de ``src/config.py`` (ver :func:`contratada_padrao`). Campos
    que não constam do cartão CNPJ — CRC e qualificação civil do signatário —
    ficam em branco de propósito: um contrato com dado inventado é pior que um
    com campo visivelmente vazio, porque o erro passa na revisão.
    """

    razao_social: str = ""
    nome_fantasia: str = "Mercabiliza"
    cnpj: str = ""
    crc: str = ""
    endereco: Endereco = field(default_factory=Endereco)
    telefone: str = ""
    email: str = ""
    site: str = ""
    representante: RepresentanteLegal = field(default_factory=RepresentanteLegal)

    @property
    def esta_configurada(self) -> bool:
        """Mínimo para emitir: identificação da pessoa jurídica e signatário."""
        return bool(
            self.razao_social and self.cnpj
            and self.endereco.esta_preenchido
            and self.representante.esta_preenchido
        )

    @property
    def pendencias(self) -> tuple[str, ...]:
        faltando = []
        if not self.razao_social:
            faltando.append("razão social da contratada")
        if not self.cnpj:
            faltando.append("CNPJ da contratada")
        if not self.endereco.esta_preenchido:
            faltando.append("endereço da sede da contratada")
        if not self.representante.nome:
            faltando.append("nome do representante que assina pela contratada")
        if not self.representante.cpf:
            faltando.append("CPF do representante da contratada (config.py)")
        if not self.crc:
            faltando.append("registro no CRC da contratada (config.py)")
        return tuple(faltando)

    @property
    def qualificacao_contratual(self) -> str:
        partes = [
            self.razao_social.strip().upper() or "(RAZÃO SOCIAL NÃO CONFIGURADA)",
            "pessoa jurídica de direito privado",
        ]
        if self.cnpj:
            partes.append(f"inscrita no CNPJ sob o nº "
                          f"{n(formatar_cnpj(self.cnpj))}")
        partes.append(
            f"registrada no CRC sob o nº {n(self.crc)}" if self.crc
            else "registrada no CRC sob o nº ______________"
        )
        if self.endereco.esta_preenchido:
            partes.append(f"com sede na {self.endereco.linha_juridica_negrito}")
        if self.representante.nome:
            partes.append("neste ato representada por "
                          f"{self.representante.qualificacao_texto}")
        partes.append("doravante denominada simplesmente CONTRATADA")
        return ", ".join(partes)


def contratada_padrao() -> Contratada:
    """Monta a :class:`Contratada` a partir das constantes de ``config.py``."""
    from ..config import (
        CONTRATADA_BAIRRO,
        CONTRATADA_CEP,
        CONTRATADA_CNPJ,
        CONTRATADA_COMPLEMENTO,
        CONTRATADA_CRC,
        CONTRATADA_EMAIL,
        CONTRATADA_LOGRADOURO,
        CONTRATADA_MUNICIPIO,
        CONTRATADA_NOME_FANTASIA,
        CONTRATADA_NUMERO,
        CONTRATADA_RAZAO_SOCIAL,
        CONTRATADA_REP_CPF,
        CONTRATADA_REP_ESTADO_CIVIL,
        CONTRATADA_REP_NOME,
        CONTRATADA_REP_ORGAO,
        CONTRATADA_REP_PROFISSAO,
        CONTRATADA_REP_QUALIFICACAO,
        CONTRATADA_REP_RG,
        CONTRATADA_SITE,
        CONTRATADA_TELEFONE,
        CONTRATADA_UF,
    )

    return Contratada(
        razao_social=CONTRATADA_RAZAO_SOCIAL,
        nome_fantasia=CONTRATADA_NOME_FANTASIA,
        cnpj=CONTRATADA_CNPJ,
        crc=CONTRATADA_CRC,
        endereco=Endereco(
            logradouro=CONTRATADA_LOGRADOURO,
            numero=CONTRATADA_NUMERO,
            complemento=CONTRATADA_COMPLEMENTO,
            bairro=CONTRATADA_BAIRRO,
            municipio=CONTRATADA_MUNICIPIO,
            uf=CONTRATADA_UF,
            cep=CONTRATADA_CEP,
        ),
        telefone=CONTRATADA_TELEFONE,
        email=CONTRATADA_EMAIL,
        site=CONTRATADA_SITE,
        representante=RepresentanteLegal(
            nome=CONTRATADA_REP_NOME,
            cpf=CONTRATADA_REP_CPF,
            rg=CONTRATADA_REP_RG,
            orgao_emissor=CONTRATADA_REP_ORGAO,
            estado_civil=CONTRATADA_REP_ESTADO_CIVIL,
            profissao=CONTRATADA_REP_PROFISSAO,
            qualificacao=CONTRATADA_REP_QUALIFICACAO,
        ),
    )
