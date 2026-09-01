"""Consulta e consolidação de dados cadastrais de CNPJ.

Três provedores públicos são consultados **em paralelo** e o resultado é
fundido por prioridade. Cada provedor é isolado num *adapter* com uma única
responsabilidade: traduzir o JSON dele para um dicionário canônico. Assim, se
a BrasilAPI mudar o schema amanhã, só um arquivo muda.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import BRASIL_API_CNPJ, CNPJ_WS_PUBLICA, RECEITA_WS, settings
from ..core.models import (
    AtividadeCNAE,
    Empresa,
    Endereco,
    SituacaoCadastral,
    Socio,
)
from ..core.tributario import classificar_cnae
from .http import criar_sessao, get_json
from .indicadores import consultar_municipio_ibge

logger = logging.getLogger(__name__)

Canonico = dict[str, Any]


def _limpo(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto.lower() in {"none", "nan", "null"} else texto


def _float(valor: Any) -> float:
    try:
        return float(str(valor).replace(",", ".")) if valor not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _com_tipo_logradouro(tipo: Any, nome: Any) -> str:
    """Junta 'RUA' + 'ANCHIETA' -> 'RUA ANCHIETA'.

    Evita duplicar quando o provedor já entrega o tipo embutido no nome
    (acontece com parte dos registros).
    """
    tipo_limpo, nome_limpo = _limpo(tipo), _limpo(nome)
    if not tipo_limpo:
        return nome_limpo
    if not nome_limpo:
        return tipo_limpo
    if nome_limpo.upper().startswith(tipo_limpo.upper()):
        return nome_limpo
    return f"{tipo_limpo} {nome_limpo}"


def _dedup_telefones(telefones: list[str]) -> list[str]:
    """Deduplica por dígitos, preservando a formatação mais legível.

    [CORRIGIDO] Deduplicar por string deixava passar o mesmo número em
    formatos diferentes. Um caso real: '(19) 3327-0038', '(19) 33270038' e
    '193327003' apareceram os três no mesmo cartão CNPJ.
    """
    melhores: dict[str, str] = {}
    for bruto in telefones:
        texto = _limpo(bruto)
        digitos = "".join(c for c in texto if c.isdigit())
        if len(digitos) < 10:        # descarta fragmentos truncados
            continue
        chave = digitos[-11:] if len(digitos) > 11 else digitos
        atual = melhores.get(chave)
        # Prefere a versão com máscara (mais legível para o cliente).
        if atual is None or (not any(c in atual for c in "()-")
                             and any(c in texto for c in "()-")):
            melhores[chave] = texto
    return sorted(melhores.values())


# --------------------------------------------------------------------------- #
# Adapters                                                                     #
# --------------------------------------------------------------------------- #
def _de_brasilapi(d: Canonico) -> Canonico:
    return {
        "fonte": "BrasilAPI",
        "razao_social": _limpo(d.get("razao_social")),
        "nome_fantasia": _limpo(d.get("nome_fantasia")),
        "situacao": _limpo(d.get("descricao_situacao_cadastral")),
        "data_situacao": _limpo(d.get("data_situacao_cadastral")),
        "porte": _limpo(d.get("porte")),
        "natureza_juridica": _limpo(d.get("natureza_juridica")),
        "capital_social": _float(d.get("capital_social")),
        "data_abertura": _limpo(d.get("data_inicio_atividade")),
        "matriz": d.get("identificador_matriz_filial") == 1,
        "emails": [_limpo(d.get("email")).lower()],
        "telefones": [_limpo(d.get("ddd_telefone_1")), _limpo(d.get("ddd_telefone_2"))],
        "optante_simples": bool(d.get("opcao_pelo_simples")),
        "optante_mei": bool(d.get("opcao_pelo_mei")),
        "cnae_codigo": _limpo(d.get("cnae_fiscal")),
        "cnae_descricao": _limpo(d.get("cnae_fiscal_descricao")),
        "cnaes_secundarios": [
            (_limpo(c.get("codigo")), _limpo(c.get("descricao")))
            for c in d.get("cnaes_secundarios") or []
        ],
        # [CORRIGIDO] A BrasilAPI separa o tipo do logradouro em outro campo.
        # Sem juntar os dois, o endereço saía "ANCHIETA, 204" em vez de
        # "RUA ANCHIETA, 204" — aceitável num dossiê, inaceitável num contrato.
        "logradouro": _com_tipo_logradouro(
            d.get("descricao_tipo_de_logradouro"), d.get("logradouro")),
        "numero": _limpo(d.get("numero")),
        "bairro": _limpo(d.get("bairro")),
        "municipio": _limpo(d.get("municipio")),
        "uf": _limpo(d.get("uf")),
        "cep": _limpo(d.get("cep")),
        "socios": [
            (_limpo(s.get("nome_socio")), _limpo(s.get("qualificacao_socio")),
             _limpo(s.get("faixa_etaria")) or "N/A")
            for s in d.get("qsa") or []
        ],
        "inscricoes_estaduais": [],
        "inscricao_municipal": "",
    }


def _de_cnpjws(d: Canonico) -> Canonico:
    estab = d.get("estabelecimento") or {}
    atividade = estab.get("atividade_principal") or {}
    ies = []
    for ie in estab.get("inscricoes_estaduais") or []:
        numero = _limpo(ie.get("inscricao_estadual")) or "N/A"
        uf = _limpo((ie.get("estado") or {}).get("sigla"))
        status = "Ativa" if ie.get("ativo") else "Inativa/Baixada"
        ies.append(f"{numero} ({uf}) - [{status}]")

    ddd, fone = _limpo(estab.get("ddd1")), _limpo(estab.get("telefone1"))
    return {
        "fonte": "CNPJ.ws",
        "razao_social": _limpo(d.get("razao_social")),
        "nome_fantasia": _limpo(estab.get("nome_fantasia")),
        "situacao": _limpo(estab.get("situacao_cadastral")),
        "data_situacao": _limpo(estab.get("data_situacao_cadastral")),
        "porte": _limpo((d.get("porte") or {}).get("descricao")),
        "natureza_juridica": _limpo((d.get("natureza_juridica") or {}).get("descricao")),
        "capital_social": _float(d.get("capital_social")),
        "data_abertura": _limpo(estab.get("data_inicio_atividade")),
        "matriz": _limpo(estab.get("tipo")).upper().startswith("MATRIZ"),
        "emails": [_limpo(estab.get("email")).lower()],
        "telefones": [f"({ddd}) {fone}".strip() if (ddd or fone) else ""],
        "optante_simples": (d.get("simples") or {}).get("simples") == "Sim",
        "optante_mei": (d.get("simples") or {}).get("mei") == "Sim",
        "cnae_codigo": _limpo(atividade.get("subclasse")),
        "cnae_descricao": _limpo(atividade.get("descricao")),
        "cnaes_secundarios": [
            (_limpo(c.get("subclasse")), _limpo(c.get("descricao")))
            for c in estab.get("atividades_secundarias") or []
        ],
        "logradouro": _limpo(estab.get("logradouro")),
        "numero": _limpo(estab.get("numero")),
        "bairro": _limpo(estab.get("bairro")),
        "municipio": _limpo((estab.get("cidade") or {}).get("nome")),
        "uf": _limpo((estab.get("estado") or {}).get("sigla")),
        "cep": _limpo(estab.get("cep")),
        "socios": [
            (_limpo(s.get("nome")),
             _limpo((s.get("qualificacao_socio") or {}).get("descricao")), "N/A")
            for s in d.get("socios") or []
        ],
        "inscricoes_estaduais": ies,
        "inscricao_municipal": _limpo(estab.get("inscricao_municipal")),
    }


def _de_receitaws(d: Canonico) -> Canonico:
    principais = d.get("atividade_principal") or [{}]
    return {
        "fonte": "ReceitaWS",
        "razao_social": _limpo(d.get("nome")),
        "nome_fantasia": _limpo(d.get("fantasia")),
        "situacao": _limpo(d.get("situacao")),
        "data_situacao": _limpo(d.get("data_situacao")),
        "porte": _limpo(d.get("porte")),
        "natureza_juridica": _limpo(d.get("natureza_juridica")),
        "capital_social": _float(d.get("capital_social")),
        "data_abertura": _limpo(d.get("abertura")),
        "matriz": _limpo(d.get("tipo")).upper().startswith("MATRIZ"),
        "emails": [_limpo(d.get("email")).lower()],
        "telefones": [t.strip() for t in _limpo(d.get("telefone")).split("/") if t.strip()],
        "optante_simples": bool((d.get("simples") or {}).get("optante")),
        "optante_mei": bool((d.get("simei") or {}).get("optante")),
        "cnae_codigo": _limpo(principais[0].get("code")),
        "cnae_descricao": _limpo(principais[0].get("text")),
        "cnaes_secundarios": [
            (_limpo(c.get("code")), _limpo(c.get("text")))
            for c in d.get("atividades_secundarias") or []
        ],
        "logradouro": _limpo(d.get("logradouro")),
        "numero": _limpo(d.get("numero")),
        "bairro": _limpo(d.get("bairro")),
        "municipio": _limpo(d.get("municipio")),
        "uf": _limpo(d.get("uf")),
        "cep": _limpo(d.get("cep")),
        "socios": [
            (_limpo(s.get("nome")), _limpo(s.get("qual")), "N/A")
            for s in d.get("qsa") or []
        ],
        "inscricoes_estaduais": [],
        "inscricao_municipal": "",
    }


PROVEDORES: tuple[tuple[str, str, Callable[[Canonico], Canonico]], ...] = (
    ("BrasilAPI", BRASIL_API_CNPJ, _de_brasilapi),
    ("CNPJ.ws", CNPJ_WS_PUBLICA, _de_cnpjws),
    ("ReceitaWS", RECEITA_WS, _de_receitaws),
)


# --------------------------------------------------------------------------- #
# Consolidação                                                                 #
# --------------------------------------------------------------------------- #
def _primeiro_preenchido(fontes: list[Canonico], chave: str, padrao: Any = "") -> Any:
    """Pega o primeiro valor não-vazio na ordem de prioridade dos provedores.

    [CORRIGIDO] O original usava cadeias de ``or`` terminadas em
    ``dados_rws.get(...)`` sem checar se ``dados_rws`` era ``None`` — um
    ``AttributeError`` garantido sempre que a BrasilAPI respondia com campo
    vazio e a ReceitaWS estava fora.
    """
    for fonte in fontes:
        valor = fonte.get(chave)
        if valor not in (None, "", 0.0, [], ()):
            return valor
    return padrao


def consolidar(cnpj: str, fontes: list[Canonico], rbt12: float = 0.0) -> Empresa:
    emails = sorted({e for f in fontes for e in f.get("emails", []) if e})
    telefones = _dedup_telefones(
        [t for f in fontes for t in f.get("telefones", []) if t])

    municipio = _primeiro_preenchido(fontes, "municipio")
    uf = _primeiro_preenchido(fontes, "uf")
    cod_ibge, regiao = consultar_municipio_ibge(municipio, uf)

    endereco = Endereco(
        logradouro=_primeiro_preenchido(fontes, "logradouro"),
        numero=_primeiro_preenchido(fontes, "numero"),
        bairro=_primeiro_preenchido(fontes, "bairro"),
        municipio=municipio, uf=uf,
        cep=_primeiro_preenchido(fontes, "cep"),
        cod_ibge=cod_ibge, regiao=regiao,
    )

    cnae_cod = _primeiro_preenchido(fontes, "cnae_codigo")
    cnae_desc = _primeiro_preenchido(fontes, "cnae_descricao")
    principal = AtividadeCNAE(
        codigo=cnae_cod or "N/A",
        descricao=cnae_desc or "Não informado",
        diagnostico=classificar_cnae(cnae_cod, rbt12),
    ) if (cnae_cod or cnae_desc) else None

    secundarias_brutas = _primeiro_preenchido(fontes, "cnaes_secundarios", [])
    secundarias = tuple(
        AtividadeCNAE(codigo=cod, descricao=desc, diagnostico=classificar_cnae(cod, rbt12))
        for cod, desc in secundarias_brutas if cod
    )

    socios = tuple(
        Socio(nome=nome, qualificacao=qual or "Não informada", faixa_etaria=faixa)
        for nome, qual, faixa in _primeiro_preenchido(fontes, "socios", []) if nome
    )

    return Empresa(
        cnpj=cnpj,
        razao_social=_primeiro_preenchido(fontes, "razao_social", "Não informada"),
        nome_fantasia=_primeiro_preenchido(fontes, "nome_fantasia")
        or _primeiro_preenchido(fontes, "razao_social", "Não informada"),
        matriz_filial="MATRIZ" if _primeiro_preenchido(fontes, "matriz", False) else "FILIAL",
        data_abertura=_primeiro_preenchido(fontes, "data_abertura", "Não informada"),
        natureza_juridica=_primeiro_preenchido(fontes, "natureza_juridica", "Não informada"),
        porte=_primeiro_preenchido(fontes, "porte", "Não informado"),
        capital_social=_float(_primeiro_preenchido(fontes, "capital_social", 0.0)),
        emails=tuple(emails), telefones=tuple(telefones),
        optante_simples=any(f.get("optante_simples") for f in fontes),
        optante_mei=any(f.get("optante_mei") for f in fontes),
        endereco=endereco,
        situacao=SituacaoCadastral(
            situacao_receita=_primeiro_preenchido(fontes, "situacao", "DESCONHECIDA").upper(),
            data_situacao=_primeiro_preenchido(fontes, "data_situacao"),
        ),
        atividade_principal=principal,
        atividades_secundarias=secundarias,
        inscricoes_estaduais=tuple(_primeiro_preenchido(fontes, "inscricoes_estaduais", [])),
        inscricao_municipal=_primeiro_preenchido(
            fontes, "inscricao_municipal", "Não identificada em busca pública"),
        socios=socios,
        fontes=tuple(f["fonte"] for f in fontes),
    )


def consultar_cnpj(cnpj: str, rbt12: float = 0.0) -> Empresa | None:
    """Consulta os 3 provedores em paralelo e consolida.

    [OTIMIZADO] Antes: 3 requisições sequenciais, ~8s de timeout cada, no pior
    caso 24s por CNPJ. Agora as 3 saem juntas — o custo é o do provedor mais
    lento, não a soma.
    """
    resultados: dict[str, Canonico] = {}

    with criar_sessao() as sessao:
        def _buscar(item):
            nome, template, adapter = item
            bruto = get_json(sessao, template.format(cnpj=cnpj), rotulo=nome)
            if not bruto:
                return nome, None
            if str(bruto.get("status", "")).upper() == "ERROR":
                logger.info("[%s] retornou status ERROR para %s", nome, cnpj)
                return nome, None
            return nome, adapter(bruto)

        with ThreadPoolExecutor(
            max_workers=settings.http.max_workers_provedores,
            thread_name_prefix="cnpj",
        ) as pool:
            for nome, canonico in pool.map(_buscar, PROVEDORES):
                if canonico:
                    resultados[nome] = canonico

    # Preserva a ordem de prioridade declarada em PROVEDORES.
    ordenados = [resultados[nome] for nome, _, _ in PROVEDORES if nome in resultados]
    if not ordenados:
        logger.warning("Nenhum provedor retornou dados para %s", cnpj)
        return None

    return consolidar(cnpj, ordenados, rbt12)
