# Deploy, infraestrutura e segurança

Guia operacional do app Mercabiliza: onde hospedar, como tirar o repositório do
público sem deixar rastro, e como gerenciar segredos sem nunca colocá-los no Git.

Tudo aqui é copiável e colável. Onde houver decisão a tomar, o trade-off está
explicado — não é "faça assim porque sim".

---

## 0. Antes de tudo: o problema que repositório privado NÃO resolve

Vale começar por isto porque é o ponto que mais gera falsa sensação de segurança.

Tornar o repositório privado protege **o código**. Não protege **o app**.

O app publicado tem uma URL pública. A aba CRM lista nome, CNPJ, e-mail e
telefone de todos os leads consultados; a aba de documentos gera contratos com
CPF, RG e endereço de pessoas físicas. Antes desta entrega, **qualquer pessoa com
o link via tudo isso** — e link de app vaza por print em grupo de WhatsApp,
histórico de navegador e compartilhamento interno.

Isso é dado pessoal sob a LGPD (Lei 13.709/2018). O art. 46 exige medidas de
segurança aptas a proteger o dado de acesso não autorizado. Uma URL sem senha
não é isso.

Por isso o pacote inclui um **portão de autenticação** (`src/ui/auth.py`), que
roda antes de qualquer renderização em `app.py`:

```python
def main() -> None:
    if not exigir_login():
        st.stop()
    ...
```

São dois controles independentes, e você precisa dos dois:

| Controle | Protege | Contra |
|---|---|---|
| Repositório privado | o código-fonte | quem quer copiar/estudar a lógica |
| Gate de autenticação | os dados dos clientes | quem tem a URL |

---

## 1. Qual plataforma usar

### Comparativo

| | **Render** | **Railway** | **Fly.io** | **Streamlit Cloud** | **Vercel** |
|---|---|---|---|---|---|
| **Serve Streamlit?** | Sim | Sim | Sim | Sim (é o nativo) | **Não** |
| **Grátis para começar** | Sim, 512 MB / 0,1 CPU (hiberna se ficar ocioso) | Trial de 30 dias com US$ 5 de crédito, depois US$ 1/mês | Não há mais tier grátis para conta nova | Sim, ilimitado | — |
| **Menor plano pago** | Starter US$ 7/mês (512 MB, 0,5 CPU) | Hobby US$ 5/mês com US$ 5 de crédito incluso | Pay-as-you-go: ~US$ 3,32/mês (512 MB) | — | — |
| **Plano confortável** | Standard US$ 25/mês (2 GB, 1 CPU) | Uso medido: ~US$ 5–6/mês para 512 MB rodando 24/7 | ~US$ 5,92/mês (1 GB) | — | — |
| **Postgres gerenciado** | Grátis **expira em 30 dias**; Basic-256mb US$ 6/mês | Add-on por uso, ~US$ 2–5/mês nesse porte | Managed Postgres à parte | Não tem | Não tem |
| **Disco persistente** | US$ 0,25/GB/mês | US$ 0,15–0,20/GB/mês equivalente | US$ 0,15/GB/mês | Não tem (efêmero) | — |
| **CD por push no Git** | Sim, nativo | Sim, nativo | Via GitHub Actions (`flyctl deploy`) | Sim, nativo | Sim |
| **Repositório privado** | Sim | Sim | Sim | Sim (precisa dar permissão de admin ao app do GitHub) | Sim |
| **Docker** | Sim | Sim | Sim (é o modelo dele) | Não | Não |
| **Infra como código** | `render.yaml` (já no repo) | `railway.toml` | `fly.toml` | — | — |
| **Região no Brasil** | Não (mais perto: Oregon/Ohio) | Não | **Sim — GRU (São Paulo)** | Não (só EUA) | Sim (GRU) |

**Vercel está fora, e não é questão de preferência.** A Vercel roda funções
serverless: cada requisição sobe, responde e morre. O Streamlit é o oposto — um
servidor de processo longo que mantém uma conexão WebSocket aberta com o
navegador para cada sessão, e guarda `st.session_state` na memória desse
processo. Não há como encaixar um no outro. O mesmo vale para Netlify e Cloudflare
Pages. Se alguém insistir, a resposta curta é: *o Streamlit precisa de um servidor
que fique de pé, não de uma função*.

### Recomendação

**Comece no Render.** Motivos, em ordem de peso:

1. **Docker de primeira classe.** O app precisa de um pacote de *sistema*
   (`fonts-dejavu-core`) para os acentos saírem nos PDFs. Buildpack automático
   instala só dependência Python — sem Docker, os contratos sairiam com
   "JUNDIAI" no lugar de "Jundiaí". O `Dockerfile` já está no repositório.
2. **Postgres gerenciado no mesmo painel**, com `DATABASE_URL` injetada
   automaticamente. Sem isso, a base de leads é apagada a cada deploy.
3. **`render.yaml` já pronto** — cria serviço e banco de uma vez, e a
   configuração fica versionada.
4. Preço previsível: US$ 7 + US$ 6 = **US$ 13/mês** (~R$ 70) para app e banco de
   verdade. Sem surpresa no fim do mês.

**Aviso honesto sobre o plano grátis do Render:** 512 MB é apertado para
Streamlit + pandas + ReportLab juntos. Dá para validar o deploy nele, mas se
aparecer "Out of memory" ou o container reiniciar sozinho, é isso — suba para
Starter, e para Standard se persistir. O plano grátis também **hiberna após 15
minutos sem acesso**, e o primeiro acesso depois disso demora ~50 segundos.
Para mostrar o app a um cliente, isso é ruim.

**Quando escolher Railway em vez do Render:** se você quiser a melhor
experiência de uso e não se importar com cobrança por uso em vez de valor fixo.
O painel é mais agradável, o deploy é mais rápido e o custo real fica parecido
(~US$ 8–10/mês com app e banco). O contra é que a fatura varia com o uso.

**Quando escolher Fly.io:** só se a **latência** virar problema. É a única das
três com região em São Paulo (`gru`). Para um app interno usado por duas ou três
pessoas, os ~120 ms a mais do Oregon não se notam. Se um dia o app for para a
mão de clientes, aí vale.

**Quando ficar no Streamlit Community Cloud:** se o orçamento for zero e a base
de leads puder viver num Google Sheets ou num Postgres externo grátis (Neon,
Supabase). É grátis de verdade, aceita repositório privado e faz CD por push. Os
limites reais: o disco é **efêmero** (SQLite some a cada redeploy), não roda
Docker (você depende do `packages.txt`, que já está no repo com a fonte) e os
servidores ficam só nos EUA.

---

## 2. Tirar o repositório do público, com segurança

A ordem importa. Trocar para privado **antes** de auditar é o certo: fecha a
porta primeiro, investiga depois.

### 2.1 Tornar privado

Pelo site: **Settings → General → Danger Zone → Change repository visibility →
Make private**.

Pelo terminal, se você tem o [GitHub CLI](https://cli.github.com/):

```bash
gh repo edit iemmanuelsan/SEU-REPO --visibility private --accept-visibility-change-consequences
```

O que você perde ao fechar (e provavelmente não usa): GitHub Pages no plano
grátis, e os minutos ilimitados de Actions — em repo privado o plano Free dá
2.000 minutos/mês, mais que suficiente para o CI deste projeto.

> ⚠️ **Forks continuam existindo.** Se alguém tiver forkado o repo enquanto ele
> era público, o fork **não** fica privado junto. Confira em
> `https://github.com/iemmanuelsan/SEU-REPO/forks` — e nas cópias em cache do
> Google. É por isso que a auditoria da seção 2.3 é necessária mesmo depois de
> fechar: se um segredo esteve público, ele deve ser considerado comprometido,
> ponto. Fechar o repositório não desfaz o vazamento.

### 2.2 O `.gitignore` (já aplicado no repo)

```gitignore
# --- Segredos e credenciais (NUNCA versionar) ---
.streamlit/secrets.toml
.env
.env.*
*.pem
*.key
*.p12
*.pfx
credentials.json
client_secret*.json
service_account*.json
*serviceaccount*.json
.netrc
.pgpass
id_rsa
id_ed25519
id_*.pub

# Exceções: arquivos-MODELO, sem valor dentro, versionados de propósito.
# A negação precisa vir DEPOIS da regra que ignora.
!.env.example
!.streamlit/secrets.toml.example

# --- Dados de clientes / LGPD ---
# O CRM guarda CNPJ, e-mail, telefone e nomes de sócios: dado pessoal.
data/
*.db
*.db-wal
*.db-shm
*.sqlite
*.sqlite3

# --- Saídas geradas (contratos e fichas com dado de cliente dentro) ---
*.xlsx
*.xls
*.pdf
!docs/**/*.pdf
exports/
output/

# --- Python ---
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.coverage
.mypy_cache/
.ruff_cache/

# --- Editores e SO ---
.vscode/
.idea/
.DS_Store
```

Duas coisas que costumam passar batido e estão cobertas aqui:

- **`*.pdf` e `*.xlsx` ignorados.** Não é organização, é privacidade: os PDFs
  que o app gera são contratos com CPF e RG de cliente. Um `git add .` distraído
  commitaria um.
- **`data/` e `*.db` ignorados.** O SQLite do CRM *é* uma base de dados
  pessoais. Versionar é criar uma cópia permanente e imutável dela.

**Importante:** `.gitignore` só vale para arquivo **ainda não rastreado**. Se
algum já foi commitado, ignorar depois não faz nada. Verifique e remova do
índice (o arquivo continua no seu disco):

```bash
# O que está rastreado e não deveria estar?
git ls-files | grep -Ei '\.(env|db|sqlite3?|pdf|xlsx|pem|key)$|secrets\.toml|^data/'

# Remover do Git mantendo o arquivo local:
git rm --cached .env
git rm --cached -r data/
git commit -m "chore: remove do versionamento arquivos com dado sensível"
```

Isso tira o arquivo dos commits **futuros**. O histórico anterior continua com
ele — é o que a seção 2.4 resolve.

### 2.3 Auditar o histórico

Rode isto no repositório real. São três varreduras, da mais rápida à mais
completa.

**a) Varredura rápida, sem instalar nada:**

```bash
# Arquivos que em ALGUM momento existiram no histórico
git log --all --name-only --pretty=format: \
  | sort -u \
  | grep -Ei '\.(env|pem|key|p12|pfx)$|secrets|credential|service.?account|\.db$|\.sqlite'

# Padrões de credencial no conteúdo de todos os commits
git log -p --all -S'password' --pickaxe-regex
git grep -nIE '(api[_-]?key|secret|token|senha|password)\s*[:=]\s*.{8,}' $(git rev-list --all) \
  | grep -v '\.example' | head -50
```

**b) Ferramenta dedicada (recomendado — pega o que grep não pega):**

```bash
# gitleaks — reconhece ~150 formatos de credencial por assinatura
# macOS:   brew install gitleaks
# Linux:   veja https://github.com/gitleaks/gitleaks/releases
# Docker (não instala nada na máquina):
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest \
  detect --source=/repo --redact --verbose
```

```bash
# trufflehog — além de achar, VERIFICA se a credencial ainda está ativa
docker run --rm -v "$PWD:/repo" trufflesecurity/trufflehog:latest \
  git file:///repo --only-verified
```

Saída limpa (`no leaks found`) = pode pular a seção 2.4.

**c) Checagem de dado pessoal, específica deste projeto** — não é credencial,
mas é LGPD:

```bash
# CPF em texto (11 dígitos com ou sem máscara) em qualquer commit
git grep -nE '[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}' $(git rev-list --all) \
  | grep -vE 'tests?/|\.md:' | head -30
```

Ignore os acertos em `tests/` — os CPFs lá são gerados para o teste de validação,
não pertencem a ninguém.

> **Resultado da auditoria no código que você recebeu:** limpo. Zero
> credenciais, zero chaves privadas, zero tokens. O único acerto do grep é o
> texto `cookie_secret = "gere-com-python -c ..."` em `src/ui/auth.py`, que é
> instrução, não segredo. O único CNPJ no código é o da própria Mercabiliza —
> dado público de registro empresarial. **Portanto: nada a expurgar na base
> atual.** A seção seguinte fica documentada para o caso de a auditoria no seu
> histórico antigo encontrar algo.

### 2.4 Se a auditoria encontrar algo: expurgar de verdade

Três avisos antes dos comandos, porque essa operação erra feio quando feita com
pressa:

1. **Reescrever histórico não é a primeira providência — rotacionar é.** Assim
   que uma credencial esteve num repositório público, considere-a vazada. Bots
   varrem o GitHub em minutos. Revogue e gere outra **antes** de mexer no
   histórico. Se você só limpar o Git, a senha antiga continua válida no mundo.
2. **A reescrita muda o hash de todo commit.** Quem tiver clone vai precisar
   clonar de novo. Combine com a equipe antes.
3. **Faça backup primeiro.** Sempre.

```bash
# 0. BACKUP — clone espelho completo, guardado fora do diretório de trabalho
git clone --mirror https://github.com/iemmanuelsan/SEU-REPO backup-repo.git
```

**Opção A — `git-filter-repo`** (recomendada; é a que o próprio Git indica no
lugar do `filter-branch`):

```bash
pip install git-filter-repo

# Apagar um arquivo de TODO o histórico
git filter-repo --invert-paths --path .env --path .streamlit/secrets.toml

# Ou substituir apenas o valor, preservando o arquivo:
printf 'minha-senha-vazada==>***REMOVIDO***\n' > /tmp/trocas.txt
git filter-repo --replace-text /tmp/trocas.txt
```

O `filter-repo` remove o `origin` de propósito, como trava de segurança. Repor e
enviar:

```bash
git remote add origin https://github.com/iemmanuelsan/SEU-REPO.git
git push origin --force --all
git push origin --force --tags
```

**Opção B — BFG Repo-Cleaner** (mais simples se você só quer apagar arquivos por
nome; precisa de Java):

```bash
# https://rtyley.github.io/bfg-repo-cleaner/
java -jar bfg.jar --delete-files .env backup-repo.git
java -jar bfg.jar --replace-text senhas-a-remover.txt backup-repo.git

cd backup-repo.git
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

**Depois do push — o passo que quase todo mundo esquece:**

O GitHub guarda os commits antigos em cache e eles continuam acessíveis pela URL
direta do hash por um tempo. Abra um chamado no
[Suporte do GitHub](https://support.github.com/) pedindo a limpeza das
referências órfãs. E confira se algum fork ainda tem o commit.

---

## 3. Gerenciamento de segredos

### A regra

Segredo não entra em arquivo versionado. Nem em `config.py` com um "depois eu
tiro", nem em comentário, nem em notebook de teste. Ele mora **só** no painel da
plataforma, e o código lê do ambiente.

### Como este app faz

`src/ui/auth.py` lê as senhas em duas fontes, nesta ordem:

1. **Variável de ambiente** — `MERCABILIZA_SENHAS` (JSON) ou
   `MERCABILIZA_SENHA_GERAL`. É o caminho no Render, Railway e Fly.
2. **`st.secrets`** — é o caminho no Streamlit Community Cloud.

> **Pegadinha que custa uma tarde:** variável de ambiente com prefixo
> `STREAMLIT_` configura *opções do Streamlit* (`STREAMLIT_SERVER_PORT` e
> afins). Ela **não** popula `st.secrets`, e **não existe** um
> `STREAMLIT_SECRETS`. Fora do Streamlit Cloud, `st.secrets` só é preenchido por
> um arquivo `secrets.toml` de verdade dentro do container. É exatamente por
> isso que o gate lê variável de ambiente como fonte primária.

### Gerar as senhas

Não invente senha à mão — e não use a mesma de outro sistema:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

### Configurar

**Render / Railway / Fly** — painel de variáveis de ambiente:

```bash
MERCABILIZA_SENHAS={"luisfelipe":"COLE-A-SENHA-GERADA","iago":"COLE-A-OUTRA"}
MERCABILIZA_AMBIENTE=producao
MERCABILIZA_LOG_LEVEL=WARNING
# DATABASE_URL é injetada automaticamente ao vincular o Postgres.
```

Uma entrada por pessoa, e não uma senha só, por dois motivos práticos: o log
registra quem entrou, e desligar alguém não obriga a trocar a senha de todo mundo.

**Streamlit Community Cloud** — painel *Secrets* (Settings → Secrets):

```toml
[senhas]
luisfelipe = "COLE-A-SENHA-GERADA"
iago = "COLE-A-OUTRA"
```

**Local** — copie os modelos versionados e preencha:

```bash
cp .env.example .env
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Os dois `.example` são versionados de propósito: documentam **quais** variáveis
existem sem revelar **nenhum** valor. Quem clonar o repo sabe o que configurar.

### Quando a senha compartilhada não bastar

Senha de equipe é o mínimo aceitável, não o ideal. Ela não prova quem fez o quê
— e sob LGPD, tratando dado pessoal em escala, trilha de auditoria é exigível.

O Streamlit tem login OIDC nativo (`st.login` / `st.user`). Se a Mercabiliza já
usa Google Workspace ou Microsoft 365, dá para plugar em uma tarde e ganhar:
conta individual, MFA herdado do provedor, revogação imediata no desligamento e
log de acesso. O formato da configuração está comentado em
`.streamlit/secrets.toml.example`.

### Rotação

Troque as senhas quando alguém sair da equipe, ao suspeitar de vazamento e, por
higiene, a cada seis meses. No Render/Railway a troca é editar a variável e
redeployar — sem tocar no código.

---

## 4. Deploy no Render, passo a passo

### 4.1 Com o `render.yaml` (recomendado)

O arquivo já está no repositório. Ele declara o serviço web em Docker e o
Postgres, já vinculados.

1. Confirme que os arquivos estão no GitHub:

```bash
git add Dockerfile .dockerignore render.yaml .env.example \
        .streamlit/secrets.toml.example .gitignore requirements.txt
git commit -m "infra: Dockerfile, blueprint do Render e modelos de configuração"
git push origin main
```

2. No Render: **New → Blueprint → Connect a repository →** escolha o repo (ele
   aparece mesmo privado, depois de você autorizar o app do Render no GitHub).
3. O Render lê o `render.yaml` e mostra o que vai criar: o serviço `mercabiliza`
   e o banco `mercabiliza-db`. Confirme.
4. Ele vai pedir o valor de `MERCABILIZA_SENHAS` — é a variável marcada com
   `sync: false`, que existe justamente para não ser versionada. Cole o JSON com
   as senhas geradas.
5. **Create**. O primeiro build leva de 5 a 8 minutos (compila a imagem Docker).

### 4.2 Manualmente, sem blueprint

Se preferir clicar em vez de usar IaC:

1. **New → PostgreSQL**: nome `mercabiliza-db`, plano Basic-256mb, região
   Oregon. Copie a *Internal Database URL*.
2. **New → Web Service** → conecte o repositório.
   - Runtime: **Docker** (o Render detecta o `Dockerfile` sozinho)
   - Branch: `main`
   - Health Check Path: `/_stcore/health`
   - Plan: Starter
   - Region: **a mesma do banco** — senão cada consulta atravessa a internet
     pública.
3. Em **Environment**, adicione:

| Chave | Valor |
|---|---|
| `DATABASE_URL` | a *Internal Database URL* copiada no passo 1 |
| `MERCABILIZA_SENHAS` | `{"luisfelipe":"...","iago":"..."}` |
| `MERCABILIZA_AMBIENTE` | `producao` |
| `MERCABILIZA_LOG_LEVEL` | `WARNING` |

4. **Create Web Service**.

### 4.3 Migrar os leads que já estão no SQLite

Se você já tem base no SQLite local, o script de migração está no repositório:

```bash
DATABASE_URL='postgresql://...' python scripts/migrar_crm.py
```

Use a *External Database URL* do Render para rodar da sua máquina (a *Internal*
só funciona de dentro da rede deles).

### 4.4 Verificar que subiu certo

```bash
# 1. Health check responde
curl -fsS https://mercabiliza.onrender.com/_stcore/health
# esperado: ok

# 2. A app está protegida — abra numa janela anônima.
#    Você DEVE ver o formulário de login e NENHUMA aba.
```

O teste 2 é o que importa. Se as abas aparecerem sem senha, a variável
`MERCABILIZA_SENHAS` não chegou ao container — confira se o JSON está válido
(aspas duplas, sem quebra de linha) e redeploye.

Na aba CRM, o rodapé mostra o backend em uso. Tem de dizer **"PostgreSQL
(persistente)"**. Se disser "SQLite (efêmero em PaaS)", o `DATABASE_URL` não
chegou, e a base vai sumir no próximo deploy.

### 4.5 Deploy contínuo

Com `autoDeploy: true` (já no `render.yaml`), cada push na `main` dispara build e
deploy. O Render mantém a versão anterior no ar até a nova passar no health
check, então um build quebrado não derruba o app.

Para separar ambientes, o padrão que funciona bem:

```
main      → produção   (deploy automático)
develop   → homologação (outro serviço no Render, banco separado)
```

O CI do GitHub Actions (`.github/workflows/ci.yml`) já roda os testes e o lint a
cada push. Para impedir que código quebrado chegue à `main`, ative a proteção de
branch: **Settings → Branches → Add rule → Require status checks to pass**.

### 4.6 Domínio próprio e HTTPS

1. Render → seu serviço → **Settings → Custom Domains → Add**.
2. Digite `app.mercabiliza.com.br`.
3. No painel do seu DNS, crie o registro que o Render mostrar:

```
Tipo   Nome   Valor
CNAME  app    mercabiliza.onrender.com
```

4. O certificado TLS (Let's Encrypt) é emitido e renovado automaticamente em
   poucos minutos. Não há nada a configurar e não há custo.

---

## 5. Alternativa: Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway add --database postgres     # injeta DATABASE_URL automaticamente

railway variables --set 'MERCABILIZA_SENHAS={"luisfelipe":"...","iago":"..."}' \
                  --set 'MERCABILIZA_AMBIENTE=producao'

railway up
railway domain                       # gera a URL pública com HTTPS
```

O Railway detecta o `Dockerfile` e o usa. Para CD por push, conecte o
repositório em **Settings → Source** no painel.

Estimativa de custo para este app rodando 24/7, pelas tarifas atuais
(memória US$ 0,00000386/GB/s):

```
0,5 GB × 2.592.000 s/mês × US$ 0,00000386 ≈ US$ 5,00/mês (app)
+ CPU quase ocioso                        ≈ US$ 0,40/mês
+ Postgres pequeno                        ≈ US$ 2,50/mês
                                          ─────────────────
                                          ≈ US$ 8/mês
```

O plano Hobby (US$ 5/mês) já inclui US$ 5 de crédito, então a conta real fica em
torno de US$ 8–10/mês. Faixa parecida com o Render; a diferença é fixo × variável.

---

## 6. Checklist antes de publicar

Segurança:

- [ ] Repositório privado no GitHub
- [ ] Forks existentes verificados
- [ ] `gitleaks` ou `trufflehog` rodado no histórico, sem achados
- [ ] Nenhum `.env`, `secrets.toml` ou `*.db` rastreado (`git ls-files | grep ...`)
- [ ] `MERCABILIZA_SENHAS` configurada com senhas geradas, uma por pessoa
- [ ] Janela anônima confirma: aparece o login, **não** aparecem as abas
- [ ] HTTPS ativo (automático nas três plataformas)
- [ ] `showErrorDetails = false` no `.streamlit/config.toml` (já está) — sem
      stack trace na cara do usuário

Funcionamento:

- [ ] `/_stcore/health` responde `ok`
- [ ] A aba CRM mostra "PostgreSQL (persistente)"
- [ ] Um PDF gerado sai **com acentos** (valida a fonte no container)
- [ ] Um deploy de teste não apagou a base de leads

LGPD, enquanto o app trata dado de cliente:

- [ ] Base legal definida para o tratamento (execução de contrato, art. 7º, V)
- [ ] Prazo de retenção dos leads não convertidos definido
- [ ] Caminho para atender pedido de exclusão (`remover(cnpj)` já existe no
      repositório)
- [ ] Backup do Postgres ativado (Render faz diário nos planos pagos)

---

## 7. Custo mensal, resumido

| Cenário | Custo | Serve para |
|---|---|---|
| Streamlit Cloud + Postgres externo grátis (Neon/Supabase) | **US$ 0** | validar a ideia; aceitar servidor nos EUA e limites do tier grátis |
| Render Free + Postgres Basic | **US$ 6** | uso interno leve; o app hiberna em 15 min de ociosidade |
| **Render Starter + Postgres Basic** | **US$ 13** (~R$ 70) | **recomendado — uso profissional diário** |
| Railway Hobby + Postgres | **~US$ 8–10** | mesma coisa, com fatura variável e painel melhor |
| Render Standard + Postgres | **US$ 31** | quando 512 MB der "out of memory" |

---

## 8. Arquivos de infraestrutura no repositório

| Arquivo | Para que serve |
|---|---|
| `Dockerfile` | Imagem única, portável entre Render, Railway e Fly. Inclui `fonts-dejavu-core` (acentos nos PDFs), usuário sem privilégio e healthcheck. |
| `.dockerignore` | Impede que `.env`, banco e PDFs de cliente entrem numa camada da imagem — camada é imutável, o que entra fica para sempre. |
| `render.yaml` | Blueprint: cria serviço e Postgres já vinculados. Segredos com `sync: false`. |
| `requirements.txt` | Dependências do app. **É o único arquivo que o Streamlit Cloud lê.** |
| `requirements-pg.txt` | Driver do Postgres, separado de propósito — instalado só pelo Dockerfile. Ver seção 9. |
| `.env.example` | Documenta quais variáveis existem, sem nenhum valor. |
| `.streamlit/secrets.toml.example` | O mesmo, no formato do Streamlit Cloud. |
| `.gitignore` | Bloqueia segredos, banco e documentos gerados. |
| `packages.txt` | Pacotes de sistema no Streamlit Cloud (que não roda Docker). |
| `.python-version` | Fixa o Python em 3.12 **para ferramentas locais** (pyenv, uv) e para o CI. O Streamlit Cloud **não lê este arquivo** — lá a versão é escolhida em *Advanced settings* no momento do deploy. |
| `.github/workflows/ci.yml` | Testes e lint a cada push. |
| `scripts/migrar_crm.py` | Move os leads do SQLite para o Postgres. |

Não há `Procfile` nem `runtime.txt` de propósito. São artefatos do modelo
Heroku: o `Procfile` declara o comando de inicialização e o `runtime.txt` a
versão do Python. Com Dockerfile, ambos ficam redundantes — o `CMD` já é o
comando, e a imagem base já fixa o Python. Manter os dois seria criar uma
segunda fonte de verdade para a mesma coisa, que é como se descobre, seis meses
depois, que produção roda uma versão de Python diferente da que está escrita no
arquivo.

Se um dia você abandonar o Docker e usar o buildpack nativo do Render, aí sim:

```procfile
web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
```

---

## 9. Continuar no Streamlit Cloud por enquanto

**Sim, o app continua rodando normalmente.** Nada aqui é obrigatório: os
arquivos de infra ficam dormindo no repositório até você decidir migrar.

O que o Streamlit Community Cloud faz com cada arquivo novo:

| Arquivo | O que o Cloud faz |
|---|---|
| `Dockerfile`, `.dockerignore` | **Ignora.** O Cloud não roda Docker. |
| `render.yaml` | **Ignora.** É formato do Render. |
| `requirements-pg.txt` | **Ignora.** Só o `requirements.txt` é lido. |
| `.env.example`, `secrets.toml.example` | **Ignora.** São só documentação. |
| `.python-version` | **Ignora.** A versão é escolhida em *Advanced settings*. |
| `requirements.txt` | Lê — e ele está igual ao que já funcionava. |
| `packages.txt` | Lê — instala o `fonts-dejavu-core`. |
| `src/ui/auth.py` | **Roda.** Ver abaixo. |

### O único arquivo que muda comportamento: o gate

Sem nenhum segredo configurado, o gate fica **aberto** e mostra um aviso. O app
funciona igual a antes — mas continua exposto.

Para ligar de verdade, no painel do app: **⋮ → Settings → Secrets**, e cole:

```toml
[senhas]
luisfelipe = "COLE-A-SENHA-GERADA"
iago = "COLE-A-OUTRA"
```

Salvar reinicia o app sozinho, em segundos. Não precisa redeployar.

### O que muda quando você migrar

Nada no código. A migração é: preencher `DATABASE_URL` (o Render injeta ao
vincular o Postgres) e rodar `scripts/migrar_crm.py` para levar os leads. As
telas não são tocadas — é para isso que existe a interface `LeadRepository`.

### Por que o driver do Postgres não está no `requirements.txt`

Este é o cuidado que evita repetir o `ModuleNotFoundError` que já te pegou uma
vez.

O Streamlit Cloud sobe a versão do Python sem aviso. Quando um pacote da lista
não tem wheel para a versão nova, o pip tenta compilar do fonte, falha, e
**aborta a lista inteira** — os pacotes que vêm *depois* dele simplesmente não
são instalados. O app cai reclamando de uma dependência que está no arquivo.

O driver do Postgres (`psycopg`) seria exatamente esse tipo de risco: um pacote
com extensão compilada, num deploy que **nem usa Postgres**. Por isso ele mora
em `requirements-pg.txt`, instalado só pelo Dockerfile. O código já colabora:
`repository_pg.py` só é importado quando `DATABASE_URL` existe, e o `psycopg`
só é importado dentro da função de conexão — sem a variável, nada disso é
tocado. Há teste garantindo que continue assim
(`tests/test_infra.py::test_app_nao_importa_psycopg_sem_database_url`).

### Ressalvas de continuar no Cloud

- **A base de leads é apagada** a cada reboot ou redeploy (disco efêmero, sem
  `DATABASE_URL`). Se você já usa o CRM para valer, exporte antes de qualquer
  mexida — ou migre o banco primeiro e o resto depois.
- **A versão do Python não pode ser alterada depois do deploy.** Para trocar, é
  deletar o app e recriar escolhendo a versão em *Advanced settings* (os
  segredos precisam ser digitados de novo).
- Repositório privado funciona, mas você precisa dar permissão de admin ao app
  do GitHub quando ele pedir.

---

## Fontes

- [Render — Pricing](https://render.com/pricing)
- [Railway — Pricing](https://railway.com/pricing)
- [Fly.io — Resource Pricing](https://fly.io/docs/about/pricing/)
- [Streamlit — App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Streamlit — Upgrade your app's Python version](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python)
- [gitleaks](https://github.com/gitleaks/gitleaks)
- [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/)
