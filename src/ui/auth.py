"""Portão de autenticação.

## Por que isto existe

O app expõe a aba CRM com nome, CNPJ, e-mail e telefone de todos os leads
consultados, e gera contratos com CPF e RG de pessoas físicas. Sem gate, tudo
isso fica acessível a **qualquer pessoa que tenha a URL** — e URLs de app
vazam por print, histórico de navegador e link compartilhado.

Repositório privado não protege nada disso: o que é público é o *app*, não o
código. São dois controles independentes.

## Como funciona

Senhas vêm de duas fontes, nesta ordem:

1. **Variável de ambiente** ``MERCABILIZA_SENHAS`` (JSON) ou
   ``MERCABILIZA_SENHA_GERAL`` — é o caminho em Render, Railway e Fly, que só
   oferecem variáveis de ambiente.
2. **``st.secrets``** — é o caminho no Streamlit Community Cloud, cujo painel
   *Secrets* grava um ``secrets.toml``.

Cuidado com uma pegadinha: variável de ambiente com prefixo ``STREAMLIT_``
configura *opções do Streamlit*, **não** popula ``st.secrets``. Não existe um
``STREAMLIT_SECRETS``. Por isso a fonte 1 existe.

Nunca no código, nunca no Git — em nenhum dos dois casos.

A comparação usa :func:`hmac.compare_digest` em vez de ``==`` para não vazar
informação por tempo de resposta. É o padrão documentado pelo Streamlit.

## Limites conhecidos — leia antes de confiar

* **Senha compartilhada não identifica quem fez o quê.** Para trilha de
  auditoria (exigível sob LGPD quando há tratamento de dado pessoal em escala),
  o caminho é OIDC — ver :func:`instrucoes_oidc`.
* O gate protege a *interface*. Se a plataforma expuser a porta do Streamlit
  sem TLS, o tráfego vai em claro. Todas as plataformas recomendadas no
  DEPLOY.md dão HTTPS por padrão.
* Não há rate limit por IP aqui. Um atacante com a URL pode tentar senhas em
  volume. Use senha longa (>16 caracteres, gerada) e, se o app ficar exposto
  na internet aberta, coloque atrás do Cloudflare Access ou equivalente.
"""

from __future__ import annotations

import hmac
import json
import logging
import os

import streamlit as st

logger = logging.getLogger(__name__)

K_AUTENTICADO = "auth_ok"
K_USUARIO = "auth_usuario"
K_TENTATIVAS = "auth_tentativas"

MAX_TENTATIVAS = 5

ENV_SENHAS = "MERCABILIZA_SENHAS"
ENV_SENHA_GERAL = "MERCABILIZA_SENHA_GERAL"

_AVISO_SEM_SENHA = """
### 🔓 Autenticação não configurada

Este app trata **dados pessoais de clientes** (CNPJ, CPF, nomes, endereços) e
está sem senha. Qualquer pessoa com este link vê a base de leads inteira.

**Em Render / Railway / Fly** — painel de variáveis de ambiente:

```bash
MERCABILIZA_SENHAS='{"luisfelipe":"senha-longa-1","iago":"senha-longa-2"}'
# ou, para senha única da equipe:
MERCABILIZA_SENHA_GERAL='uma-senha-longa-e-aleatoria'
```

**No Streamlit Community Cloud** — painel *Secrets*:

```toml
[senhas]
luisfelipe = "senha-longa-1"
iago = "senha-longa-2"
```

Gere as senhas assim (não invente à mão):

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Enquanto não houver segredo definido, o app **continua funcionando** para não
travar o desenvolvimento local — mas não publique assim.
"""


def _do_ambiente() -> dict[str, str]:
    """Senhas por variável de ambiente (Render, Railway, Fly, Docker local)."""
    bruto = os.getenv(ENV_SENHAS, "").strip()
    if bruto:
        try:
            dados = json.loads(bruto)
            if isinstance(dados, dict) and dados:
                return {str(u).strip().lower(): str(s) for u, s in dados.items()}
            logger.error("%s não é um objeto JSON com pares usuário/senha.",
                         ENV_SENHAS)
        except json.JSONDecodeError:
            # Falha explícita: senha malformada não pode virar "gate aberto"
            # silencioso — seria uma brecha causada por um erro de digitação.
            logger.error("%s não é JSON válido. Formato esperado: "
                         '{"usuario":"senha"}', ENV_SENHAS)

    geral = os.getenv(ENV_SENHA_GERAL, "").strip()
    if geral:
        return {"equipe": geral}
    return {}


def _dos_secrets() -> dict[str, str]:
    """Senhas via ``st.secrets`` (Streamlit Community Cloud e local)."""
    try:
        if "senhas" in st.secrets:
            return {str(u).strip().lower(): str(s)
                    for u, s in st.secrets["senhas"].items()}
        if "senha_geral" in st.secrets:
            return {"equipe": str(st.secrets["senha_geral"])}
    except Exception:
        # st.secrets levanta se não houver secrets.toml algum — situação normal
        # em produção fora do Streamlit Cloud, onde a fonte é o ambiente.
        logger.debug("Sem secrets.toml disponível.")
    return {}


def _senhas_configuradas() -> dict[str, str]:
    """Lê as senhas configuradas. Dicionário vazio = gate desligado.

    Ambiente tem prioridade sobre ``secrets.toml``: assim um arquivo local
    esquecido na máquina não sobrescreve a senha de produção.
    """
    return _do_ambiente() or _dos_secrets()


def _validar(usuario: str, senha: str, configuradas: dict[str, str]) -> bool:
    """Compara em tempo constante.

    ``hmac.compare_digest`` em vez de ``==``: a comparação ingênua para no
    primeiro byte diferente, e a diferença de tempo permite descobrir a senha
    caractere por caractere.
    """
    esperada = configuradas.get(usuario)
    if esperada is None:
        # Compara contra um valor descartável para o tempo de resposta não
        # revelar se o usuário existe.
        hmac.compare_digest(senha.encode(), b"usuario-inexistente")
        return False
    return hmac.compare_digest(senha.encode(), esperada.encode())


def _formulario(configuradas: dict[str, str]) -> None:
    st.title("🛒 Mercabiliza")
    st.caption("Inteligência tributária e onboarding contábil")

    usuario_unico = list(configuradas) == ["equipe"]

    with st.form("form_login"):
        usuario = ("equipe" if usuario_unico
                   else st.text_input("Usuário").strip().lower())
        senha = st.text_input("Senha", type="password")
        enviado = st.form_submit_button("Entrar", type="primary",
                                        width="stretch")

    if not enviado:
        return

    tentativas = st.session_state.get(K_TENTATIVAS, 0)
    if tentativas >= MAX_TENTATIVAS:
        st.error("Muitas tentativas. Recarregue a página para tentar de novo.")
        return

    if _validar(usuario, senha, configuradas):
        st.session_state[K_AUTENTICADO] = True
        st.session_state[K_USUARIO] = usuario
        st.session_state[K_TENTATIVAS] = 0
        logger.info("Login bem-sucedido: %s", usuario)
        st.rerun()
    else:
        st.session_state[K_TENTATIVAS] = tentativas + 1
        restantes = MAX_TENTATIVAS - st.session_state[K_TENTATIVAS]
        logger.warning("Login falhou para '%s' (%d tentativas)",
                       usuario or "(vazio)", st.session_state[K_TENTATIVAS])
        st.error(f"Usuário ou senha inválidos. "
                 f"{max(0, restantes)} tentativa(s) restante(s).")


def exigir_login() -> bool:
    """Bloqueia o app até o login. ``True`` = pode seguir.

    Chame no início de ``main()``, antes de qualquer render::

        if not exigir_login():
            st.stop()

    Sem segredo configurado o gate fica **aberto** com aviso na tela: travar o
    app por falta de config atrapalharia o desenvolvimento local, e o aviso
    garante que a ausência não passe em branco antes de publicar.
    """
    configuradas = _senhas_configuradas()

    if not configuradas:
        with st.sidebar:
            st.warning("⚠️ Sem autenticação — não publique assim.", icon="🔓")
        with st.expander("🔓 Autenticação não configurada", expanded=False):
            st.markdown(_AVISO_SEM_SENHA)
        return True

    if st.session_state.get(K_AUTENTICADO):
        return True

    _formulario(configuradas)
    return False


def usuario_atual() -> str:
    return st.session_state.get(K_USUARIO, "")


def botao_sair() -> None:
    """Botão de logout na sidebar. Só aparece se o gate estiver ativo."""
    if not st.session_state.get(K_AUTENTICADO):
        return
    with st.sidebar:
        st.caption(f"Conectado como **{usuario_atual()}**")
        if st.button("Sair", width="stretch"):
            for chave in (K_AUTENTICADO, K_USUARIO):
                st.session_state.pop(chave, None)
            st.rerun()


def instrucoes_oidc() -> str:
    """Caminho para autenticação de verdade, quando a senha não bastar.

    O Streamlit tem login OIDC nativo (``st.login`` / ``st.user``). Com Google
    Workspace ou Microsoft 365 — que a Mercabiliza provavelmente já usa — isso
    dá: cada pessoa com a própria conta, MFA herdado do provedor, revogação
    imediata ao desligar alguém, e log de quem acessou o quê.
    """
    return """
    # .streamlit/secrets.toml
    [auth]
    redirect_uri = "https://seu-app.onrender.com/oauth2callback"
    cookie_secret = "gere-com-python -c 'import secrets;print(secrets.token_hex(32))'"

    [auth.google]
    client_id = "..."
    client_secret = "..."
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
    """
