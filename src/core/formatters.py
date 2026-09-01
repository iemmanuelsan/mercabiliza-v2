"""Formatação pt-BR e sanitização de texto."""

from __future__ import annotations

import unicodedata
from urllib.parse import quote_plus


def moeda(valor: float | None) -> str:
    """1234.5 -> 'R$ 1.234,50' (sem depender de locale instalado no servidor)."""
    v = float(valor or 0.0)
    inteiro = f"{abs(v):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{'-' if v < 0 else ''}R$ {inteiro}"


def percentual(fracao: float | None, casas: int = 2) -> str:
    return f"{float(fracao or 0.0) * 100:.{casas}f}".replace(".", ",") + "%"


def sem_acento(texto: object) -> str:
    """Transliteração para ASCII — usada apenas em fallback de fonte no PDF."""
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in normalizado if not unicodedata.combining(c)) \
        .encode("ascii", "ignore").decode("ascii").strip()


def texto_ou(valor: object, padrao: str = "Não informado") -> str:
    """Evita que ``None`` vaze como a string 'None' em PDFs e planilhas."""
    if valor is None:
        return padrao
    s = str(valor).strip()
    return s if s and s.lower() not in {"none", "nan"} else padrao


def url_google_maps(endereco_linha: str) -> str:
    """[CORRIGIDO] Antes usava ``.replace(' ', '+')``, que quebra com
    acentos, ``#``, ``&`` e com campos ``None``."""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(endereco_linha)}"


def url_whatsapp(telefone_digits: str, mensagem: str) -> str | None:
    """Monta o link wa.me a partir de UM telefone já isolado."""
    numero = "".join(ch for ch in str(telefone_digits) if ch.isdigit())
    if len(numero) < 10:
        return None
    if not numero.startswith("55"):
        numero = "55" + numero
    return f"https://wa.me/{numero[:13]}?text={quote_plus(mensagem)}"
