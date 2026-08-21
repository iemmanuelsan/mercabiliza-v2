"""Motor de inteligência tributária.

Mudanças relevantes em relação à versão original (todas sinalizadas com
``# [CORRIGIDO]``) — os números seguem a LC 123/2006 e a legislação do Lucro
Presumido, mas **devem ser homologados pela contabilidade** antes de virar
argumento comercial.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .formatters import moeda
from .formatters import percentual as _pct
from .models import DiagnosticoCNAE

# --------------------------------------------------------------------------- #
# 1. Tabelas progressivas do Simples Nacional (LC 123/2006, Anexos I a V)      #
# --------------------------------------------------------------------------- #
# Cada faixa: (teto de RBT12, alíquota nominal, parcela a deduzir)
TabelaAnexo = tuple[tuple[float, float, float], ...]

ANEXO_I: TabelaAnexo = (
    (180_000.00, 0.0400, 0.00),
    (360_000.00, 0.0730, 5_940.00),
    (720_000.00, 0.0950, 13_860.00),
    (1_800_000.00, 0.1070, 22_500.00),
    (3_600_000.00, 0.1430, 87_300.00),
    (4_800_000.00, 0.1900, 378_000.00),
)
ANEXO_II: TabelaAnexo = (
    (180_000.00, 0.0450, 0.00),
    (360_000.00, 0.0780, 5_940.00),
    (720_000.00, 0.1000, 13_860.00),
    (1_800_000.00, 0.1120, 22_500.00),
    (3_600_000.00, 0.1470, 85_500.00),
    (4_800_000.00, 0.3000, 720_000.00),
)
ANEXO_III: TabelaAnexo = (
    (180_000.00, 0.0600, 0.00),
    (360_000.00, 0.1120, 9_360.00),
    (720_000.00, 0.1350, 17_640.00),
    (1_800_000.00, 0.1600, 35_640.00),
    (3_600_000.00, 0.2100, 125_640.00),
    (4_800_000.00, 0.3300, 648_000.00),
)
ANEXO_IV: TabelaAnexo = (
    (180_000.00, 0.0450, 0.00),
    (360_000.00, 0.0900, 8_100.00),
    (720_000.00, 0.1020, 12_420.00),
    (1_800_000.00, 0.1400, 39_780.00),
    (3_600_000.00, 0.2200, 183_780.00),
    (4_800_000.00, 0.3300, 828_000.00),
)
ANEXO_V: TabelaAnexo = (
    (180_000.00, 0.1550, 0.00),
    (360_000.00, 0.1800, 4_500.00),
    (720_000.00, 0.1950, 9_900.00),
    (1_800_000.00, 0.2050, 17_100.00),
    (3_600_000.00, 0.2300, 62_100.00),
    (4_800_000.00, 0.3050, 540_000.00),
)

TABELAS = {
    "I": ANEXO_I, "II": ANEXO_II, "III": ANEXO_III, "IV": ANEXO_IV, "V": ANEXO_V,
}

LIMITE_SIMPLES_ANUAL = 4_800_000.00
LIMITE_MEI_MENSAL = 6_750.00          # R$ 81.000/ano ÷ 12
DAS_MEI_MEDIO_MENSAL = 75.00


def aliquota_efetiva(rbt12: float, tabela: TabelaAnexo) -> float:
    """Alíquota efetiva do Simples: ``(RBT12 × nominal − PD) ÷ RBT12``.

    [CORRIGIDO] A versão anterior usava alíquotas fixas de 3,3% (Simples) e
    5,9% (Presumido), ignorando totalmente a faixa de faturamento. Para um
    minimercado faturando R$ 35 mil/mês (R$ 420 mil/ano) o erro passava de
    100% na estimativa do DAS.
    """
    if rbt12 <= 0:
        return 0.0
    for teto, nominal, deducao in tabela:
        if rbt12 <= teto:
            return max(0.0, (rbt12 * nominal - deducao) / rbt12)
    # Acima do teto do Simples: devolve a última faixa apenas como referência.
    teto, nominal, deducao = tabela[-1]
    return max(0.0, (rbt12 * nominal - deducao) / rbt12)


# --------------------------------------------------------------------------- #
# 2. Classificação de CNAE — orientada a dados, não a cadeia de if/elif        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RegraCNAE:
    prefixos: tuple[str, ...]
    anexo_rotulo: str
    anexo_chave: str
    tem_fator_r: bool
    is_minimercado: bool
    resumo: str
    dica: str


DICA_MONOFASICO = (
    "💡 OPORTUNIDADE DE REDUÇÃO FISCAL PARA MINI MERCADOS & VAREJO\n"
    "• PIS/COFINS MONOFÁSICO e ICMS-ST: bebidas (cervejas, refrigerantes, água, "
    "energéticos), higiene pessoal e alguns snacks têm o tributo recolhido na "
    "indústria/distribuidora.\n"
    "• SEGREGAÇÃO NO SIMPLES: na apuração do PGDAS-D (Anexo I) essas receitas são "
    "informadas com tributação monofásica, retirando PIS/COFINS da base.\n"
    "👉 Ação: exigir o relatório de vendas por NCM/EAN do totem de autoatendimento "
    "para permitir a segregação mês a mês."
)

DICA_FATOR_R = (
    "• Se (folha de pagamento + pró-labore dos últimos 12 meses) ÷ RBT12 ≥ 28%, "
    "a empresa tributa pelo ANEXO III.\n"
    "• Abaixo de 28%, tributa pelo ANEXO V, substancialmente mais caro.\n"
    "👉 Recomendação: simular o ajuste de pró-labore para cruzar os 28%, confrontando "
    "o custo do INSS adicional contra a economia no DAS antes de recomendar."
)

REGRAS: tuple[RegraCNAE, ...] = (
    RegraCNAE(
        prefixos=("4711", "4712", "4721", "4723", "4729"),
        anexo_rotulo="Anexo I (Comércio Varejista Alimentício)",
        anexo_chave="I", tem_fator_r=False, is_minimercado=True,
        resumo="🛒 Minimercado / varejo alimentício. Anexo I do Simples Nacional.",
        dica=DICA_MONOFASICO,
    ),
    RegraCNAE(
        prefixos=("45", "46", "47"),
        anexo_rotulo="Anexo I (Comércio)",
        anexo_chave="I", tem_fator_r=False, is_minimercado=False,
        resumo="Atividade de comércio. Tributada pelo Anexo I.",
        dica=DICA_MONOFASICO,
    ),
    RegraCNAE(
        prefixos=tuple(str(i) for i in range(10, 33)),
        anexo_rotulo="Anexo II (Indústria)",
        anexo_chave="II", tem_fator_r=False, is_minimercado=False,
        resumo="Atividade industrial. Tributada pelo Anexo II.",
        dica="Atentar ao destaque de IPI, apuração de insumos e crédito de ICMS.",
    ),
    RegraCNAE(
        prefixos=("41", "42", "43", "8010", "8020", "8011", "8012", "8013"),
        anexo_rotulo="Anexo IV (Construção Civil / Vigilância)",
        anexo_chave="IV", tem_fator_r=False, is_minimercado=False,
        resumo="Tributada pelo Anexo IV.",
        dica=("A contribuição patronal do INSS (CPP) NÃO está inclusa no DAS. "
              "Recolher em GPS/DARF apartada — impacto relevante no fluxo de caixa."),
    ),
    RegraCNAE(
        prefixos=("6201", "6202", "6203", "6204", "6209", "6911", "7020", "7111",
                  "7112", "7311", "7490", "8610", "8630", "8650", "9000"),
        anexo_rotulo="Anexo III ou V (sujeito ao Fator R ⚡)",
        anexo_chave="III", tem_fator_r=True, is_minimercado=False,
        resumo="⚡ Atividade sujeita à regra do Fator R.",
        dica=DICA_FATOR_R,
    ),
)

REGRA_PADRAO = RegraCNAE(
    prefixos=(),
    anexo_rotulo="Anexo III (Serviços Gerais)",
    anexo_chave="III", tem_fator_r=False, is_minimercado=False,
    resumo="Tributada diretamente pelo Anexo III.",
    dica="Serviço com tributação no Anexo III sem necessidade de atingir o Fator R.",
)


def _normalizar_cnae(codigo: object) -> str:
    return "".join(ch for ch in str(codigo or "") if ch.isdigit())


def classificar_cnae(codigo: object, rbt12: float = 0.0) -> DiagnosticoCNAE:
    """Classifica um CNAE e calcula a alíquota efetiva real para o RBT12 dado.

    [CORRIGIDO] Antes a "alíquota inicial" era uma string fixa ("4,0%") que
    valia apenas para a 1ª faixa. Agora, quando o faturamento é conhecido, a
    alíquota exibida é a efetiva daquela empresa.
    """
    limpo = _normalizar_cnae(codigo)

    # Prefixos mais longos vencem: 4712 (minimercado) antes de 47 (comércio).
    regra = REGRA_PADRAO
    melhor = 0
    for candidata in REGRAS:
        for prefixo in candidata.prefixos:
            if limpo.startswith(prefixo) and len(prefixo) > melhor:
                regra, melhor = candidata, len(prefixo)

    tabela = TABELAS[regra.anexo_chave]
    if rbt12 > 0:
        efetiva = aliquota_efetiva(rbt12, tabela)
        rotulo = f"{_pct(efetiva)} (efetiva para RBT12 de {moeda(rbt12)})"
    else:
        rotulo = f"{_pct(tabela[0][1])} (1ª faixa — informe o faturamento)"

    if regra.tem_fator_r and rbt12 > 0:
        alt = aliquota_efetiva(rbt12, ANEXO_V)
        rotulo = f"{rotulo} | Anexo V: {_pct(alt)}"

    return DiagnosticoCNAE(
        anexo=regra.anexo_rotulo,
        aliquota_inicial=rotulo,
        tem_fator_r=regra.tem_fator_r,
        is_minimercado=regra.is_minimercado,
        resumo=regra.resumo,
        dica_engenharia=regra.dica,
    )


# --------------------------------------------------------------------------- #
# 3. Comparador de regimes                                                     #
# --------------------------------------------------------------------------- #
# Lucro Presumido — comércio (presunção de 8% IRPJ / 12% CSLL):
PRESUNCAO_IRPJ_COMERCIO = 0.08
PRESUNCAO_CSLL_COMERCIO = 0.12
ALIQ_IRPJ = 0.15
ADICIONAL_IRPJ = 0.10
LIMITE_ADICIONAL_IRPJ_TRIMESTRAL = 60_000.00
ALIQ_CSLL = 0.09
ALIQ_PIS_CUMULATIVO = 0.0065
ALIQ_COFINS_CUMULATIVO = 0.03


@dataclass(frozen=True, slots=True)
class ComparacaoRegimes:
    faturamento_anual: float
    simples_bruto: float
    simples_otimizado: float
    presumido: float
    economia_monofasico: float
    melhor_regime: str
    diferenca_anual: float
    aliquota_simples_efetiva: float
    aliquota_presumido_efetiva: float
    detalhamento_presumido: dict[str, float]


def comparar_regimes(
    faturamento_mensal: float,
    pct_monofasico: float = 0.0,
    tabela: TabelaAnexo = ANEXO_I,
) -> ComparacaoRegimes:
    """Compara Simples Nacional × Lucro Presumido para um comércio.

    [CORRIGIDO] A função original recebia ``margem_pct`` e ``tipo_lucro``,
    calculava ``margem_efetiva_pct`` e **nunca usava a variável** — os dois
    parâmetros eram código morto. A margem é irrelevante para o Simples e para
    PIS/COFINS/IRPJ presumido (que incidem sobre a receita), então ela foi
    removida da assinatura em vez de fingir que influencia o resultado.

    ``pct_monofasico`` é a parcela da receita com PIS/COFINS já recolhido na
    origem — essa parcela sai da base de PIS/COFINS nos dois regimes.
    """
    fat_anual = max(0.0, faturamento_mensal) * 12
    if fat_anual <= 0:
        return ComparacaoRegimes(0, 0, 0, 0, 0, "Informe um faturamento válido",
                                 0, 0, 0, {})

    fracao_mono = min(max(pct_monofasico, 0.0), 100.0) / 100.0

    # --- Simples Nacional -------------------------------------------------- #
    aliq_simples = aliquota_efetiva(fat_anual, tabela)
    simples_bruto = fat_anual * aliq_simples

    # No Anexo I, PIS (2,76%) + COFINS (12,74%) somam 15,50% da alíquota
    # efetiva. A segregação retira essa fatia proporcionalmente à receita
    # monofásica.
    PARCELA_PIS_COFINS_ANEXO_I = 0.1550
    simples_otimizado = simples_bruto * (1 - fracao_mono * PARCELA_PIS_COFINS_ANEXO_I)
    economia_mono = simples_bruto - simples_otimizado

    # --- Lucro Presumido --------------------------------------------------- #
    base_pis_cofins = fat_anual * (1 - fracao_mono)
    pis = base_pis_cofins * ALIQ_PIS_CUMULATIVO
    cofins = base_pis_cofins * ALIQ_COFINS_CUMULATIVO

    lucro_presumido_irpj = fat_anual * PRESUNCAO_IRPJ_COMERCIO
    irpj = lucro_presumido_irpj * ALIQ_IRPJ
    excedente = max(0.0, lucro_presumido_irpj - LIMITE_ADICIONAL_IRPJ_TRIMESTRAL * 4)
    irpj += excedente * ADICIONAL_IRPJ

    csll = fat_anual * PRESUNCAO_CSLL_COMERCIO * ALIQ_CSLL

    detalhamento = {
        "PIS": pis, "COFINS": cofins, "IRPJ": irpj, "CSLL": csll,
    }
    presumido = sum(detalhamento.values())

    melhor = ("Simples Nacional (com segregação de monofásicos)"
              if simples_otimizado <= presumido else "Lucro Presumido")

    return ComparacaoRegimes(
        faturamento_anual=fat_anual,
        simples_bruto=simples_bruto,
        simples_otimizado=simples_otimizado,
        presumido=presumido,
        economia_monofasico=economia_mono,
        melhor_regime=melhor,
        diferenca_anual=abs(presumido - simples_otimizado),
        aliquota_simples_efetiva=aliq_simples,
        aliquota_presumido_efetiva=presumido / fat_anual,
        detalhamento_presumido=detalhamento,
    )


# --------------------------------------------------------------------------- #
# 4. Desenquadramento retroativo do MEI                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class DiagnosticoMEI:
    limite_proporcional: float
    excesso: float
    pct_excesso: float
    requer_retroativo: bool
    imposto_estimado: float
    encargos_estimados: float
    total_com_encargos: float
    orientacao: str
    selic_utilizada: float


def diagnosticar_mei(
    faturamento_anual: float,
    meses_atividade: int,
    selic_acumulada_aa: float,
    pct_monofasico: float = 55.0,
) -> DiagnosticoMEI:
    """Estima o custo do desenquadramento do MEI por excesso de receita.

    [CORRIGIDO] ``obter_indicadores_bacen()`` era chamado de dentro desta
    função, acoplando regra de negócio a I/O de rede e tornando o cálculo
    impossível de testar. A Selic agora é injetada pelo chamador.
    """
    meses = max(1, min(int(meses_atividade), 12))
    limite = meses * LIMITE_MEI_MENSAL
    fat = max(0.0, faturamento_anual)

    if fat <= limite:
        return DiagnosticoMEI(
            limite_proporcional=limite, excesso=0.0, pct_excesso=0.0,
            requer_retroativo=False, imposto_estimado=0.0, encargos_estimados=0.0,
            total_com_encargos=0.0, selic_utilizada=selic_acumulada_aa,
            orientacao="🟢 **MEI regular:** faturamento dentro do limite proporcional.",
        )

    excesso = fat - limite
    pct_excesso = (excesso / limite) * 100 if limite else 0.0

    aliq_base = aliquota_efetiva(fat, ANEXO_I)
    fracao_mono = min(max(pct_monofasico, 0.0), 100.0) / 100.0
    aliq_efetiva = aliq_base * (1 - fracao_mono * 0.1550)

    if pct_excesso <= 20.0:
        imposto = excesso * aliq_efetiva
        retroativo = False
        orientacao = (
            "🟡 **Excesso de até 20% — desenquadramento a partir de 01/jan do ano seguinte.**\n"
            "Recolhe-se DAS complementar apenas sobre o valor excedente, sem retroação."
        )
    else:
        das_pago = meses * DAS_MEI_MEDIO_MENSAL
        imposto = max(0.0, fat * aliq_efetiva - das_pago)
        retroativo = True
        orientacao = (
            "🔴 **Excesso acima de 20% — desenquadramento RETROATIVO.**\n"
            "O CNPJ é tributado como ME desde janeiro (ou desde a abertura). Toda a "
            "receita do ano vai ao PGDAS-D, compensando-se os DAS-MEI já pagos."
        )

    # Juros de mora ≈ Selic acumulada do período + 1% no mês do pagamento;
    # multa de mora de 0,33% ao dia, limitada a 20%. Aproximação gerencial.
    if retroativo:
        multa_mora = 0.20
        juros = selic_acumulada_aa / 100.0 + 0.01
        encargos = imposto * (multa_mora + juros)
    else:
        encargos = 0.0

    return DiagnosticoMEI(
        limite_proporcional=limite, excesso=excesso, pct_excesso=pct_excesso,
        requer_retroativo=retroativo, imposto_estimado=imposto,
        encargos_estimados=encargos, total_com_encargos=imposto + encargos,
        orientacao=orientacao, selic_utilizada=selic_acumulada_aa,
    )


# --------------------------------------------------------------------------- #
# 5. Precificação da proposta                                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Honorarios:
    base: float
    adicional_cnpjs: float
    adicional_dp: float
    blocos_dp: int
    pontuais: dict[str, float]

    @property
    def mensal(self) -> float:
        return self.base + self.adicional_cnpjs + self.adicional_dp

    @property
    def total_pontual(self) -> float:
        return sum(self.pontuais.values())


def calcular_honorarios(
    num_cnpjs: int, num_pessoas: int, servicos_pontuais: Iterable[tuple[str, float]],
    precos,
) -> Honorarios:
    """Centraliza a regra de preço.

    [CORRIGIDO] A fórmula existia duplicada em dois lugares (na UI, para o
    resumo na tela, e dentro do gerador de PDF). Qualquer reajuste exigiria
    lembrar dos dois — e divergências passariam despercebidas.
    """
    cnpjs = max(1, int(num_cnpjs))
    pessoas = max(0, int(num_pessoas))
    blocos = -(-pessoas // precos.pessoas_por_bloco_dp) if pessoas else 0
    return Honorarios(
        base=precos.honorario_base,
        adicional_cnpjs=(cnpjs - 1) * precos.adicional_por_cnpj,
        adicional_dp=blocos * precos.adicional_por_bloco_dp,
        blocos_dp=blocos,
        pontuais=dict(servicos_pontuais),
    )
