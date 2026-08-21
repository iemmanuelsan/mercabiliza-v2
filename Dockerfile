# Imagem única, portável entre Render, Railway e Fly.io.
#
# Por que Docker em vez do buildpack automático da plataforma: este app precisa
# de um pacote de SISTEMA (fonts-dejavu-core, para os acentos nos PDFs). O
# buildpack do Render/Railway instala só dependências Python — a fonte não
# entraria, e os PDFs sairiam sem acento. Com Dockerfile o ambiente é o mesmo
# em qualquer plataforma e igual ao que você testa localmente.

FROM python:3.12-slim-bookworm

# --- Pacotes de sistema -------------------------------------------------- #
# fonts-dejavu-core : acentuação e símbolos nos PDFs (ReportLab e fpdf2)
# ca-certificates   : TLS nas chamadas às APIs públicas
# curl              : usado pelo HEALTHCHECK
# --no-install-recommends mantém a imagem pequena; a limpeza do apt na mesma
# camada evita carregar o cache no layer final.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MERCABILIZA_AMBIENTE=producao

WORKDIR /app

# --- Dependências antes do código ---------------------------------------- #
# Camada separada: mudar uma linha de código não reinstala tudo de novo.
#
# requirements-pg.txt (driver do Postgres) é instalado aqui e NÃO no
# requirements.txt: esta imagem roda onde existe Postgres; o Streamlit
# Community Cloud, que lê só o requirements.txt, não usa banco e não deve
# carregar o risco de uma dependência que nem chama. Ver requirements-pg.txt.
COPY requirements.txt requirements-pg.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-pg.txt

# --- Código -------------------------------------------------------------- #
COPY app.py ./
COPY src/ ./src/
COPY templates/ ./templates/
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/

# --- Usuário sem privilégio ---------------------------------------------- #
# Container rodando como root é escalada de privilégio de graça se houver
# qualquer RCE. O diretório data/ precisa ser gravável pelo app (SQLite local
# quando não há DATABASE_URL).
RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

# A plataforma injeta $PORT. O default 8501 serve para rodar local.
ENV PORT=8501
EXPOSE 8501

# --- Healthcheck --------------------------------------------------------- #
# O Streamlit expõe /_stcore/health. Sem isto a plataforma considera o
# container saudável só por estar de pé, mesmo travado.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/_stcore/health" || exit 1

# --- Inicialização ------------------------------------------------------- #
# address=0.0.0.0 é obrigatório: o default do Streamlit escuta em localhost e
# a plataforma não conseguiria alcançar o processo.
# headless=true evita a tentativa de abrir navegador e o prompt de e-mail.
# Forma shell (sem JSON) para o ${PORT} ser expandido em tempo de execução.
CMD streamlit run app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableXsrfProtection=true \
    --browser.gatherUsageStats=false
