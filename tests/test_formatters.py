from src.core.formatters import (
    moeda,
    percentual,
    sem_acento,
    texto_ou,
    url_google_maps,
    url_whatsapp,
)


def test_moeda_pt_br():
    assert moeda(1234.5) == "R$ 1.234,50"
    assert moeda(1_234_567.89) == "R$ 1.234.567,89"
    assert moeda(0) == "R$ 0,00"
    assert moeda(None) == "R$ 0,00"
    assert moeda(-99.9) == "-R$ 99,90"


def test_percentual():
    assert percentual(0.062) == "6,20%"


def test_sem_acento():
    assert sem_acento("PRESTAÇÃO DE SERVIÇOS CONTÁBEIS") == \
        "PRESTACAO DE SERVICOS CONTABEIS"


def test_texto_ou_trata_none_e_nan():
    assert texto_ou(None) == "Não informado"
    assert texto_ou("None") == "Não informado"
    assert texto_ou("nan") == "Não informado"
    assert texto_ou("  ") == "Não informado"
    assert texto_ou("ok") == "ok"


def test_google_maps_escapa_corretamente():
    url = url_google_maps("Rua São João, 100 & Cia - Sé/SP")
    assert " " not in url and "&query=" in url
    assert "%26" in url  # o '&' do endereço foi escapado, não vira parâmetro


def test_whatsapp_adiciona_ddi():
    url = url_whatsapp("19992853550", "olá")
    assert url.startswith("https://wa.me/5519992853550")


def test_whatsapp_preserva_ddi_existente():
    assert url_whatsapp("5519992853550", "oi").startswith("https://wa.me/5519992853550")


def test_whatsapp_rejeita_numero_curto():
    assert url_whatsapp("1234", "oi") is None


def test_regressao_bug_de_telefones_concatenados():
    """Antes: ``re.sub(r'\\D','', '(19) 3333-4444, (19) 99999-8888')[:11]``
    produzia '1933334444' + dígitos do segundo número — um telefone que não
    existe. Agora cada número é tratado isoladamente."""
    telefones = ["(19) 3333-4444", "(19) 99999-8888"]
    url = url_whatsapp(telefones[0], "oi")
    assert url is not None and "551933334444" in url
