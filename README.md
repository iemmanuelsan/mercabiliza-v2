# 🛒 Mercabiliza — Inteligência Tributária & Onboarding Contábil

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.61-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/tests-206%20passing-success)](tests/)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff)](https://docs.astral.sh/ruff/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Plataforma de **prospecção, diagnóstico tributário e onboarding contábil** para
minimercados autônomos. A partir de um CNPJ, monta o dossiê completo, identifica
oportunidades de economia (PIS/COFINS monofásico, Fator R), simula regimes,
estima o custo do desenquadramento do MEI e emite os documentos de fechamento —
ficha cadastral, contrato em papel timbrado e formulário de abertura.

> **Escopo:** ferramenta de apoio gerencial e comercial. Não emite certidões, não
> substitui a apuração no PGDAS-D, e os documentos jurídicos exigem revisão por
> advogado antes do uso. Todos os valores são estimativas.

---

## ✨ Módulos

| Aba | O que faz |
|---|---|
| 🔍 **Dossiê individual** | Consolida 3 bases públicas de CNPJ em paralelo + IBGE. Cartão CNPJ, QSA, diagnóstico tributário por CNAE, endereço com Maps e WhatsApp direto. |
| ⚔️ **Comparador de regimes** | Simples Nacional pelas tabelas progressivas reais da LC 123/2006 × Lucro Presumido detalhado tributo a tributo. |
| 📊 **Análise em lote** | Upload de planilha, validação e deduplicação de CNPJs, processamento concorrente com progresso real e relatório de falhas. |
| 🛠️ **Calculadora MEI** | Estima o custo do desenquadramento retroativo, com Selic ao vivo do BACEN. |
| 📝 **Ficha & contrato** | Ficha cadastral, contrato em papel timbrado e formulário DOCX de abertura/desenquadramento. Três modalidades: PJ, MEI e PF. |
| 🗃️ **CRM & leads** | Base de prospects com filtros, gráfico por UF, exportação e remoção individual (LGPD). |

---

## 📝 Módulo de documentos

Três modalidades, cada uma com um fluxo próprio:

| Modalidade | Entrada | Saídas |
|---|---|---|
| **PJ — Contrato regular** | consulta de CNPJ | ficha + contrato + form. de alteração |
| **MEI — Desenquadramento** | consulta de CNPJ | ficha + contrato + form. de desenquadramento |
| **PF — Abertura de empresa** | CPF + CEP (manual) | ficha + contrato + form. de abertura |

### Papel timbrado

O contrato e a ficha saem sobre a arte oficial (`assets/timbrado/`), desenhada
como fundo de página inteira pelo ReportLab. As margens vêm da própria arte
(34 mm no topo) para o texto não invadir o logo. Cascata de fallback:

```
assets/timbrado/mercabiliza_a4.png  →  assets/logo.png + dados  →  faixa da marca
```

O documento nunca deixa de ser gerado por falta de imagem.

### Preenchimento híbrido no DOCX

O formulário de abertura distingue visualmente três situações — é o que evita
que o cliente releia 89 campos para achar as 29 decisões que só ele pode tomar:

| Marca | Significado |
|---|---|
| **negrito** | preenchido pelo sistema (API de CNPJ, CEP ou cadastro). Só conferir. |
| `[ PREENCHER AQUI ]` em vermelho | depende de decisão do cliente: opções de razão social, capital social, distribuição de quotas, previsão de faturamento. |
| linha em branco | dado que o cliente tem e o sistema não conseguiu obter. |

### Destaque dos dados identificadores

Seguindo o contrato em uso, o que **identifica a parte** sai em negrito —
razão social, CNPJ, RG, CPF, inscrição estadual, endereço e CEP — enquanto a
prosa jurídica que liga esses dados fica em peso normal. Não é estética: é o
que faz o conferente achar os campos críticos de relance, no momento em que
erro de digitação precisa ser pego.

O marcador é `**` (via `core.pessoas.n()`), entendido tanto pelo gerador de PDF
quanto pelo `st.markdown` do preview — a tela mostra o mesmo que o papel.

> ⚠️ Fonte TTF customizada exige `pdfmetrics.registerFontFamily()`, senão o
> ReportLab **ignora silenciosamente** a tag `<b>`. Há teste de regressão que
> confere a fonte do caractere, não apenas a presença de negrito na página.

### Minuta editável sem tocar em código

O texto do contrato vive em `templates/*.md.j2` (Jinja2). O advogado revisa e
edita o arquivo direto; o código só injeta as variáveis. Convenções lidas pelo
gerador de PDF:

```
## TÍTULO          título de cláusula
### SUBTÍTULO      seção dentro da cláusula
a) item            item alfabético (a letra é preservada — outras cláusulas a citam)
[[ASSINATURAS]]    insere os blocos de assinatura
[[QUEBRA]]         força quebra de página
```

### Ficha em branco — quando não há CNPJ

**Não existe base pública de CPF.** A Consulta CPF do SERPRO devolve apenas nome
e situação cadastral (não endereço, telefone ou estado civil), e bureau privado
exige base legal própria sob a LGPD. Para pessoa física ou empresa ainda não
aberta, o caminho é a **ficha em branco** com declaração de veracidade assinada
— mais rápido, sem custo, e juridicamente mais sólido que qualquer consulta.

---

## ⚙️ Configuração obrigatória

Antes de emitir documento real, revise `src/config.py`:

```python
CONTRATADA_UF_REVISAR = "PR"   # ⚠️ Jundiaí é SP — ver nota no arquivo
FORO_PADRAO = "Campinas/SP"    # o modelo elege Campinas; a sede é Jundiaí
```

A qualificação da CONTRATADA (`CONTRATADA_QUALIFICACAO_FIXA`) é texto fixo com
as duas empresas do grupo, sem CRC e sem nomear pessoa física — decisão de
negócio, reproduzida do contrato em uso.

---

## 🆕 CNPJ alfanumérico

Desde julho/2026 a Receita emite CNPJs **alfanuméricos** (`12.ABC.345/01DE-35`).
A validação implementa módulo 11 com conversão `ord(c) - 48`, cobrindo os dois
formatos:

```python
from src.core.cnpj import validar, calcular_digitos

validar("11.222.333/0001-81")     # numérico tradicional
validar("12.ABC.345/01DE-35")     # novo formato
calcular_digitos("00000000E08G")  # -> "12"  (primeiro alfanumérico real emitido)
```

---

## 🏗️ Arquitetura

Separação estrita entre **regra de negócio** e **interface**: `core/` e
`services/` são Python puro, sem nenhum `import streamlit`. O motor tributário
roda em pytest em segundos e pode virar endpoint FastAPI ou job batch sem
reescrita.

```
app.py                          93 linhas — só configura a página e monta as abas
├── src/
│   ├── config.py               settings tipados, dados da CONTRATADA, preços
│   ├── core/                   ── Python puro, zero dependência de UI ──
│   │   ├── cnpj.py             validação numérica + alfanumérica (módulo 11)
│   │   ├── cpf.py              validação de CPF (módulo 11)
│   │   ├── models.py           Empresa, Endereço, CNAE, Sócio
│   │   ├── pessoas.py          partes contratuais e qualificação jurídica
│   │   ├── contrato.py         parâmetros, números por extenso, render Jinja2
│   │   ├── tributario.py       tabelas do Simples, comparador, MEI, honorários
│   │   └── formatters.py       moeda pt-BR, URLs seguras
│   ├── services/               ── I/O isolado ──
│   │   ├── http.py             Session com pool + retry exponencial
│   │   ├── cnpj_providers.py   3 provedores em paralelo + consolidação
│   │   ├── cep.py              ViaCEP + fallback BrasilAPI
│   │   ├── indicadores.py      BACEN (SGS) e IBGE
│   │   └── repository.py       persistência atrás de um Protocol
│   ├── exporters/              ── geração de artefatos ──
│   │   ├── excel.py            dossiê em 4 abas
│   │   ├── pdf_base.py         infraestrutura fpdf2 (layout fixo)
│   │   ├── pdf_dossie.py       dossiê, cartão CNPJ, proposta
│   │   ├── pdf_juridico.py     ReportLab Platypus (texto corrido, Página X de Y)
│   │   ├── timbrado.py         papel timbrado com cascata de fallback
│   │   ├── pdf_ficha.py        ficha cadastral (preenchida e em branco)
│   │   ├── pdf_contrato.py     contrato
│   │   ├── pdf_documentos.py   fachada pública dos documentos
│   │   └── docx_abertura.py    formulário DOCX com preenchimento híbrido
│   └── ui/                     ── única camada que conhece o Streamlit ──
│       ├── state.py            cache, session_state, singletons
│       ├── components.py       painéis reutilizáveis
│       └── tabs/               uma aba por arquivo
├── templates/                  minutas contratuais editáveis (Jinja2)
├── assets/timbrado/            arte do papel timbrado
├── scripts/migrar_crm.py       migração do banco v1 → v2
└── tests/                      206 testes
```

### Duas bibliotecas de PDF, de propósito

| Biblioteca | Onde | Por quê |
|---|---|---|
| **fpdf2** | dossiê, cartão CNPJ, proposta | layout fixo: sei quais campos existem e onde ficam |
| **ReportLab** | ficha, contrato | texto corrido de tamanho imprevisível: parágrafo justificado, controle de viúvas/órfãs, assinaturas que não partem entre páginas, "Página X de Y" (só conhecido após paginar tudo) |

WeasyPrint daria tipografia melhor, mas depende de cairo/pango — instável no
Streamlit Cloud. ReportLab é Python puro com wheels prontas.

---

## 🚀 Como rodar

```bash
git clone https://github.com/<seu-usuario>/<seu-repo>.git
cd <seu-repo>

python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
```

Abra <http://localhost:8501>.

### Desenvolvimento

```bash
pip install -r requirements-dev.txt
pytest                          # 263 testes
ruff check .                    # lint
mypy src                        # tipagem
```

> Continuar rodando no Streamlit Community Cloud funciona sem nenhuma mudança:
> `Dockerfile`, `render.yaml` e `requirements-pg.txt` são simplesmente ignorados
> por ele. O único ajuste recomendado é preencher os segredos para ligar o gate.
> Detalhes em [DEPLOY.md, seção 9](DEPLOY.md).

---

## 🔐 Autenticação

O app trata dado pessoal de cliente e a aba CRM lista a base de leads inteira.
Por isso `app.py` chama `exigir_login()` **antes de qualquer renderização** — sem
senha configurada, ninguém vê aba nenhuma.

As senhas vêm do ambiente (nunca do código):

```bash
# Render, Railway, Fly, Docker local — uma entrada por pessoa
MERCABILIZA_SENHAS='{"luisfelipe":"senha-longa","iago":"outra-senha-longa"}'

# Alternativa: senha única de equipe (não identifica quem entrou)
MERCABILIZA_SENHA_GERAL='uma-senha-longa-e-aleatoria'
```

No Streamlit Community Cloud, use o painel *Secrets* com o formato de
`.streamlit/secrets.toml.example`.

Gere cada senha assim — não invente à mão:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Sem nenhum segredo configurado o gate fica **aberto**, com aviso em tela: travar
o app por falta de config atrapalharia o desenvolvimento local, e o aviso impede
que a ausência passe em branco até a publicação.

> Repositório privado **não** substitui isto. Privado protege o *código*; o gate
> protege os *dados*. São controles independentes e você precisa dos dois.

Para trilha de auditoria de verdade (quem acessou o quê), o caminho é o login
OIDC nativo do Streamlit com a conta Google/Microsoft da empresa — formato
comentado em `.streamlit/secrets.toml.example`.

---

## ☁️ Deploy

O guia completo está em **[DEPLOY.md](DEPLOY.md)**: comparativo de plataformas
com custo real, migração do repositório público para privado (incluindo
auditoria do histórico com `gitleaks`/`trufflehog` e expurgo com
`git-filter-repo`), gerenciamento de segredos e passo a passo do deploy.

Resumo:

| Plataforma | Custo | Quando usar |
|---|---|---|
| **Render** (recomendado) | US$ 13/mês com Postgres | uso profissional diário; Docker nativo e banco no mesmo painel |
| Railway | ~US$ 8–10/mês | mesma coisa, painel melhor, fatura variável |
| Fly.io | ~US$ 6–9/mês | única com região em São Paulo (`gru`) |
| Streamlit Community Cloud | grátis | validação; disco efêmero e sem Docker |
| Vercel / Netlify | — | **não serve**: Streamlit é servidor de processo longo com WebSocket, não função serverless |

Arquivos de infra já no repositório: `Dockerfile`, `.dockerignore`,
`render.yaml`, `.env.example`, `.streamlit/secrets.toml.example`.

Rodar a imagem localmente, igual à de produção:

```bash
docker build -t mercabiliza .
docker run --rm -p 8501:8501 \
  -e MERCABILIZA_SENHA_GERAL='senha-de-teste' \
  mercabiliza
```

### Persistência: SQLite ou Postgres

O backend é escolhido por uma variável de ambiente, sem tocar em código de tela:

| `DATABASE_URL` | Backend | Consequência |
|---|---|---|
| ausente | SQLite em `data/` | ótimo local; **em PaaS a base é apagada a cada deploy** |
| definida | Postgres | persistente — é o que Render e Railway injetam ao vincular o banco |

A aba CRM mostra qual está em uso. Migrar o que já existe:

```bash
DATABASE_URL='postgresql://...' python scripts/migrar_crm.py
```

### Por que `requirements.txt` usa `>=` e não `==`

O Cloud atualiza o Python do runtime sem aviso. Um pin exato feito hoje vira,
meses depois, uma versão sem wheel para o Python novo — o pip tenta compilar do
fonte, falha e **aborta a instalação inteira**. O sintoma é cruel: pacotes que
vêm depois na lista simplesmente não são instalados, e o app quebra com
`ModuleNotFoundError` numa dependência que está no arquivo.

> ⚠️ **O disco do Community Cloud é efêmero.** Sem `DATABASE_URL`, o SQLite do
> CRM é apagado a cada reboot ou redeploy. Ver a tabela de persistência acima.

---

## 📊 Fontes de dados

| Fonte | Uso | Limite |
|---|---|---|
| [BrasilAPI](https://brasilapi.com.br/) | cadastro, QSA, CNAEs | público |
| [CNPJ.ws](https://cnpj.ws/) | inscrições estaduais, Simples | público |
| [ReceitaWS](https://receitaws.com.br/) | fallback cadastral | ~3 req/min (grátis) |
| [ViaCEP](https://viacep.com.br/) | endereço por CEP | público |
| [IBGE Localidades](https://servicodados.ibge.gov.br/) | código municipal, região | público |
| [BACEN SGS](https://dadosabertos.bcb.gov.br/) | Selic (4390), IPCA (433) | público |

A concorrência do lote é limitada a 4 requisições simultâneas para respeitar o
rate limit da ReceitaWS.

---

## 🔒 Privacidade e LGPD

A base de leads e os documentos armazenam CNPJ, CPF, e-mail, telefone e nomes de
sócios — dado pessoal sob a LGPD. Antes de operar comercialmente:

- Defina a base legal (execução de contrato para clientes; legítimo interesse
  para prospecção B2B, art. 7º, IX).
- Estabeleça política de retenção e descarte.
- Garanta o direito de eliminação (disponível na aba CRM).
- Nunca versione `data/`, `.db`, `.env` nem PDFs gerados — o `.gitignore` cobre
  todos, e `tests/test_infra.py` verifica que continua cobrindo.
- Publique **com autenticação** (art. 46: medidas aptas a proteger o dado de
  acesso não autorizado). Ver a seção 🔐 acima.
- **Não consulte CPF de terceiros em bureau privado** sem base legal própria.
  Peça o dado ao titular pela ficha cadastral.

---

## ⚖️ Ressalvas técnicas

Os cálculos seguem a LC 123/2006 e a legislação do Lucro Presumido, validados
contra referências publicadas (RBT12 de R$ 4 mi → 9,55%; teto do Anexo I →
11,12%). Ainda assim **precisam de homologação contábil** antes de virar
argumento comercial. Fora do escopo:

- **ICMS** — varia por UF e regime de substituição tributária.
- **Segregação de monofásicos** — o modelo usa a proporção de 15,50% de
  PIS/COFINS na alíquota do Anexo I. A apuração real é por NCM, item a item.
- **Encargos de mora do MEI** — aproximação (multa com teto de 20% + Selic +
  1%). O valor oficial sai do PGDAS-D na data do pagamento.
- **Reforma tributária (CBS/IBS)** — o período de transição afetará as
  projeções nos próximos anos.

O relatório completo de auditoria da refatoração está em [AUDITORIA.md](AUDITORIA.md).

---

## 📄 Licença

MIT — veja [LICENSE](LICENSE).
