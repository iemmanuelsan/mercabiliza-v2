# Check-up Técnico — app-Mercabiliza-contabil

**Auditoria de código, produto e arquitetura**
Revisor: Engenharia Sênior Python/Streamlit · Data: 14/08/2026
Escopo: `app.py` (1.295 linhas), `requirements.txt`, `README.md`

---

## Sumário executivo

O app entrega valor real e a lógica de negócio demonstra domínio do assunto
(monofásicos, Fator R, desenquadramento de MEI). Os problemas não estão na
ideia — estão na **estrutura** e em alguns **cálculos**.

Três achados exigem ação imediata:

| # | Achado | Impacto |
|---|---|---|
| 🔴 1 | **CNPJ alfanumérico é rejeitado silenciosamente** | O app não consulta CNPJs emitidos desde julho/2026 |
| 🔴 2 | **Selos de regularidade FGTS/CNDT são fixos, sem consulta** | Afirma regularidade não verificada em documento entregue ao cliente |
| 🔴 3 | **Excel + 2 PDFs regerados a cada interação** | Travamento e estouro de memória no Streamlit Cloud |

Total: **9 bugs de correção**, **6 gargalos de performance**, **5 riscos de
produto/jurídicos** e a ausência completa de testes.

**Veredito:** a refatoração entregue reduz `app.py` de 1.295 linhas para **91**,
distribui a lógica em 18 módulos coesos e adiciona **77 testes** (todos
passando, lint limpo).

> 📌 Este relatório é datado de 14/08/2026. O módulo de documentos (ficha,
> contrato em timbrado e formulário DOCX) veio depois, junto de mais achados
> sobre os documentos-fonte da empresa — ver **Apêndice** no fim do arquivo.
> Estado atual: `app.py` com 93 linhas e **199 testes**.

---

## 1. Bugs de correção

### 🔴 1.1 — CNPJ alfanumérico descartado (crítico e datado)

Desde **julho/2026** a Receita emite CNPJs alfanuméricos; o primeiro real
(`00.000.000/E08G-12`, agência do Banco do Brasil) saiu em **02/08/2026** —
doze dias antes desta auditoria.

```python
# ANTES — descarta as letras e rejeita o CNPJ como inválido
def limpar_cnpj(cnpj_raw):
    cnpj_limpo = re.sub(r'\D', '', str(cnpj_raw))   # "12ABC34501DE35" -> "123450135"
    return cnpj_limpo if len(cnpj_limpo) == 14 else None
```

Não valida dígito verificador **e** mutila o novo formato. Devolver `None` em
silêncio faz um erro de digitação virar "CNPJ não localizado".

```python
# DEPOIS — módulo 11 com ord(c)-48; retrocompatível com o formato numérico
_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

def _digito(base: str, pesos: tuple[int, ...]) -> int:
    soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto

def validar(bruto: object) -> str:
    """Devolve o CNPJ limpo ou levanta CNPJInvalidoError com o motivo."""
    cnpj = normalizar(bruto)
    if len(cnpj) != 14:
        raise CNPJInvalidoError(f"CNPJ deve ter 14 caracteres (recebidos {len(cnpj)}).")
    if not cnpj[12:].isdigit():
        raise CNPJInvalidoError("As duas últimas posições devem ser numéricas.")
    if calcular_digitos(cnpj[:12]) != cnpj[12:]:
        raise CNPJInvalidoError("Dígito verificador inválido — confira a digitação.")
    return cnpj
```

Validado contra o exemplo canônico da RFB (`12.ABC.345/01DE-35`) e contra o
primeiro alfanumérico real emitido. → `src/core/cnpj.py`

---

### 🔴 1.2 — `AttributeError` garantido quando um provedor falha

```python
# ANTES — se dados_rws for None e os anteriores vierem vazios: AttributeError
razao = (dados_br.get("razao_social") if dados_br else None) \
        or (dados_ws.get("razao_social") if dados_ws else None) \
        or dados_rws.get("nome")          # ← sem guarda
```

O padrão se repete em **15 campos** (linhas 420–434). Basta a BrasilAPI
responder com `razao_social` vazio e a ReceitaWS estar fora para o app quebrar.

```python
# DEPOIS — resolução por prioridade, imune a fonte ausente
def _primeiro_preenchido(fontes: list[dict], chave: str, padrao=""):
    for fonte in fontes:
        valor = fonte.get(chave)
        if valor not in (None, "", 0.0, [], ()):
            return valor
    return padrao
```

Cada provedor vira um *adapter* que traduz seu JSON para um dicionário
canônico; a consolidação passa a ser trivial. → `src/services/cnpj_providers.py`

---

### 🔴 1.3 — Comparador de regimes: margem é código morto, alíquotas fixas

```python
# ANTES
def comparar_regimes_simples_presumido(fat_mensal, margem_pct=15.0, tipo_lucro="Líquido"):
    if tipo_lucro == "Bruto":
        margem_efetiva_pct = margem_pct * 0.30
    else:
        margem_efetiva_pct = margem_pct     # ← calculada e NUNCA usada

    imp_simples = fat_anual * 0.033         # ← alíquota fixa
    imp_presumido = fat_anual * 0.059       # ← alíquota fixa
```

Dois problemas somados. A UI tem um `radio` de Líquido/Bruto e um campo de
margem que **não alteram nada** no resultado. E os 3,3% ignoram a tabela
progressiva:

| RBT12 | Original (3,3%) | Efetiva real (Anexo I) | Erro |
|---|---|---|---|
| R$ 420.000 (R$ 35 mil/mês) | 3,30% | **6,20%** | −88% |
| R$ 1.000.000 | 3,30% | **8,45%** | −156% |

O app **subestima o DAS pela metade** no cenário-padrão da tela.

```python
# DEPOIS — tabelas progressivas da LC 123/2006
ANEXO_I = (
    (180_000.00, 0.0400, 0.00),
    (360_000.00, 0.0730, 5_940.00),
    (720_000.00, 0.0950, 13_860.00),
    (1_800_000.00, 0.1070, 22_500.00),
    (3_600_000.00, 0.1430, 87_300.00),
    (4_800_000.00, 0.1900, 378_000.00),
)

def aliquota_efetiva(rbt12: float, tabela) -> float:
    """(RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12"""
    if rbt12 <= 0:
        return 0.0
    for teto, nominal, deducao in tabela:
        if rbt12 <= teto:
            return max(0.0, (rbt12 * nominal - deducao) / rbt12)
    ...
```

O Lucro Presumido também passou a ser calculado por dentro — PIS 0,65% +
COFINS 3% sobre a receita não monofásica, IRPJ 15% sobre presunção de 8% com
adicional de 10%, CSLL 9% sobre presunção de 12% — em vez de 5,9% chapados.
Os parâmetros de margem foram **removidos da assinatura**: margem não influencia
tributos que incidem sobre receita, e manter o parâmetro sugeria o contrário.

> ✅ Validado contra referências publicadas: RBT12 de R$ 4 mi → 9,55%; teto do
> Anexo I → 11,12%. Um teste documenta a **descontinuidade real** da LC 123 na
> fronteira de R$ 3,6 mi (a efetiva cai de 11,875% para 8,50%) — para que
> ninguém "corrija" a tabela por engano.

→ `src/core/tributario.py`

---

### 🟠 1.4 — Selic somada em vez de composta

```python
# ANTES — série 4390 é "Selic acumulada NO MÊS"; somar ignora juros sobre juros
soma = sum(float(item["valor"]) for item in dados if "valor" in item)
if soma > 0: selic_ano = soma
```

O erro se propagava direto para os encargos de mora do cálculo retroativo do
MEI. A série `10844` usada para o IPCA também não é a série mensal do IPCA
(que é a **433**).

```python
# DEPOIS
def _acumular_composto(valores: list[float]) -> float | None:
    if not valores:
        return None
    fator = 1.0
    for taxa in valores:
        fator *= 1 + taxa / 100.0
    return (fator - 1) * 100.0
```

→ `src/services/indicadores.py`

---

### 🟠 1.5 — Link de WhatsApp gera número inexistente

```python
# ANTES — d['telefone'] é a junção de TODOS os telefones
num_limpo = re.sub(r'\D', '', str(d['telefone']))   # "(19) 3333-4444, (19) 99999-8888"
num_wsp = "55" + num_limpo[:11]                     # -> "551933334444199" ❌
```

Empresa com duas linhas → link para um número que não existe. Corrigido com
`Empresa.telefone_principal` e um `selectbox` para o usuário escolher a linha.
→ `src/core/models.py`, `src/ui/components.py`

---

### 🟠 1.6 — Demais correções

| Bug | Local original | Correção |
|---|---|---|
| `ZeroDivisionError` na barra de progresso com planilha vazia | linha 1166 | guarda `if total == 0` |
| `TypeError` em `float(capital_social)` quando a chave existe com `None` | linha 454 | `_float()` tolerante |
| `IndexError` em `.split(" - ")[1]` | linhas 474, 606-607 | dados vêm do modelo, sem parsing de string |
| `.replace(" ", "+")` quebra URL do Maps com acento/`&` | linha 438 | `quote_plus()` |
| Ordem de e-mails/telefones não-determinística (`set`) | linhas 351-352 | `sorted()` → tupla |
| `$R\$` (LaTeX quebrado) na tela | linha 1218 | removido |

---

## 2. Performance

### 🔴 2.1 — Artefatos regenerados a cada rerun (maior gargalo)

O Streamlit reexecuta **o script inteiro** a cada interação com qualquer
widget. Estas três chamadas estão no corpo da aba, fora de qualquer callback:

```python
# ANTES — linhas 997, 1007, 1049
excel_file = gerar_excel_dossie_4abas(st.session_state.historico)   # 4 abas, N empresas
pdf_bytes = gerar_pdf_dossie_completo(d)                            # PDF completo
pdf_proposta = gerar_proposta_minimercado_pdf(d, ...)               # outro PDF
```

Consequência: **mover o slider de "% monofásico" na aba 2 reconstrói uma
pasta de trabalho Excel e dois PDFs** — para todas as empresas do lote. Com 50
empresas em sessão, cada clique custa segundos de CPU e dezenas de MB.

```python
# DEPOIS — cache por conteúdo; o "_" evita hashear os objetos Empresa
@st.cache_data(show_spinner=False, max_entries=32)
def excel_bytes(chave: str, _empresas: tuple[Empresa, ...]) -> bytes:
    from ..exporters.excel import gerar_dossie_excel
    return gerar_dossie_excel(list(_empresas))

# chamada: excel_bytes("|".join(sorted(e.cnpj for e in lote)), tuple(lote))
```

A proposta em PDF foi além: só é montada quando o usuário **clica no botão**.
E o bloco de precificação virou `@st.fragment`, isolando seus reruns.
→ `src/ui/state.py`, `src/ui/tabs/dossie.py`

---

### 🔴 2.2 — Consultas de API em série

```python
# ANTES — 3 requisições sequenciais, timeout de 8s cada = até 24s por CNPJ
r = requests.get(f"https://brasilapi.com.br/...", timeout=8)
r = requests.get(f"https://publica.cnpj.ws/...", timeout=8)
r = requests.get(f"https://receitaws.com.br/...", timeout=8)
```

No lote isso multiplicava por N: 100 CNPJs = 300 requisições estritamente
sequenciais, cada uma abrindo uma conexão TLS nova.

```python
# DEPOIS — provedores em paralelo, dentro de uma Session com pool + retry
with ThreadPoolExecutor(max_workers=3) as pool:
    for nome, canonico in pool.map(_buscar, PROVEDORES):
        if canonico:
            resultados[nome] = canonico
```

E o lote processa 4 CNPJs simultâneos (limite deliberado: a ReceitaWS gratuita
permite ~3 req/min). Ganho de ordem de grandeza, com rate limit respeitado.
→ `src/services/cnpj_providers.py`, `src/services/http.py`

---

### 🟠 2.3 — Outros ganhos

| Problema | Correção |
|---|---|
| `consultar_dossie_completo` sem cache — reconsultava a mesma empresa | `@st.cache_data(ttl=12h)` |
| `init_db()` no topo do módulo → `CREATE TABLE` a cada rerun | `@st.cache_resource` |
| Conexão TCP+TLS nova por request | `requests.Session` com pool |
| Histórico de sessão crescia sem limite | teto de 25 empresas |
| Lote sem teto de linhas | limite de 200 CNPJs, com aviso |

---

## 3. Riscos de produto e jurídicos

### 🔴 3.1 — Regularidade afirmada sem consulta

```python
# ANTES — valores fixos, nenhuma consulta é feita
return {
    "cnd_fgts": "🟢 Regularidade Cadastral FGTS", "obs_fgts": "Consulta cadastral ativa.",
    "cndt_trabalhista": "🟢 CNDT - Regularidade Trabalhista", "obs_cndt": "Sem pendências cadastrais.",
    "processos_judiciais": "🟢 Sem Apontamentos Públicos", "obs_processos": "Sem registros impeditivos.",
}
```

Esses selos verdes aparecem na tela, **no Excel e no PDF entregue ao cliente**.
"Sem pendências" e "Sem registros impeditivos" são afirmações de fato sobre a
situação trabalhista e judicial de terceiros que o sistema nunca verificou.

Isso não é bug de código — é risco jurídico e reputacional. O rodapé genérico
("exige certificado digital") não neutraliza um selo verde afirmativo no corpo
do documento.

```python
# DEPOIS — o modelo distingue verificado de não verificado
@property
def pendentes_de_verificacao(self) -> tuple[str, ...]:
    return (
        "CND Federal (RFB/PGFN) — exige emissão no e-CAC",
        "CRF/FGTS — exige consulta na Caixa",
        "CNDT — exige consulta no TST",
        "Certidões estaduais e municipais",
    )
```

A UI mostra apenas a situação cadastral (essa sim consultada) e lista
explicitamente o que **não** foi verificado. → `src/core/models.py`

---

### 🟠 3.2 — Injeção de HTML sem escape

```python
# ANTES — dados de API entram direto no DOM
html_code = f"""<td ...>{d['razao_social']}</td>..."""
st.markdown(html_code, unsafe_allow_html=True)
```

Razão social ou nome fantasia com `<script>` vira XSS armazenado. Substituído
por `st.dataframe`, que escapa por construção. → `src/ui/components.py`

---

### 🟠 3.3 — LGPD e vazamento do banco

`leads_contabeis.db` grava CNPJ, e-mail, telefone e **nomes de sócios** (dado
pessoal) na raiz do projeto — sem `.gitignore`, um `git add .` publica a base de
prospects no GitHub. O `.gitignore` entregue cobre `data/`, `*.db`, `*.xlsx`,
`*.pdf` e `secrets.toml`. A aba CRM ganhou remoção individual (direito de
eliminação).

---

### 🟠 3.4 — Silenciamento total de erros

O padrão `except Exception: pass` aparece **8 vezes**. O caso mais grave:

```python
# ANTES — falha de gravação é invisível; a UI ainda diz "salvo no CRM!"
def salvar_lead_db(emp):
    try:
        ...
    except Exception:
        pass
```

Substituído por logging estruturado com o motivo real (timeout, 429, JSON
inválido) e feedback honesto na UI.

---

### 🟠 3.5 — Persistência efêmera não sinalizada

A tela afirma que os dados são salvos "no banco de dados local da sua máquina".
No Streamlit Community Cloud o disco é **efêmero**: o CRM é apagado a cada
reboot. O usuário perde a base sem saber por quê. Adicionado aviso explícito e
a interface `LeadRepository` (`Protocol`) para trocar por Postgres sem tocar em
UI.

---

## 4. Arquitetura e boas práticas

### 4.1 — Antes: um arquivo, todas as responsabilidades

`app.py` com 1.295 linhas misturava chamadas HTTP, regra tributária, geração de
PDF, SQL e layout. Impossível testar sem subir o Streamlit; impossível
reaproveitar o motor tributário fora dele.

### 4.2 — Depois: núcleo puro, UI na borda

**`core/` e `services/` não importam Streamlit.** Consequências práticas: o
motor tributário roda em pytest em 0,12s, e amanhã pode virar endpoint FastAPI
sem reescrita.

```
app.py (91 linhas)  →  src/config.py · core/ (4) · services/ (4) · exporters/ (3) · ui/ (8)
```

### 4.3 — Substituindo if/elif por dados

```python
# ANTES — 65 linhas de if/elif com dicionários literais repetidos
if is_minimercado or code_clean.startswith(('45','46','47')): return {...}
elif code_clean.startswith(('10','11',...,'32')): return {...}
for prefix in sujeito_fator_r: ...
```

```python
# DEPOIS — tabela de regras; prefixo mais específico vence
REGRAS = (
    RegraCNAE(prefixos=("4711","4712","4721","4723","4729"), anexo_chave="I",
              is_minimercado=True, ...),
    RegraCNAE(prefixos=("45","46","47"), anexo_chave="I", ...),
    ...
)

regra, melhor = REGRA_PADRAO, 0
for candidata in REGRAS:
    for prefixo in candidata.prefixos:
        if limpo.startswith(prefixo) and len(prefixo) > melhor:
            regra, melhor = candidata, len(prefixo)
```

Bônus: a ordem dos `elif` deixa de ser sutilmente relevante. Adicionar um CNAE
vira uma linha de dados, não um ramo de código.

### 4.4 — Dicionário de 30 chaves → dataclasses

`emp_dict` circulava entre API, exporters e UI. Erro de digitação em chave só
aparecia como `KeyError` no meio da geração do PDF. Agora há `Empresa`,
`Endereco`, `AtividadeCNAE`, `Socio`, `SituacaoCadastral` — com autocomplete e
checagem estática.

### 4.5 — Regra de preço duplicada

A fórmula de honorários existia em dois lugares (resumo na tela e dentro do PDF).
Um reajuste exigiria lembrar dos dois. Centralizada em `calcular_honorarios()`.

---

## 5. Repositório

### 5.1 — `requirements.txt`

```diff
- streamlit          # sem pin: o Cloud reconstrói com a última versão a cada deploy
- requests
- pandas
- openpyxl
- fpdf2
+ streamlit==1.41.1
+ requests==2.32.3
+ urllib3==2.2.3
+ pandas==2.2.3
+ openpyxl==3.1.5
+ fpdf2==2.8.2
```

Sem pin, um app que funcionava ontem quebra hoje por breaking change de
terceiro — e o log do Cloud não deixa isso óbvio. Adicionado
`requirements-dev.txt` com pytest, ruff e mypy.

### 5.2 — Arquivos que faltavam

| Arquivo | Por quê |
|---|---|
| `.gitignore` | protege `data/`, `*.db`, `secrets.toml`, `__pycache__` |
| `.streamlit/config.toml` | tema da marca, `maxUploadSize`, `showErrorDetails=false` |
| `pyproject.toml` | configuração de ruff, pytest e mypy |
| `README.md` | o original tinha **2 linhas** (só o título) |
| `tests/` | não existia nenhum teste |

### 5.3 — Depreciações corrigidas

`fpdf2 ≥ 2.7.6` depreciou `cell(..., ln=True)` → substituído por
`new_x=XPos.LMARGIN, new_y=YPos.NEXT` num helper da classe base.

---

## 6. UI/UX

| Antes | Depois |
|---|---|
| Sem sidebar; instruções perdidas no `caption` | Sidebar com guia de uso e escopo legal |
| Botão dispara busca; resultado só no rerun seguinte | `st.form` + callback: resultado imediato ao pressionar Enter |
| Histórico guardado mas só `[0]` exibido | `selectbox` navega todas as consultas da sessão |
| Erro genérico "CNPJ não localizado" | Motivo real: DV inválido, formato, ou APIs fora |
| Barra de progresso sem contexto | `"37/200 processados · 34 encontrados"` |
| Linhas inválidas do lote descartadas em silêncio | Tabela de descartados com o motivo de cada um |
| CRM sem filtros | Filtros por UF/regime/busca + gráfico + remoção LGPD |
| PDF sem acentos: "PRESTACAO DE SERVICOS CONTABEIS" | Fonte Unicode DejaVu: **"PRESTAÇÃO DE SERVIÇOS CONTÁBEIS"** |
| Excel com colunas cortadas | Larguras automáticas, autofiltro, painéis congelados |
| Alíquota sempre a da 1ª faixa | Campo RBT12 opcional → alíquota efetiva real da empresa |

---

## 7. Testes

Não havia nenhum. Foram escritos **77**, todos passando:

```
tests/test_cnpj.py          →  validação numérica e alfanumérica, exemplos oficiais da RFB
tests/test_tributario.py    →  42 testes: tabelas, faixas, continuidade, regimes, MEI, preços
tests/test_formatters.py    →  moeda pt-BR, URLs escapadas, regressão do bug do WhatsApp
tests/test_app_smoke.py     →  renderização completa via AppTest, com a rede bloqueada
```

Três decisões que valem destaque:

**Testes de regressão nomeados.** Cada bug corrigido tem um teste que falha se
alguém reintroduzir o comportamento antigo — por exemplo
`test_regressao_margem_era_codigo_morto`.

**Validação contra referências externas.** As alíquotas são conferidas contra
valores publicados (R$ 4 mi → 9,55%; teto 11,12%), não contra o que o código
calcula.

**Smoke test com a rede desligada.** `AppTest` roda o app inteiro headless com
`requests` bloqueado, garantindo degradação elegante quando as APIs caem — o
cenário mais provável em produção.

```bash
$ pytest -q
77 passed in 4.31s

$ ruff check src app.py tests
All checks passed!
```

---

## 8. Plano de ação priorizado

### 🚑 Quick wins (fazer hoje — ~2h, alto impacto)

1. **Criar `.gitignore`** e rodar `git rm --cached leads_contabeis.db` se a base
   já estiver versionada. *(5 min — impede vazamento de dados pessoais)*
2. **Pinar o `requirements.txt`.** *(5 min — evita quebra silenciosa no deploy)*
3. **Remover os selos fixos de FGTS/CNDT/processos** da tela, do Excel e do PDF.
   *(30 min — elimina o risco jurídico)*
4. **Tirar as três chamadas de geração de arquivo do corpo das abas**, movendo-as
   para trás de um botão ou de `@st.cache_data`. *(30 min — resolve o
   travamento)*
5. **Corrigir o link do WhatsApp** para usar um único telefone. *(15 min — hoje
   ele gera número inexistente)*

### 🔧 Refatoração média (esta semana — ~1 dia)

6. **Adotar a validação de CNPJ alfanumérico.** Já em produção há 12 dias.
7. **Paralelizar as consultas** com `ThreadPoolExecutor` + `Session`.
8. **Substituir as alíquotas fixas** pelas tabelas progressivas.
9. **Trocar `except Exception: pass`** por logging com motivo.
10. **Corrigir a acumulação da Selic** (composta, não somada).

### 🏗️ Refatoração profunda (próximas 2 semanas)

11. **Adotar a estrutura modular** (`core`/`services`/`exporters`/`ui`).
12. **Migrar o CRM para Postgres** — o SQLite não sobrevive ao Cloud.
13. **Rodar a suíte de testes no CI** (GitHub Actions com pytest + ruff).
14. **Homologar os números com a contabilidade** antes de usá-los como
    argumento comercial.

---

## 9. Ressalva importante

Os cálculos tributários foram corrigidos com base na LC 123/2006 e na
legislação do Lucro Presumido, e validados contra referências publicadas. Ainda
assim, **precisam de homologação contábil formal** antes de virar argumento de
venda. Pontos que ficaram deliberadamente fora do escopo:

- **ICMS** (varia por UF e regime de substituição tributária).
- **Segregação de monofásicos:** o modelo usa a proporção de 15,50% de
  PIS/COFINS na alíquota do Anexo I. A apuração real é feita por NCM, item a
  item — o número da tela é estimativa, não apuração.
- **Encargos de mora do MEI:** aproximação (multa de mora com teto de 20% +
  Selic acumulada + 1%). O valor oficial sai do PGDAS-D na data do pagamento.
- **Reforma tributária (CBS/IBS):** o período de transição afetará estas
  projeções nos próximos anos. Vale planejar como o app tratará os dois
  sistemas em paralelo.

---

## Anexo — Arquivos entregues

```
mercabiliza/
├── app.py                       91 linhas (era 1.295)
├── AUDITORIA.md                 este documento
├── README.md                    README de portfólio com badges e arquitetura
├── requirements.txt             pinado
├── requirements-dev.txt         pytest, ruff, mypy
├── pyproject.toml               config de lint, testes e tipagem
├── .gitignore                   proteção de dados e segredos
├── .streamlit/config.toml       tema e limites do servidor
├── src/
│   ├── config.py
│   ├── core/        cnpj.py · models.py · tributario.py · formatters.py
│   ├── services/    http.py · cnpj_providers.py · indicadores.py · repository.py
│   ├── exporters/   pdf_base.py · pdf_dossie.py · excel.py
│   └── ui/          state.py · components.py · tabs/{dossie,comparador,lote,mei,crm}.py
└── tests/           77 testes
```

---

# Apêndice — Atualizações posteriores à auditoria

A auditoria acima é datada de **14/08/2026** e trata do `app.py` original de
1.295 linhas. O que veio depois está registrado aqui para manter o documento
coerente com o repositório.

## A.1 Módulo de documentos (21/08/2026)

Nova aba **📝 Ficha & contrato** com três modalidades (PJ, MEI, PF) gerando:

| Documento | Formato | Motor |
|---|---|---|
| Ficha cadastral (preenchida e em branco) | PDF | ReportLab |
| Contrato de prestação de serviços | PDF em papel timbrado | ReportLab |
| Formulário de abertura/desenquadramento | DOCX | python-docx |

Módulos acrescentados: `core/cpf.py`, `core/pessoas.py`, `core/contrato.py`,
`services/cep.py`, `exporters/pdf_juridico.py`, `exporters/timbrado.py`,
`exporters/pdf_ficha.py`, `exporters/pdf_contrato.py`,
`exporters/docx_abertura.py`, `ui/tabs/contratos.py` e as minutas em
`templates/`.

Testes: **77 → 199**.

## A.2 Erros encontrados nos documentos-fonte

Estes não são defeitos de código — são erros nos documentos em uso, que se
repetiriam em todo contrato assinado.

| # | Achado | Situação |
|---|---|---|
| 1 | `JUNDIAI/PR` na qualificação da CONTRATADA. Jundiaí é município de **São Paulo**; o cartão CNPJ da própria empresa traz `JUNDIAI/SP`. | Mantido conforme o modelo, isolado em `CONTRATADA_UF_REVISAR` (`src/config.py`). **Pendente de decisão.** |
| 2 | Rodapé cita `Lei 10.402/2002`. O Código Civil é a **Lei 10.406/2002**. | Corrigido em `CONTRATO_NOTA_RODAPE`, com nota. |
| 3 | `Papeltimbrado08Mercabiliza.docx` contém duas artes: `image1.png` é um template **AMLabs Summit** (fundo escuro, outra marca) e `image2.png` é o timbrado Mercabiliza. Os headers `first` e `default` apontam para o AMLabs. | O app usa o `image2`. **O .docx original precisa ser limpo.** |
| 4 | O rodapé do timbrado traz endereço em **Campinas**; a qualificação do contrato traz **Jundiaí**. | Provavelmente intencional (operação × sede). **Confirmar.** |
| 5 | O contrato modelo não tem cláusula de LGPD. | Acrescentada como Cláusula 6. |

## A.3 Bugs de código encontrados a partir de saída real

O cartão CNPJ gerado em produção pelo próprio app revelou dois defeitos na
consolidação de dados:

| Bug | Sintoma real | Correção |
|---|---|---|
| Tipo de logradouro descartado | endereço saía `ANCHIETA, 204` em vez de `RUA ANCHIETA, 204` — a BrasilAPI separa o tipo em `descricao_tipo_de_logradouro` | `_com_tipo_logradouro()` |
| Deduplicação de telefone por string | `(19) 3327-0038, (19) 33270038, 193327003` — o mesmo número três vezes | `_dedup_telefones()` deduplica por dígitos |

Ambos passariam desapercebidos num dossiê e são inaceitáveis num contrato.

## A.4 Precisão jurídica da qualificação

Três correções na redação das partes, todas visíveis em documento assinado:

- **MEI/EI não é "pessoa jurídica de direito privado"** — é empresário
  individual, e a razão social é o nome da pessoa. O texto agora detecta isso
  pela natureza jurídica e escreve "neste ato assinando na qualidade de
  titular" em vez de "representada por" a mesma pessoa.
- **Concordância de gênero** — saía "MARIA DA SILVA, brasileiro, casada,
  empresário… inscrito no CPF". Nacionalidade, estado civil, profissão e
  qualificação passam por uma tabela de flexão conservadora.
- **CONTRATADA sem CRC e sem pessoa física** — decisão de negócio, refletida no
  texto fixo das duas empresas do grupo.

## A.5 Ressalva sobre o argumento comercial

A mensagem da aba **Comparador** afirma que a economia com monofásicos "cobre
boa parte dos honorários". Levantando a curva:

| Faturamento/mês | Economia/mês | % do honorário (R$ 550) |
|---|---|---|
| R$ 25 mil | R$ 113 | 21% |
| R$ 35 mil | R$ 185 | 34% |
| R$ 50 mil | R$ 306 | 56% |
| **R$ 75 mil** | **R$ 524** | **95%** |
| R$ 100 mil | R$ 752 | 137% |

O argumento só se sustenta a partir de ~**R$ 75 mil/mês**. Abaixo disso a
mensagem superestima. **Pendente:** tornar o texto condicional ao valor real.
