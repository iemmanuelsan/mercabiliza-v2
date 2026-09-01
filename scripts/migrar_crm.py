#!/usr/bin/env python3
"""Migra o banco de leads da v1 (schema antigo) para a v2.

Uso:
    python scripts/migrar_crm.py leads_contabeis.db

O banco da v1 não tem as colunas ``situacao``, ``cnae_principal``, ``anexo``,
``capital_social`` e usa ``data_consulta`` no lugar de ``consultado_em``. Como
o ``CREATE TABLE IF NOT EXISTS`` da v2 não altera uma tabela existente, apontar
o app novo para o banco antigo falha logo na inicialização com
``no such column: consultado_em``.

Este script cria a tabela nova, copia os dados preservando o que existe e
guarda um backup do original. É idempotente: rodar duas vezes não duplica nada.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

COLUNAS_V2 = (
    "cnpj", "razao_social", "nome_fantasia", "telefone", "email", "municipio",
    "uf", "regime", "porte", "situacao", "cnae_principal", "anexo",
    "capital_social", "consultado_em",
)

ESQUEMA_V2 = """
CREATE TABLE IF NOT EXISTS leads_v2 (
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
"""


def _converter_data(valor: object) -> str:
    """'10/08/2026' -> '2026-08-10'. Mantém ISO se já estiver nesse formato."""
    texto = str(valor or "").strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return datetime.today().date().isoformat()


def migrar(caminho: Path) -> int:
    if not caminho.exists():
        print(f"❌ Arquivo não encontrado: {caminho}")
        return 1

    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    try:
        tabelas = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "leads" not in tabelas:
            print("❌ Não há tabela 'leads' neste arquivo.")
            return 1

        colunas = {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
        if "consultado_em" in colunas:
            print("✅ O banco já está no schema v2 — nada a fazer.")
            return 0

        backup = caminho.with_suffix(caminho.suffix + ".v1.bak")
        shutil.copy2(caminho, backup)
        print(f"💾 Backup salvo em: {backup}")

        linhas = conn.execute("SELECT * FROM leads").fetchall()
        print(f"📦 {len(linhas)} lead(s) encontrado(s).")

        conn.executescript(ESQUEMA_V2)
        placeholders = ", ".join("?" * len(COLUNAS_V2))
        conn.executemany(
            f"INSERT OR REPLACE INTO leads_v2 ({', '.join(COLUNAS_V2)}) "
            f"VALUES ({placeholders})",
            [
                (
                    linha["cnpj"], linha["razao_social"], linha["nome_fantasia"],
                    linha["telefone"], linha["email"], linha["municipio"],
                    linha["uf"], linha["regime"], linha["porte"],
                    "NÃO CONSULTADA",   # situacao — não existia na v1
                    "", "",             # cnae_principal, anexo
                    0.0,                # capital_social
                    _converter_data(linha["data_consulta"]),
                )
                for linha in linhas
            ],
        )
        conn.execute("DROP TABLE leads")
        conn.execute("ALTER TABLE leads_v2 RENAME TO leads")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_uf ON leads(uf)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_consulta ON leads(consultado_em DESC)")
        conn.commit()
        print(f"✅ Migração concluída: {len(linhas)} lead(s) preservado(s).")
        print("   Mova o arquivo para data/leads_contabeis.db e rode o app.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"❌ Falha na migração: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    alvo = Path(sys.argv[1] if len(sys.argv) > 1 else "leads_contabeis.db")
    raise SystemExit(migrar(alvo))
