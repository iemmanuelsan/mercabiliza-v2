"""Testes dos arquivos de infraestrutura.

Erro de infra não aparece em teste de unidade — aparece no deploy, dez minutos
depois do push, com o app fora do ar. Estes testes pegam a classe de erro mais
comum: um `COPY` apontando para pasta que foi renomeada, um segredo que deixou de
ser ignorado, o app e o banco em regiões diferentes.

São baratos (não sobem container, não chamam rede) e rodam junto com o resto.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

DOCKERFILE = RAIZ / "Dockerfile"
DOCKERIGNORE = RAIZ / ".dockerignore"
GITIGNORE = RAIZ / ".gitignore"
RENDER_YAML = RAIZ / "render.yaml"


def _padroes(arquivo: Path) -> list[str]:
    return [linha.strip() for linha in arquivo.read_text().splitlines()
            if linha.strip() and not linha.startswith("#")]


# --------------------------------------------------------------------------- #
# Dockerfile                                                                  #
# --------------------------------------------------------------------------- #
def _origens_copy() -> list[str]:
    """Todas as origens de todo COPY (a última palavra é o destino)."""
    origens: list[str] = []
    for linha in re.findall(r"^COPY\s+(.+)$", DOCKERFILE.read_text(), re.MULTILINE):
        partes = [p for p in linha.split() if not p.startswith("--")]
        origens.extend(partes[:-1])   # descarta o destino
    return origens


def test_todo_copy_aponta_para_caminho_existente():
    """Um COPY de pasta inexistente derruba o build só no deploy."""
    origens = _origens_copy()
    assert origens, "nenhum COPY encontrado — Dockerfile mudou de forma?"
    faltando = [o for o in origens if not (RAIZ / o.rstrip("/")).exists()]
    assert not faltando, f"COPY sem origem no repo: {faltando}"


def test_dockerignore_nao_exclui_o_que_o_dockerfile_copia():
    """Conflito silencioso: o COPY 'funciona' mas chega vazio na imagem."""
    padroes = [p for p in _padroes(DOCKERIGNORE) if not p.startswith("!")]
    for origem in _origens_copy():
        alvo = origem.rstrip("/")
        conflitos = [p for p in padroes if fnmatch.fnmatch(alvo, p.rstrip("/"))]
        assert not conflitos, f"{alvo} é copiado mas casa com {conflitos}"


def test_container_nao_roda_como_root():
    """Root no container transforma qualquer RCE em escalada de privilégio."""
    texto = DOCKERFILE.read_text()
    assert re.search(r"^USER\s+(?!root)", texto, re.MULTILINE), \
        "falta USER não-root no Dockerfile"


def test_healthcheck_usa_endpoint_do_streamlit():
    assert "/_stcore/health" in DOCKERFILE.read_text()


def test_bind_em_todas_as_interfaces():
    """O default do Streamlit escuta em localhost; a plataforma não alcança."""
    assert "--server.address=0.0.0.0" in DOCKERFILE.read_text()


def test_cmd_usa_a_porta_injetada_pela_plataforma():
    assert "${PORT}" in DOCKERFILE.read_text()


@pytest.mark.parametrize("padrao", [".env", "data/", "*.db"])
def test_dockerignore_bloqueia_segredo_e_dado_de_cliente(padrao):
    """Camada de imagem é imutável: o que entra não sai mais."""
    assert padrao in _padroes(DOCKERIGNORE)


# --------------------------------------------------------------------------- #
# Dependências — a separação que protege o deploy do Streamlit Cloud           #
# --------------------------------------------------------------------------- #
REQS = RAIZ / "requirements.txt"
REQS_PG = RAIZ / "requirements-pg.txt"


def test_driver_do_postgres_fora_do_requirements_principal():
    """O Streamlit Cloud lê o requirements.txt e não usa Postgres.

    Se o driver voltar para cá, o deploy do Cloud passa a depender de existir
    wheel dele para a versão de Python da plataforma — que muda sem aviso. Sem
    wheel, o pip aborta a lista inteira e pacotes seguintes nem são instalados.
    """
    assert not any("psycopg" in linha for linha in _padroes(REQS)), (
        "psycopg voltou ao requirements.txt — ver o cabeçalho de "
        "requirements-pg.txt para o motivo de estar separado")


def test_driver_do_postgres_declarado_no_arquivo_proprio():
    assert any("psycopg" in line for line in _padroes(REQS_PG))


def test_dockerfile_instala_os_dois_arquivos():
    """A imagem roda onde HÁ Postgres, então lá o driver é obrigatório."""
    texto = DOCKERFILE.read_text()
    assert "requirements-pg.txt" in texto, \
        "Dockerfile não instala o driver — Postgres falharia em produção"
    instalacao = next(linha for linha in texto.splitlines()
                      if "pip install" in linha)
    assert "-r requirements.txt" in instalacao
    assert "-r requirements-pg.txt" in instalacao


def test_requirements_usa_pisos_e_nao_pins():
    """Pin exato quebra quando a plataforma sobe a versão do Python."""
    pins = [line for line in _padroes(REQS) if "==" in line]
    assert not pins, f"pins exatos reintroduzidos: {pins}"


def test_app_nao_importa_psycopg_sem_database_url(monkeypatch):
    """Sem DATABASE_URL o driver não pode nem ser tocado.

    É o que permite rodar no Streamlit Cloud com o pacote ausente.
    """
    import sys

    monkeypatch.delenv("DATABASE_URL", raising=False)
    for modulo in ("src.services.repository_pg", "psycopg"):
        sys.modules.pop(modulo, None)

    import importlib

    import src.config
    import src.services.repository as repo
    importlib.reload(src.config)
    importlib.reload(repo)
    repo.criar_repositorio()

    assert "src.services.repository_pg" not in sys.modules
    assert "psycopg" not in sys.modules


# --------------------------------------------------------------------------- #
# .gitignore — verificado pelo próprio Git, não por leitura de texto           #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def status_git() -> dict[str, bool]:
    """Cria um repo temporário com o .gitignore real e pergunta ao Git.

    Ler o arquivo e procurar a linha não bastaria: a ordem das regras e as
    negações (``!.env.example``) mudam o resultado. Só o Git sabe de verdade.
    """
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git indisponível")

    amostras = [
        ".env", ".env.producao", ".env.example",
        ".streamlit/secrets.toml", ".streamlit/secrets.toml.example",
        ".streamlit/config.toml",
        "data/leads_contabeis.db", "leads.sqlite3",
        "contrato_cliente.pdf", "planilha.xlsx",
        "chave.pem", "id_rsa", "service_account.json", "client_secret_1.json",
        "app.py", "render.yaml", "DEPLOY.md", "requirements.txt",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        (raiz / ".gitignore").write_text(GITIGNORE.read_text())
        for nome in amostras:
            alvo = raiz / nome
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text("conteudo")
        subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
        # Sem "-v" de propósito: com -v o check-ignore também imprime os
        # caminhos que casaram com uma regra NEGATIVA (!.env.example), e a
        # saída ficaria indistinguível de "ignorado". Sem -v, ele lista
        # apenas o que está realmente ignorado. Sai com 1 quando nada casa,
        # daí não usar check=True.
        saida = subprocess.run(
            ["git", "check-ignore", *amostras],
            cwd=raiz, capture_output=True, text=True).stdout
        ignorados = set(saida.split())
        return {nome: nome in ignorados for nome in amostras}


@pytest.mark.parametrize("arquivo", [
    ".env", ".env.producao", ".streamlit/secrets.toml",
    "data/leads_contabeis.db", "leads.sqlite3",
    "contrato_cliente.pdf", "planilha.xlsx",
    "chave.pem", "id_rsa", "service_account.json", "client_secret_1.json",
])
def test_gitignore_bloqueia(arquivo, status_git):
    assert status_git[arquivo], f"{arquivo} NÃO está sendo ignorado"


@pytest.mark.parametrize("arquivo", [
    ".env.example",                      # documenta as variáveis, sem valores
    ".streamlit/secrets.toml.example",   # idem, formato Streamlit
    ".streamlit/config.toml",            # tema e config pública do app
    "app.py", "render.yaml", "DEPLOY.md", "requirements.txt",
])
def test_gitignore_permite(arquivo, status_git):
    """As negações têm de vencer as regras amplas que vêm antes delas."""
    assert not status_git[arquivo], f"{arquivo} está sendo ignorado por engano"


# --------------------------------------------------------------------------- #
# render.yaml                                                                 #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def render():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(RENDER_YAML.read_text())


def test_render_declara_servico_e_banco(render):
    assert render["services"][0]["runtime"] == "docker"
    assert render["databases"], "sem banco declarado — CRM perderia a base"


def test_render_app_e_banco_na_mesma_regiao(render):
    """Regiões diferentes fazem cada consulta atravessar a internet pública."""
    assert render["services"][0]["region"] == render["databases"][0]["region"]


def test_render_injeta_database_url_do_banco_declarado(render):
    """Sem isso o app cai no SQLite e apaga a base a cada deploy."""
    envs = {e["key"]: e for e in render["services"][0]["envVars"]}
    origem = envs["DATABASE_URL"]["fromDatabase"]
    assert origem["name"] == render["databases"][0]["name"]
    assert origem["property"] == "connectionString"


def test_render_nao_versiona_nenhum_segredo(render):
    """Toda variável de senha precisa de sync:false — o arquivo vai pro Git."""
    for env in render["services"][0]["envVars"]:
        if "SENHA" in env["key"].upper() or "SECRET" in env["key"].upper():
            assert env.get("sync") is False, \
                f"{env['key']} sem sync:false — valor iria para o repositório"
            assert "value" not in env, f"{env['key']} tem valor no arquivo!"


def test_render_healthcheck_bate_com_o_dockerfile(render):
    caminho = render["services"][0]["healthCheckPath"]
    assert caminho in DOCKERFILE.read_text(), \
        "healthCheckPath do Render difere do HEALTHCHECK da imagem"


# --------------------------------------------------------------------------- #
# Modelos de configuração                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("modelo", [
    ".env.example", ".streamlit/secrets.toml.example"])
def test_modelo_existe_e_nao_contem_segredo_real(modelo):
    """O .example é versionado; se alguém preencher com valor real, vaza."""
    texto = (RAIZ / modelo).read_text()
    assert texto.strip(), f"{modelo} está vazio"
    # Toda linha de valor precisa ser comentário, placeholder ou vazia.
    for numero, linha in enumerate(texto.splitlines(), 1):
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or "=" not in limpa:
            continue
        valor = limpa.split("=", 1)[1].strip().strip("'\"")
        if not valor:
            continue
        marcadores = ("TROCAR", "COLE", "...", "senha", "usuario", "local",
                      "gere", "INFO", "postgresql://usuario")
        assert any(m in valor for m in marcadores), (
            f"{modelo}:{numero} parece conter valor real: {limpa}")
