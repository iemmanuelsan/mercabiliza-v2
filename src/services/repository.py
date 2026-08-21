"""Persistência do CRM de leads (SQLite).

⚠️ AVISO DE DEPLOY: no Streamlit Community Cloud o sistema de arquivos é
**efêmero**. O banco é apagado a cada reboot ou redeploy do app. Para uso
comercial real, troque ``SQLiteLeadRepository`` por um Postgres gerenciado
(Supabase/Neon têm plano gratuito) — a interface ``LeadRepository`` existe
justamente para que essa troca não toque em nenhuma linha de UI.

⚠️ AVISO LGPD: esta tabela guarda dados de contato de pessoas jurídicas e
nomes de sócios (pessoa natural). Garanta base legal (legítimo interesse para
prospecção B2B), política de retenção e o direito de eliminação.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import pandas as pd

from ..config import settings
from ..core.models import Empresa

logger = logging.getLogger(__name__)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
    cnpj            TEXT PRIMARY KEY,
    razao_social    TEXT,
    nome_fantasia   TEXT,
    telefone        TEXT,
    email           TEXT,
    municipio       TEXT,
    uf              TEXT,
    regime          TEXT,
    porte           TEXT,
    situacao        TEXT,
    cnae_principal  TEXT,
    anexo           TEXT,
    capital_social  REAL,
    consultado_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_uf ON leads(uf);
CREATE INDEX IF NOT EXISTS idx_leads_consulta ON leads(consultado_em DESC);
"""

_COLUNAS = (
    "cnpj", "razao_social", "nome_fantasia", "telefone", "email", "municipio",
    "uf", "regime", "porte", "situacao", "cnae_principal", "anexo",
    "capital_social", "consultado_em",
)


class LeadRepository(Protocol):
    """Contrato mínimo — permite trocar SQLite por Postgres sem tocar na UI."""

    def salvar_varios(self, empresas: Iterable[Empresa]) -> int: ...
    def listar(self) -> pd.DataFrame: ...
    def remover(self, cnpj: str) -> bool: ...
    def total(self) -> int: ...


class SQLiteLeadRepository:
    def __init__(self, caminho: Path | None = None) -> None:
        self._caminho = Path(caminho or settings.db_path)
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conexao() as conn:
            conn.executescript(_ESQUEMA)

    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        """Conexão por operação, com WAL e commit/rollback garantidos.

        [CORRIGIDO] O original abria a conexão, executava e chamava
        ``conn.close()`` fora de qualquer ``try/finally`` — uma exceção no meio
        vazava o handle. E ``salvar_lead_db`` engolia toda exceção com
        ``except Exception: pass``: o usuário via "salvo no CRM!" mesmo quando
        nada tinha sido gravado.
        """
        conn = sqlite3.connect(self._caminho, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    def salvar_varios(self, empresas: Iterable[Empresa]) -> int:
        linhas = [
            (
                e.cnpj, e.razao_social, e.nome_fantasia, e.telefone_str, e.email_str,
                e.endereco.municipio, e.endereco.uf, e.regime, e.porte,
                e.situacao.situacao_receita, e.cnae_principal_str,
                e.atividade_principal.diagnostico.anexo if e.atividade_principal else "",
                e.capital_social, e.consultado_em.isoformat(),
            )
            for e in empresas
        ]
        if not linhas:
            return 0

        placeholders = ", ".join("?" * len(_COLUNAS))
        sql = (f"INSERT OR REPLACE INTO leads ({', '.join(_COLUNAS)}) "
               f"VALUES ({placeholders})")
        with self._lock, self._conexao() as conn:
            conn.executemany(sql, linhas)
        logger.info("Persistidos %d lead(s) no CRM.", len(linhas))
        return len(linhas)

    def salvar(self, empresa: Empresa) -> int:
        return self.salvar_varios([empresa])

    def listar(self) -> pd.DataFrame:
        with self._conexao() as conn:
            return pd.read_sql_query(
                "SELECT * FROM leads ORDER BY consultado_em DESC, razao_social", conn
            )

    def remover(self, cnpj: str) -> bool:
        with self._lock, self._conexao() as conn:
            cursor = conn.execute("DELETE FROM leads WHERE cnpj = ?", (cnpj,))
            return cursor.rowcount > 0

    def total(self) -> int:
        with self._conexao() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0])


# --------------------------------------------------------------------------- #
# Fábrica — escolhe o backend pelo ambiente                                    #
# --------------------------------------------------------------------------- #
def criar_repositorio() -> LeadRepository:
    """Postgres se ``DATABASE_URL`` estiver definida; SQLite caso contrário.

    A escolha é feita aqui, num lugar só. A UI conversa com o ``Protocol`` e
    não sabe qual backend está atrás — é o que permite migrar de SQLite para
    Postgres sem tocar em nenhuma tela.

    Se ``DATABASE_URL`` existir mas a conexão falhar, **propaga o erro** em vez
    de cair silenciosamente no SQLite: escrever no banco errado é pior que
    falhar alto, porque os leads gravados no disco efêmero somem no próximo
    deploy sem ninguém notar.
    """
    from ..config import DATABASE_URL

    if not DATABASE_URL:
        logger.info("DATABASE_URL ausente — usando SQLite em %s",
                    settings.db_path)
        return SQLiteLeadRepository()

    from .repository_pg import PostgresLeadRepository
    logger.info("Usando Postgres (DATABASE_URL definida).")
    return PostgresLeadRepository(DATABASE_URL)


def backend_em_uso() -> str:
    """Rótulo para exibir na aba CRM — o usuário precisa saber se a base é
    persistente ou vai evaporar no próximo deploy."""
    from ..config import DATABASE_URL
    return "PostgreSQL (persistente)" if DATABASE_URL else "SQLite (efêmero em PaaS)"
