"""Smoke test de renderização: o app inteiro precisa executar sem exceção.

Usa ``streamlit.testing.v1.AppTest``, que roda o script de verdade (todas as
abas, todos os widgets) num runner headless. Pega justamente a classe de erro
que passaria despercebida em testes de unidade: ``KeyError`` numa chave de
dicionário, ``st.metric`` recebendo tipo inválido, import circular.

A rede é bloqueada de propósito — o app deve degradar com elegância quando as
APIs públicas estão fora, não estourar tela de erro.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

TIMEOUT = 60
APP = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def sem_rede(monkeypatch):
    """Simula indisponibilidade total das APIs externas."""
    import requests

    def _falhar(*args, **kwargs):
        raise requests.ConnectionError("rede bloqueada no teste")

    monkeypatch.setattr(requests.Session, "get", _falhar)
    monkeypatch.setattr(requests, "get", _falhar)


@pytest.fixture
def app(tmp_path, monkeypatch, sem_rede):
    monkeypatch.setenv("MERCABILIZA_DATA_DIR", str(tmp_path))
    return AppTest.from_file(str(APP), default_timeout=TIMEOUT)


def test_app_renderiza_sem_excecao(app):
    app.run()
    assert not app.exception, [str(e) for e in app.exception]


def test_as_cinco_abas_existem(app):
    app.run()
    assert len(app.tabs) >= 5


def test_titulo_e_sidebar_presentes(app):
    app.run()
    assert any("Inteligência Tributária" in t.value for t in app.title)
    assert app.sidebar is not None


def test_cnpj_invalido_mostra_erro_amigavel(app):
    """Não pode estourar traceback: o usuário precisa ver uma mensagem."""
    app.run()
    app.text_input[0].set_value("123").run()
    app.button[0].click().run()
    assert not app.exception
    assert any("CNPJ" in e.value for e in app.error)


def test_comparador_calcula_sem_rede(app):
    """A aba 2 é 100% offline — deve funcionar mesmo com as APIs fora."""
    app.run()
    assert not app.exception
    assert any("Simples" in m.label or "Simples" in str(m.value) for m in app.metric)


def test_apis_fora_nao_quebram_a_calculadora_mei(app):
    """O BACEN indisponível deve cair no fallback, não em tela de erro."""
    app.run()
    assert not app.exception
    assert app.metric  # a aba MEI renderizou suas métricas


# --------------------------------------------------------------------------- #
# Aba de contratos                                                            #
# --------------------------------------------------------------------------- #
def test_aba_contratos_existe(app):
    app.run()
    assert len(app.tabs) >= 6


def test_alternar_para_pessoa_fisica_nao_quebra(app):
    """Trocar PJ -> PF troca o formulário inteiro; é onde estado mal gerenciado
    normalmente estoura."""
    app.run()
    radio = next(r for r in app.radio if r.label == "Modalidade")
    radio.set_value("PF — Abertura de empresa").run()
    assert not app.exception, [str(e) for e in app.exception]


def test_cpf_invalido_mostra_erro_sem_traceback(app):
    app.run()
    next(r for r in app.radio if r.label == "Modalidade") \
        .set_value("PF — Abertura de empresa").run()
    campo = next(t for t in app.text_input if t.label == "CPF *")
    campo.set_value("111").run()
    assert not app.exception
    assert any("CPF" in e.value for e in app.error)


def test_modalidade_mei_oferece_formulario_de_desenquadramento(app):
    """A modalidade MEI muda o rótulo do botão de DOCX."""
    app.run()
    next(r for r in app.radio if r.label == "Modalidade") \
        .set_value("MEI — Desenquadramento").run()
    assert not app.exception, [str(e) for e in app.exception]


def _antigo_test_contratada_incompleta_avisa_na_tela(app):
    """Desativado: a CONTRATADA passou a ser texto fixo de duas empresas, sem
    CRC e sem pessoa física, por decisão de negócio."""
    app.run()
    assert any("Mercabiliza" in w.value for w in app.warning)


def test_gerar_contrato_pelo_botao_produz_download(app):
    """Fluxo completo: clicar em gerar e ter o botão de download aparecendo."""
    app.run()
    botao = next((b for b in app.button if "Gerar Contrato" in b.label), None)
    assert botao is not None, "botão de gerar contrato não encontrado"
    botao.click().run()
    assert not app.exception, [str(e) for e in app.exception]
