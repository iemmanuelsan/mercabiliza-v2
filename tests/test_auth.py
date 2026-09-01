"""Testes do portão de autenticação.

Este é o teste mais importante do repositório em termos de risco: se o gate
falhar aberto, a base de leads (nome, CNPJ, e-mail e telefone de clientes reais)
fica pública para quem tiver a URL. Por isso aqui se testa o comportamento
observável — quantas abas aparecem, se a aba CRM está na tela — e não só o
retorno das funções internas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from src.ui.auth import ENV_SENHA_GERAL, ENV_SENHAS, _senhas_configuradas, _validar

TIMEOUT = 60
APP = Path(__file__).resolve().parent.parent / "app.py"

SENHA = "senha-de-teste-longa-o-suficiente"


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch, tmp_path):
    """Isola cada teste: sem senha herdada e sem tocar o banco real."""
    monkeypatch.delenv(ENV_SENHAS, raising=False)
    monkeypatch.delenv(ENV_SENHA_GERAL, raising=False)
    monkeypatch.setenv("MERCABILIZA_DATA_DIR", str(tmp_path))


@pytest.fixture
def sem_rede(monkeypatch):
    import requests

    def _falhar(*args, **kwargs):
        raise requests.ConnectionError("rede bloqueada no teste")

    monkeypatch.setattr(requests.Session, "get", _falhar)
    monkeypatch.setattr(requests, "get", _falhar)


# --------------------------------------------------------------------------- #
# Leitura da configuração                                                     #
# --------------------------------------------------------------------------- #
def test_sem_config_retorna_vazio():
    assert _senhas_configuradas() == {}


def test_le_json_do_ambiente(monkeypatch):
    monkeypatch.setenv(ENV_SENHAS, '{"iago":"abc","luisfelipe":"def"}')
    assert _senhas_configuradas() == {"iago": "abc", "luisfelipe": "def"}


def test_usuario_do_json_normalizado_para_minusculo(monkeypatch):
    """O formulário faz .lower(); a config precisa combinar."""
    monkeypatch.setenv(ENV_SENHAS, '{"Iago":"abc"}')
    assert "iago" in _senhas_configuradas()


def test_senha_geral_do_ambiente(monkeypatch):
    monkeypatch.setenv(ENV_SENHA_GERAL, SENHA)
    assert _senhas_configuradas() == {"equipe": SENHA}


def test_json_invalido_nao_abre_o_gate(monkeypatch):
    """Erro de digitação no painel não pode virar app sem senha.

    Cai para a próxima fonte; não havendo nenhuma, o dicionário fica vazio e o
    app avisa em tela. O que NÃO pode acontecer é engolir o erro em silêncio —
    daí o log de nível ERROR verificado abaixo.
    """
    monkeypatch.setenv(ENV_SENHAS, "iago:abc")   # esqueceu de usar JSON
    assert _senhas_configuradas() == {}


def test_json_invalido_registra_erro(monkeypatch, caplog):
    monkeypatch.setenv(ENV_SENHAS, "{isto nao e json}")
    with caplog.at_level("ERROR"):
        _senhas_configuradas()
    assert any("JSON" in r.message for r in caplog.records)


def test_ambiente_tem_prioridade_sobre_secrets(monkeypatch):
    """secrets.toml esquecido na máquina não pode vencer a senha de produção."""
    monkeypatch.setenv(ENV_SENHA_GERAL, "producao")
    monkeypatch.setattr("src.ui.auth._dos_secrets",
                        lambda: {"equipe": "local-antiga"})
    assert _senhas_configuradas() == {"equipe": "producao"}


# --------------------------------------------------------------------------- #
# Comparação                                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("usuario,senha,esperado", [
    ("iago", SENHA, True),
    ("iago", SENHA + "x", False),
    ("iago", SENHA[:-1], False),
    ("iago", "", False),
    ("inexistente", SENHA, False),
    ("", SENHA, False),
])
def test_validar(usuario, senha, esperado):
    assert _validar(usuario, senha, {"iago": SENHA}) is esperado


# --------------------------------------------------------------------------- #
# Comportamento no app                                                        #
# --------------------------------------------------------------------------- #
def test_com_senha_o_app_nao_renderiza_as_abas(monkeypatch, sem_rede):
    """O ponto central: anônimo não vê nada além do formulário."""
    monkeypatch.setenv(ENV_SENHA_GERAL, SENHA)
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    assert not app.exception, [str(e) for e in app.exception]
    assert len(app.tabs) == 0, "abas renderizadas antes do login"
    assert len(app.text_input) == 1, "esperado apenas o campo de senha"


def test_crm_nao_aparece_antes_do_login(monkeypatch, sem_rede):
    """Verificação explícita do dado sensível, não só da contagem de abas."""
    monkeypatch.setenv(ENV_SENHA_GERAL, SENHA)
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    tela = " ".join([m.value for m in app.markdown]
                    + [c.value for c in app.caption]
                    + [t.value for t in app.title])
    assert "CRM" not in tela


def test_senha_correta_libera_o_app(monkeypatch, sem_rede):
    monkeypatch.setenv(ENV_SENHA_GERAL, SENHA)
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    app.text_input[0].set_value(SENHA)
    app.button[0].click().run()

    assert not app.exception, [str(e) for e in app.exception]
    assert len(app.tabs) >= 5, "app deveria estar liberado após login válido"


def test_senha_errada_mostra_erro_e_nao_libera(monkeypatch, sem_rede):
    monkeypatch.setenv(ENV_SENHA_GERAL, SENHA)
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    app.text_input[0].set_value("chute")
    app.button[0].click().run()

    assert len(app.tabs) == 0
    assert any("inválid" in e.value.lower() for e in app.error)


def test_sem_senha_o_app_abre_mas_avisa(sem_rede):
    """Sem config, o gate fica aberto para não travar o dev local — com aviso.

    O aviso é o que impede a ausência de senha de passar em branco até a
    publicação, então ele é parte do contrato e é testado.
    """
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    assert not app.exception, [str(e) for e in app.exception]
    assert len(app.tabs) >= 5
    assert any("autentica" in w.value.lower() for w in app.warning)
