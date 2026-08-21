"""Modelos de domínio.

O código original transitava um ``dict`` de ~30 chaves entre APIs, exporters e
UI. Qualquer erro de digitação em uma chave só aparecia em runtime, dentro de
um `KeyError` no meio da geração do PDF. Dataclasses dão autocomplete,
checagem estática e defaults seguros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class DiagnosticoCNAE:
    anexo: str
    aliquota_inicial: str
    tem_fator_r: bool
    is_minimercado: bool
    resumo: str
    dica_engenharia: str


@dataclass(frozen=True, slots=True)
class AtividadeCNAE:
    codigo: str
    descricao: str
    diagnostico: DiagnosticoCNAE

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.codigo} - {self.descricao}"


@dataclass(frozen=True, slots=True)
class Socio:
    nome: str
    qualificacao: str
    faixa_etaria: str = "N/A"


@dataclass(frozen=True, slots=True)
class Endereco:
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    cep: str = ""
    cod_ibge: str = "N/A"
    regiao: str = "Brasil"
    # Acrescentado no fim de propósito: manter a ordem posicional dos campos
    # existentes intacta para não quebrar chamadas já escritas.
    complemento: str = ""

    @property
    def logradouro_numero(self) -> str:
        base = f"{self.logradouro}, {self.numero}".strip(", ")
        return f"{base}, {self.complemento}" if self.complemento else base

    @property
    def linha_completa(self) -> str:
        partes = [
            p for p in (
                self.logradouro_numero,
                self.bairro,
                f"{self.municipio}/{self.uf}".strip("/"),
            ) if p
        ]
        base = " - ".join(partes)
        return f"{base} - CEP: {self.cep}" if self.cep else base

    @property
    def cep_formatado(self) -> str:
        digitos = "".join(c for c in self.cep if c.isdigit())
        return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else self.cep

    @property
    def linha_juridica(self) -> str:
        """Endereço no padrão de qualificação contratual."""
        partes = [p for p in (self.logradouro_numero, self.bairro) if p]
        base = ", ".join(partes)
        cidade = f"{self.municipio}/{self.uf}".strip("/")
        if cidade:
            base = f"{base}, {cidade}" if base else cidade
        return f"{base}, CEP {self.cep_formatado}" if self.cep else base

    @property
    def linha_juridica_negrito(self) -> str:
        """Endereço com logradouro/bairro e CEP em negrito.

        Segue o contrato modelo: o logradouro com número e bairro sai
        destacado, o município fica em texto normal, e o CEP volta a negrito.
        Marcadores ``**`` — o gerador de PDF converte para ``<b>``.
        """
        partes = []
        cabeca = ", ".join(p for p in (self.logradouro_numero, self.bairro) if p)
        if cabeca:
            partes.append(f"**{cabeca}**")
        cidade = f"{self.municipio}/{self.uf}".strip("/")
        if cidade:
            partes.append(cidade)
        base = ", ".join(partes)
        if self.cep:
            return f"{base}, **CEP {self.cep_formatado}**" if base \
                else f"**CEP {self.cep_formatado}**"
        return base

    @property
    def esta_preenchido(self) -> bool:
        return bool(self.logradouro and self.municipio and self.uf)


@dataclass(frozen=True, slots=True)
class SituacaoCadastral:
    """Somente o que é efetivamente verificável em base pública.

    ATENÇÃO: a versão anterior devolvia "🟢 Regularidade FGTS" e
    "🟢 CNDT sem pendências" como texto fixo, sem consultar nada. Isso é uma
    afirmação de regularidade não verificada em um documento entregue ao
    cliente. Aqui os campos não consultados são explicitamente marcados como
    NÃO VERIFICADOS.
    """

    situacao_receita: str = "DESCONHECIDA"
    data_situacao: str = ""

    @property
    def esta_ativa(self) -> bool:
        return self.situacao_receita.strip().upper() == "ATIVA"

    @property
    def rotulo_receita(self) -> str:
        icone = "🟢" if self.esta_ativa else "🔴"
        return f"{icone} {self.situacao_receita} na Receita Federal"

    @property
    def pendentes_de_verificacao(self) -> tuple[str, ...]:
        return (
            "CND Federal (RFB/PGFN) — exige emissão no e-CAC",
            "CRF/FGTS — exige consulta na Caixa",
            "CNDT — exige consulta no TST",
            "Certidões estaduais e municipais",
        )


@dataclass(slots=True)
class Empresa:
    cnpj: str
    razao_social: str = ""
    nome_fantasia: str = ""
    matriz_filial: str = "MATRIZ"
    data_abertura: str = ""
    natureza_juridica: str = ""
    porte: str = ""
    capital_social: float = 0.0
    emails: tuple[str, ...] = ()
    telefones: tuple[str, ...] = ()
    optante_simples: bool = False
    optante_mei: bool = False
    endereco: Endereco = field(default_factory=Endereco)
    situacao: SituacaoCadastral = field(default_factory=SituacaoCadastral)
    atividade_principal: AtividadeCNAE | None = None
    atividades_secundarias: tuple[AtividadeCNAE, ...] = ()
    inscricoes_estaduais: tuple[str, ...] = ()
    inscricao_municipal: str = "Não identificada em busca pública"
    socios: tuple[Socio, ...] = ()
    fontes: tuple[str, ...] = ()
    consultado_em: date = field(default_factory=date.today)

    # ---------------------------------------------------------------- #
    @property
    def regime(self) -> str:
        if self.optante_mei:
            return "MEI"
        if self.optante_simples:
            return "Simples Nacional"
        return "Lucro Presumido / Real"

    @property
    def email_str(self) -> str:
        return ", ".join(self.emails) if self.emails else "Não informado"

    @property
    def telefone_str(self) -> str:
        return ", ".join(self.telefones) if self.telefones else "Não informado"

    @property
    def telefone_principal(self) -> str:
        """Primeiro telefone da lista.

        Bug corrigido: o código anterior concatenava TODOS os telefones,
        removia os não-dígitos e cortava os 11 primeiros — produzindo um
        número inexistente sempre que a empresa tinha mais de uma linha.
        """
        return self.telefones[0] if self.telefones else ""

    @property
    def tem_risco_societario(self) -> bool:
        return len(self.socios) > 1

    @property
    def cnae_principal_str(self) -> str:
        return str(self.atividade_principal) if self.atividade_principal else "Não informado"

    def to_row(self) -> dict[str, Any]:
        """Linha achatada para DataFrame / persistência."""
        return {
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "nome_fantasia": self.nome_fantasia,
            "situacao": self.situacao.situacao_receita,
            "regime": self.regime,
            "porte": self.porte,
            "email": self.email_str,
            "telefone": self.telefone_str,
            "municipio": self.endereco.municipio,
            "uf": self.endereco.uf,
            "cnae_principal": self.cnae_principal_str,
            "anexo": self.atividade_principal.diagnostico.anexo
            if self.atividade_principal else "",
            "capital_social": self.capital_social,
            "consultado_em": self.consultado_em.isoformat(),
        }
