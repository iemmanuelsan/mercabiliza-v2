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
    next(r for r in app.radio if r.label == "Modalidade").set_value(
        "PF — Abertura de empresa"
    ).run()
    campo = next(t for t in app.text_input if t.label == "CPF *")
    campo.set_value("111").run()
    assert not app.exception
    assert any("CPF" in e.value for e in app.error)


def test_modalidade_mei_oferece_formulario_de_desenquadramento(app):
    """A modalidade MEI muda o rótulo do botão de DOCX."""
    app.run()
    next(r for r in app.radio if r.label == "Modalidade").set_value(
        "MEI — Desenquadramento"
    ).run()
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


# --------------------------------------------------------------------------- #
# Formulário de transição contábil                                             #
# --------------------------------------------------------------------------- #
def test_bloco_de_transicao_aparece_na_aba_de_documentos(app):
    app.run()
    assert any("transição contábil" in s.value.lower() for s in app.subheader), (
        "o bloco de transição não foi renderizado"
    )


def test_gerar_formulario_de_transicao_produz_download(app):
    """Fluxo completo sem preencher nada: o formulário em branco é um uso
    legítimo — é o impresso que substitui a planilha."""
    app.run()
    botao = next((b for b in app.button if "transição" in b.label.lower()), None)
    assert botao is not None, "botão de gerar transição não encontrado"
    botao.click().run()
    assert not app.exception, [str(e) for e in app.exception]

    baixar = [b for b in app.download_button if "transição" in b.label.lower()]
    assert baixar, "o download do formulário de transição não apareceu"


def test_transicao_funciona_tambem_na_modalidade_pf(app):
    """Em PF não há CNPJ para consultar, e o bloco recebe ``None``. Não pode
    estourar — só sai sem prefill."""
    app.run()
    next(r for r in app.radio if r.label == "Modalidade").set_value(
        "PF — Abertura de empresa"
    ).run()
    botao = next((b for b in app.button if "transição" in b.label.lower()), None)
    assert botao is not None
    botao.click().run()
    assert not app.exception, [str(e) for e in app.exception]


def test_a_tela_so_manda_campos_que_o_exportador_conhece():
    """As chaves escritas à mão no ``_bloco_transicao`` têm de existir em
    ``CAMPOS_POR_BLOCO``.

    Sem isto, um nome digitado errado na tela viraria ``CampoDesconhecidoError``
    só quando alguém clicasse no botão em produção — e o teste acima gera o
    formulário em branco, que não exercita todas as chaves.
    """
    import ast
    import inspect

    from src.exporters.docx_transicao import CAMPOS_POR_BLOCO
    from src.ui.tabs import contratos

    fonte = inspect.getsource(contratos._bloco_transicao)
    arvore = ast.parse(inspect.cleandoc(fonte))

    chamada = next(
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and getattr(no.func, "id", "") == "gerar_formulario_transicao"
    )
    conferidos = set()
    for argumento in chamada.keywords:
        bloco = argumento.arg.removeprefix("dados_")
        if not isinstance(argumento.value, ast.Dict):
            continue  # `dados_iniciais` é uma dict comp; conferido logo abaixo
        enviadas = {c.value for c in argumento.value.keys if isinstance(c, ast.Constant)}
        desconhecidas = enviadas - CAMPOS_POR_BLOCO[bloco]
        assert not desconhecidas, (
            f"a tela manda {desconhecidas} no bloco '{bloco}', que o exportador não conhece"
        )
        conferidos.add(bloco)

    # `dados_iniciais` é montado antes da chamada, num `iniciais.update({...})`.
    # Sem conferi-lo aqui, o bloco com MAIS campos ficaria justamente de fora.
    atualizacoes = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and getattr(no.func, "attr", "") == "update"
        and getattr(getattr(no.func, "value", None), "id", "") == "iniciais"
    ]
    assert atualizacoes, "não achei o `iniciais.update({...})` para conferir"
    for chamada_update in atualizacoes:
        for arg in chamada_update.args:
            if not isinstance(arg, ast.Dict):
                continue
            enviadas = {c.value for c in arg.keys if isinstance(c, ast.Constant)}
            desconhecidas = enviadas - CAMPOS_POR_BLOCO["iniciais"]
            assert not desconhecidas, (
                f"a tela manda {desconhecidas} em 'iniciais', que o exportador não conhece"
            )
            conferidos.add("iniciais")

    assert conferidos == set(CAMPOS_POR_BLOCO), (
        f"blocos não conferidos por este teste: {set(CAMPOS_POR_BLOCO) - conferidos}"
    )
