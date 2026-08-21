import pytest

from src.core.tributario import (
    ANEXO_I,
    aliquota_efetiva,
    calcular_honorarios,
    classificar_cnae,
    comparar_regimes,
    diagnosticar_mei,
)


# --------------------------------------------------------------------------- #
# Alíquota efetiva                                                             #
# --------------------------------------------------------------------------- #
def test_primeira_faixa_anexo_i_nao_tem_deducao():
    assert aliquota_efetiva(100_000, ANEXO_I) == pytest.approx(0.04)


def test_segunda_faixa_anexo_i():
    # 300.000 × 7,30% = 21.900 − 5.940 = 15.960 → 5,32%
    assert aliquota_efetiva(300_000, ANEXO_I) == pytest.approx(0.0532, abs=1e-4)


def test_faixa_de_minimercado_tipico():
    # R$ 35 mil/mês = R$ 420 mil/ano, 3ª faixa
    # 420.000 × 9,50% = 39.900 − 13.860 = 26.040 → 6,20%
    assert aliquota_efetiva(420_000, ANEXO_I) == pytest.approx(0.062, abs=1e-4)


def test_aliquota_e_monotonica_ate_a_5a_faixa():
    faixas = [50_000, 200_000, 500_000, 1_000_000, 2_500_000, 3_600_000]
    valores = [aliquota_efetiva(f, ANEXO_I) for f in faixas]
    assert valores == sorted(valores)


def test_faixas_sao_continuas_nas_fronteiras_internas():
    """As parcelas a deduzir existem justamente para não haver salto de carga.
    Verificado nas fronteiras de R$ 180 mil a R$ 1,8 mi."""
    for limite in (180_000, 360_000, 720_000, 1_800_000):
        antes = aliquota_efetiva(limite, ANEXO_I)
        depois = aliquota_efetiva(limite + 1, ANEXO_I)
        assert antes == pytest.approx(depois, abs=1e-6)


def test_descontinuidade_conhecida_na_6a_faixa():
    """QUIRK DA LC 123 (não é bug): na fronteira de R$ 3,6 mi a alíquota
    efetiva do Anexo I CAI de 11,875% para 8,50%, porque a parcela a deduzir
    da 6ª faixa (R$ 378.000) não preserva a continuidade. Documentado aqui
    para que ninguém "corrija" a tabela por engano."""
    assert aliquota_efetiva(3_600_000, ANEXO_I) == pytest.approx(0.11875, abs=1e-5)
    assert aliquota_efetiva(3_600_001, ANEXO_I) == pytest.approx(0.085, abs=1e-5)


@pytest.mark.parametrize("rbt12,esperado", [
    (4_000_000, 0.0955),    # referência publicada
    (4_800_000, 0.11125),   # teto efetivo do Anexo I
    (3_000_000, 0.1139),
])
def test_pontos_de_referencia_publicados(rbt12, esperado):
    assert aliquota_efetiva(rbt12, ANEXO_I) == pytest.approx(esperado, abs=1e-4)


def test_faturamento_zero_nao_divide_por_zero():
    assert aliquota_efetiva(0, ANEXO_I) == 0.0


def test_regressao_aliquota_fixa_era_muito_errada():
    """O código original usava 3,3% fixos para o Simples. Para um minimercado
    de R$ 35 mil/mês a efetiva real é 6,20% — quase o dobro."""
    real = aliquota_efetiva(420_000, ANEXO_I)
    assert real / 0.033 > 1.8


# --------------------------------------------------------------------------- #
# Classificação de CNAE                                                        #
# --------------------------------------------------------------------------- #
def test_minimercado_e_reconhecido():
    diag = classificar_cnae("4712100")
    assert diag.is_minimercado and "Anexo I" in diag.anexo


def test_prefixo_mais_longo_vence():
    """4712 (minimercado) deve ganhar de 47 (comércio genérico)."""
    assert classificar_cnae("4712100").is_minimercado
    assert not classificar_cnae("4744001").is_minimercado


def test_industria_vai_para_anexo_ii():
    assert "Anexo II" in classificar_cnae("1091101").anexo


def test_construcao_civil_vai_para_anexo_iv():
    assert "Anexo IV" in classificar_cnae("4120400").anexo


def test_ti_esta_sujeita_ao_fator_r():
    assert classificar_cnae("6201501").tem_fator_r


def test_cnae_desconhecido_cai_no_padrao():
    diag = classificar_cnae("9999999")
    assert "Anexo III" in diag.anexo and not diag.tem_fator_r


def test_cnae_vazio_nao_quebra():
    assert classificar_cnae(None) is not None
    assert classificar_cnae("") is not None


def test_aliquota_exibida_usa_rbt12_quando_informado():
    sem = classificar_cnae("4712100")
    com = classificar_cnae("4712100", rbt12=420_000)
    assert "1ª faixa" in sem.aliquota_inicial
    assert "6,2" in com.aliquota_inicial.replace(".", ",")


# --------------------------------------------------------------------------- #
# Comparador de regimes                                                        #
# --------------------------------------------------------------------------- #
def test_faturamento_invalido_nao_quebra():
    r = comparar_regimes(0)
    assert r.faturamento_anual == 0 and "válido" in r.melhor_regime


def test_monofasico_reduz_a_carga_do_simples():
    sem = comparar_regimes(35_000, pct_monofasico=0)
    com = comparar_regimes(35_000, pct_monofasico=55)
    assert com.simples_otimizado < sem.simples_otimizado
    assert com.economia_monofasico > 0


def test_sem_monofasico_nao_ha_economia():
    assert comparar_regimes(35_000, 0).economia_monofasico == pytest.approx(0.0)


def test_presumido_detalhado_soma_o_total():
    r = comparar_regimes(35_000, 55)
    assert sum(r.detalhamento_presumido.values()) == pytest.approx(r.presumido)


def test_presumido_tem_os_quatro_tributos():
    r = comparar_regimes(35_000, 0)
    assert set(r.detalhamento_presumido) == {"PIS", "COFINS", "IRPJ", "CSLL"}


def test_adicional_de_irpj_incide_acima_do_limite():
    """Presunção de 8% > R$ 240 mil/ano exige receita > R$ 3 mi."""
    pequeno = comparar_regimes(100_000)     # R$ 1,2 mi/ano
    grande = comparar_regimes(350_000)      # R$ 4,2 mi/ano
    assert grande.aliquota_presumido_efetiva > pequeno.aliquota_presumido_efetiva


def test_regressao_margem_era_codigo_morto():
    """Na versão antiga, mudar a margem de lucro não alterava NADA no
    resultado — os dois impostos eram percentuais fixos da receita."""
    r = comparar_regimes(35_000, 55)
    assert r.aliquota_simples_efetiva != pytest.approx(0.033)
    assert r.aliquota_presumido_efetiva != pytest.approx(0.059)


# --------------------------------------------------------------------------- #
# MEI                                                                          #
# --------------------------------------------------------------------------- #
def test_mei_dentro_do_limite():
    d = diagnosticar_mei(70_000, 12, 10.5)
    assert not d.requer_retroativo and d.excesso == 0 and d.total_com_encargos == 0


def test_limite_proporcional_por_meses():
    assert diagnosticar_mei(0, 6, 10.5).limite_proporcional == pytest.approx(40_500.0)


def test_excesso_ate_20_pct_nao_retroage():
    d = diagnosticar_mei(90_000, 12, 10.5)   # limite 81.000, excesso 11,1%
    assert d.excesso > 0 and not d.requer_retroativo and d.encargos_estimados == 0


def test_excesso_acima_de_20_pct_retroage_com_encargos():
    d = diagnosticar_mei(150_000, 12, 10.5)
    assert d.requer_retroativo and d.encargos_estimados > 0
    assert d.total_com_encargos > d.imposto_estimado


def test_meses_fora_da_faixa_sao_limitados():
    assert diagnosticar_mei(0, 99, 10.5).limite_proporcional == pytest.approx(81_000.0)
    assert diagnosticar_mei(0, 0, 10.5).limite_proporcional == pytest.approx(6_750.0)


def test_selic_e_injetada_nao_buscada_na_rede():
    """Garantia de testabilidade: a função é pura."""
    baixa = diagnosticar_mei(150_000, 12, 5.0)
    alta = diagnosticar_mei(150_000, 12, 15.0)
    assert alta.encargos_estimados > baixa.encargos_estimados


def test_monofasico_reduz_o_imposto_do_mei():
    sem = diagnosticar_mei(150_000, 12, 10.5, pct_monofasico=0)
    com = diagnosticar_mei(150_000, 12, 10.5, pct_monofasico=80)
    assert com.imposto_estimado < sem.imposto_estimado


# --------------------------------------------------------------------------- #
# Honorários                                                                   #
# --------------------------------------------------------------------------- #
class _Precos:
    honorario_base = 350.0
    adicional_por_cnpj = 50.0
    adicional_por_bloco_dp = 50.0
    pessoas_por_bloco_dp = 3


@pytest.mark.parametrize("pessoas,blocos", [
    (0, 0), (1, 1), (3, 1), (4, 2), (6, 2), (7, 3), (10, 4),
])
def test_blocos_de_dp(pessoas, blocos):
    assert calcular_honorarios(1, pessoas, [], _Precos()).blocos_dp == blocos


def test_mensalidade_completa():
    h = calcular_honorarios(3, 4, [("Abertura", 1600.0)], _Precos())
    assert h.adicional_cnpjs == 100.0          # 2 filiais
    assert h.adicional_dp == 100.0             # 2 blocos
    assert h.mensal == 550.0
    assert h.total_pontual == 1600.0


def test_valores_negativos_sao_saneados():
    h = calcular_honorarios(-5, -3, [], _Precos())
    assert h.mensal == 350.0
