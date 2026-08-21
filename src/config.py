"""Configuração central da aplicação.

Tudo que é "número mágico" ou endpoint externo vive aqui, para que ajustes
de negócio (preços, limites, TTLs) não exijam caçar constantes espalhadas
pelos módulos de UI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("MERCABILIZA_DATA_DIR", BASE_DIR / "data"))
ASSETS_DIR = BASE_DIR / "assets"

# --------------------------------------------------------------------------- #
# Ambiente — tudo que muda entre local e produção                             #
# --------------------------------------------------------------------------- #
# Regra: NADA de segredo com valor padrão no código. Ausente = comportamento
# seguro (SQLite local, gate avisando) em vez de silenciosamente inseguro.

# Render e Railway injetam DATABASE_URL ao vincular o Postgres ao serviço.
# Vazia = usa SQLite local (efêmero em PaaS — ver DEPLOY.md).
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# "producao" liga travas extras: sem stack trace na tela, log mais enxuto.
AMBIENTE = os.getenv("MERCABILIZA_AMBIENTE", "local").strip().lower()
EH_PRODUCAO = AMBIENTE in {"producao", "production", "prod"}

LOG_LEVEL = os.getenv("MERCABILIZA_LOG_LEVEL", "WARNING" if EH_PRODUCAO
                      else "INFO").upper()


# --------------------------------------------------------------------------- #
# Infraestrutura                                                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HttpSettings:
    timeout: float = 8.0
    total_retries: int = 2
    backoff_factor: float = 0.6
    user_agent: str = "Mercabiliza-Onboarding/2.0 (+contato@mercabiliza.com.br)"
    # Nº de CNPJs consultados em paralelo no modo lote. Mantido baixo de
    # propósito: a ReceitaWS gratuita limita a ~3 req/min por IP.
    max_workers_lote: int = 4
    # Consultas simultâneas aos provedores de um MESMO CNPJ.
    max_workers_provedores: int = 3


@dataclass(frozen=True)
class CacheSettings:
    dossie_ttl: int = 60 * 60 * 12       # 12h — dado cadastral muda pouco
    bacen_ttl: int = 60 * 60 * 24        # 24h
    ibge_ttl: int = 60 * 60 * 24 * 30    # 30d — código IBGE é praticamente estático


@dataclass(frozen=True)
class LimitSettings:
    max_cnpjs_por_lote: int = 200
    max_historico_sessao: int = 25       # trava de memória p/ Streamlit Cloud


# --------------------------------------------------------------------------- #
# Endpoints externos                                                          #
# --------------------------------------------------------------------------- #
BRASIL_API_CNPJ = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
CNPJ_WS_PUBLICA = "https://publica.cnpj.ws/cnpj/{cnpj}"
RECEITA_WS = "https://receitaws.com.br/v1/cnpj/{cnpj}"
IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
BACEN_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/{n}?formato=json"

# Séries do SGS/BACEN.
#   4390 = Taxa Selic acumulada no mês (% a.m.) -> precisa ser COMPOSTA, não somada.
#   433  = IPCA, variação percentual mensal.
SGS_SELIC_MENSAL = 4390
SGS_IPCA_MENSAL = 433

# Fallbacks usados quando o BACEN está fora do ar.
SELIC_FALLBACK_AA = 10.50
IPCA_FALLBACK_AA = 4.00


# --------------------------------------------------------------------------- #
# Regras comerciais (Mercabiliza)                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TabelaPrecos:
    honorario_base: float = 350.0
    adicional_por_cnpj: float = 50.0
    adicional_por_bloco_dp: float = 50.0
    pessoas_por_bloco_dp: int = 3
    desenquadramento_mei: float = 350.0
    abertura_empresa: float = 1600.0
    validade_proposta_dias: int = 15


@dataclass(frozen=True)
class DadosEmissor:
    nome: str = "Luis Felipe"
    cargo: str = "Sócio - Mercabiliza Contabilidade"
    telefone: str = "+55 19 99285-3550"
    email: str = "luisfelipe@contabilidadeclassea.com.br"
    cor_marca: tuple[int, int, int] = (220, 50, 80)


# --------------------------------------------------------------------------- #
# Dados da CONTRATADA — usados na qualificação das partes do contrato          #
# --------------------------------------------------------------------------- #
# Preenchidos a partir do Comprovante de Inscrição (CNPJ 62.350.925/0001-10).
#
# Estes campos alimentam o cabeçalho/rodapé dos documentos e a ficha cadastral.
# A qualificação da CONTRATADA **no contrato** NÃO usa este bloco: ela é o texto
# fixo de duas empresas em CONTRATADA_QUALIFICACAO_FIXA (mais abaixo), sem CRC e
# sem nomear pessoa física, por decisão de negócio. CONTRATADA_CRC e os campos
# CONTRATADA_REP_* seguem opcionais por isso.
CONTRATADA_RAZAO_SOCIAL = "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA"
CONTRATADA_NOME_FANTASIA = "Mercabiliza"
CONTRATADA_CNPJ = "62350925000110"
CONTRATADA_CRC = ""                      # ← PREENCHER
CONTRATADA_TELEFONE = "(19) 3327-0038"
CONTRATADA_EMAIL = "contato@contabilidadeclassea.com.br"
CONTRATADA_SITE = ""
CONTRATADA_LOGRADOURO = "RUA ANCHIETA"
CONTRATADA_NUMERO = "204"
CONTRATADA_COMPLEMENTO = ""
CONTRATADA_BAIRRO = "VILA BOAVENTURA"
CONTRATADA_MUNICIPIO = "Jundiaí"
CONTRATADA_UF = "SP"
CONTRATADA_CEP = "13201804"

# Representante legal que assina pela Mercabiliza.
CONTRATADA_REP_NOME = "Luis Felipe"
CONTRATADA_REP_CPF = ""                  # ← PREENCHER
CONTRATADA_REP_RG = ""                   # ← PREENCHER
CONTRATADA_REP_ORGAO = ""                # ← PREENCHER
CONTRATADA_REP_ESTADO_CIVIL = ""         # ← PREENCHER
CONTRATADA_REP_PROFISSAO = "contador"
CONTRATADA_REP_QUALIFICACAO = "sócio administrador"

# --------------------------------------------------------------------------- #
# CONTRATADA — texto fixo da qualificação (duas empresas do grupo)             #
# --------------------------------------------------------------------------- #
# Reproduz LITERALMENTE o bloco do contrato modelo da Mercabiliza, sem CRC e
# sem nomear pessoa física, conforme definido pela diretoria.
#
# ⚠️ REVISAR: o modelo diz "JUNDIAI/PR". Jundiaí é município de SÃO PAULO —
#    o cartão CNPJ da própria empresa (62.350.925/0001-10) traz JUNDIAI/SP.
#    Mantido como está para não divergir do contrato em uso, mas isso se
#    repete em todo contrato assinado. Trocar "PR" por "SP" nas duas linhas
#    abaixo resolve em definitivo.
CONTRATADA_UF_REVISAR = "PR"   # ← trocar para "SP" após confirmar com o jurídico

CONTRATADA_QUALIFICACAO_FIXA = f"""Nossos serviços serão prestados por:

**MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA.** (CNPJ: 62.350.925/0001-10), **R ANCHIETA, 204, SALA 102, BAIRRO: VILA BOAVENTURA, JUNDIAI/{CONTRATADA_UF_REVISAR}.**

**MERCABILIZA SOLUCOES EM TECNOLOGIA E GESTAO LTDA.** (CNPJ: 62.291.063/0001-00), com sede na **R ANCHIETA, 214, SALA 107, BAIRRO: VILA BOAVENTURA, JUNDIAI/{CONTRATADA_UF_REVISAR}.**"""

# Assinatura do contrato: apenas a razão social e o CNPJ da entidade contábil.
CONTRATADA_ASSINATURA_NOME = "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA"
CONTRATADA_ASSINATURA_CNPJ = "62.350.925/0001-10"

# Nota de rodapé do contrato modelo.
# ⚠️ REVISAR: o modelo cita "Lei 10.402/2002". O Código Civil é a Lei
#    nº 10.406/2002 — 10.402 não corresponde a essa norma.
CONTRATO_NOTA_RODAPE = (
    "(Documento produzido em consonância com o art. 107 da Lei 10.406/2002 e "
    "art. 441 da Lei 13.105/2015)"
)

# Foro padrão sugerido na aba de contratos (comarca da sede).
FORO_PADRAO = "Campinas/SP"   # o contrato modelo elege Campinas


@dataclass(frozen=True)
class Settings:
    http: HttpSettings = field(default_factory=HttpSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    limites: LimitSettings = field(default_factory=LimitSettings)
    precos: TabelaPrecos = field(default_factory=TabelaPrecos)
    emissor: DadosEmissor = field(default_factory=DadosEmissor)
    db_path: Path = field(default_factory=lambda: DATA_DIR / "leads_contabeis.db")


settings = Settings()
