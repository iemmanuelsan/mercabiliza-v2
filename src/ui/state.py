"""Camada de integração com o Streamlit: cache, estado e recursos singleton.

É o ÚNICO módulo do projeto que conhece o Streamlit além de ``ui/``. O núcleo
(``core/``) e os serviços (``services/``) são Python puro — testáveis com
pytest, reaproveitáveis numa API FastAPI ou num job de linha de comando.
"""

from __future__ import annotations

import logging

import streamlit as st

from ..config import settings
from ..core.models import Empresa
from ..services.cnpj_providers import consultar_cnpj as _consultar_cnpj
from ..services.indicadores import Indicadores
from ..services.indicadores import obter_indicadores as _obter_indicadores
from ..services.repository import LeadRepository, criar_repositorio

logger = logging.getLogger(__name__)

CHAVE_HISTORICO = "historico"
CHAVE_LOTE = "lote_processado"
CHAVE_RBT12 = "rbt12_referencia"


# --------------------------------------------------------------------------- #
# Recursos singleton                                                          #
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def obter_repositorio() -> LeadRepository:
    """[CORRIGIDO] ``init_db()`` era chamado no topo do módulo, executando um
    CREATE TABLE a cada rerun do Streamlit — ou seja, a cada tecla digitada.
    ``cache_resource`` garante exatamente uma inicialização por processo."""
    return criar_repositorio()


# --------------------------------------------------------------------------- #
# Consultas cacheadas                                                         #
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=settings.cache.bacen_ttl, show_spinner=False)
def indicadores_bacen() -> Indicadores:
    return _obter_indicadores()


@st.cache_data(ttl=settings.cache.ibge_ttl, show_spinner="Consultando CEP…",
               max_entries=512)
def consultar_cep_cached(cep: str):
    """CEP é praticamente imutável — cache longo evita bater no ViaCEP à toa."""
    from ..services.cep import consultar_cep
    return consultar_cep(cep)


@st.cache_data(ttl=settings.cache.dossie_ttl, show_spinner=False, max_entries=256)
def consultar_dossie(cnpj: str, rbt12: float = 0.0) -> Empresa | None:
    """[OTIMIZADO] A consulta completa não era cacheada. Reprocessar o mesmo
    lote, ou reconsultar um CNPJ recém-pesquisado, disparava as 3 chamadas de
    rede de novo — desperdício e risco de rate limit (a ReceitaWS gratuita
    permite ~3 req/min)."""
    return _consultar_cnpj(cnpj, rbt12)


# --------------------------------------------------------------------------- #
# Geração de artefatos — cacheada por conteúdo                                #
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False, max_entries=32)
def excel_bytes(chave: str, _empresas: tuple[Empresa, ...]) -> bytes:
    """Gera o Excel apenas quando a lista muda de fato.

    [CORRIGIDO — maior gargalo do app] No original, ``gerar_excel_dossie_4abas``
    e os dois ``gerar_pdf_*`` eram chamados no corpo da aba, fora de qualquer
    callback. Como o Streamlit reexecuta o script inteiro a cada interação,
    mexer no slider de "% monofásico" da aba 2 reconstruía uma pasta de
    trabalho de 4 abas e dois PDFs — para todas as empresas do lote.

    O ``_`` no nome do parâmetro diz ao Streamlit para não tentar hashear os
    objetos ``Empresa``; ``chave`` é o identificador estável do conteúdo.
    """
    from ..exporters.excel import gerar_dossie_excel
    return gerar_dossie_excel(list(_empresas))


@st.cache_data(show_spinner=False, max_entries=32)
def pdf_dossie_bytes(chave: str, _empresa: Empresa) -> bytes:
    from ..exporters.pdf_dossie import gerar_dossie
    return gerar_dossie(_empresa)


@st.cache_data(show_spinner=False, max_entries=32)
def pdf_cartao_bytes(chave: str, _empresa: Empresa) -> bytes:
    from ..exporters.pdf_dossie import gerar_cartao_cnpj
    return gerar_cartao_cnpj(_empresa)


# --------------------------------------------------------------------------- #
# Estado de sessão                                                            #
# --------------------------------------------------------------------------- #
def inicializar_estado() -> None:
    st.session_state.setdefault(CHAVE_HISTORICO, [])
    st.session_state.setdefault(CHAVE_LOTE, [])
    st.session_state.setdefault(CHAVE_RBT12, 0.0)


def registrar_no_historico(empresa: Empresa) -> None:
    """Insere no topo, deduplica e aplica teto de memória.

    [CORRIGIDO] O histórico crescia indefinidamente na sessão e era exportado
    inteiro num arquivo nomeado com o CNPJ de uma única empresa."""
    historico = [e for e in st.session_state[CHAVE_HISTORICO] if e.cnpj != empresa.cnpj]
    historico.insert(0, empresa)
    st.session_state[CHAVE_HISTORICO] = historico[: settings.limites.max_historico_sessao]
