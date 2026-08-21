"""Repositório de leads em PostgreSQL.

## Por que existe

O SQLite funciona bem localmente, mas em PaaS o disco é efêmero (Streamlit
Cloud) ou exige volume pago e preso a uma única instância (Render, Railway,
Fly). Um CRM que perde a base a cada redeploy não é CRM.

Este módulo implementa o mesmo ``Protocol`` de ``repository.py``, então a
troca é **uma linha de configuração** — nenhuma tela muda.

## Ativação

Defina ``DATABASE_URL`` no ambiente. Render e Railway injetam essa variável
automaticamente ao criar o Postgres gerenciado e vinculá-lo ao serviço.

    DATABASE_URL=postgresql://usuario:senha@host:5432/banco

Sem a variável, o app usa SQLite e avisa na aba CRM. A dependência
``psycopg[binary]`` é opcional: se não estiver instalada, o import falha de
forma explícita com instrução em vez de estourar no meio de uma consulta.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

import pandas as pd

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
    capital_social  DOUBLE PRECISION,
    consultado_em   DATE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_uf ON leads(uf);
CREATE INDEX IF NOT EXISTS idx_leads_consulta ON leads(consultado_em DESC);
"""

_COLUNAS = (
    "cnpj", "razao_social", "nome_fantasia", "telefone", "email", "municipio",
    "uf", "regime", "porte", "situacao", "cnae_principal", "anexo",
    "capital_social", "consultado_em",
)


class PsycopgAusenteError(ImportError):
    """``DATABASE_URL`` definida mas o driver não está instalado."""


def _conectar(url: str):
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise PsycopgAusenteError(
            "DATABASE_URL está definida mas 'psycopg' não está instalado. "
            "Acrescente 'psycopg[binary]>=3.1' ao requirements.txt."
        ) from exc
    return psycopg.connect(url, autocommit=False)


class PostgresLeadRepository:
    """Mesma interface do :class:`SQLiteLeadRepository`, em Postgres.

    Abre conexão por operação em vez de manter um pool: o volume aqui é de
    dezenas de escritas por dia, não milhares por segundo, e conexão curta
    evita o problema clássico de conexão morta após o PaaS reciclar o
    container.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        with self._conexao() as conn, conn.cursor() as cur:
            cur.execute(_ESQUEMA)
        logger.info("Repositório Postgres inicializado.")

    @contextmanager
    def _conexao(self) -> Iterator:
        conn = _conectar(self._url)
        try:
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
                e.cnpj, e.razao_social, e.nome_fantasia, e.telefone_str,
                e.email_str, e.endereco.municipio, e.endereco.uf, e.regime,
                e.porte, e.situacao.situacao_receita, e.cnae_principal_str,
                e.atividade_principal.diagnostico.anexo
                if e.atividade_principal else "",
                e.capital_social, e.consultado_em,
            )
            for e in empresas
        ]
        if not linhas:
            return 0

        placeholders = ", ".join(["%s"] * len(_COLUNAS))
        atualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUNAS
                             if c != "cnpj")
        sql = (
            f"INSERT INTO leads ({', '.join(_COLUNAS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (cnpj) DO UPDATE SET {atualiza}"
        )
        with self._conexao() as conn, conn.cursor() as cur:
            cur.executemany(sql, linhas)
        logger.info("Persistidos %d lead(s) no Postgres.", len(linhas))
        return len(linhas)

    def salvar(self, empresa: Empresa) -> int:
        return self.salvar_varios([empresa])

    def listar(self) -> pd.DataFrame:
        with self._conexao() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM leads ORDER BY consultado_em DESC, razao_social")
            colunas = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=colunas)

    def remover(self, cnpj: str) -> bool:
        with self._conexao() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM leads WHERE cnpj = %s", (cnpj,))
            return cur.rowcount > 0

    def total(self) -> int:
        with self._conexao() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM leads")
            return int(cur.fetchone()[0])
