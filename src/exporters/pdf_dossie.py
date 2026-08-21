"""Geração dos PDFs de dossiê, cartão CNPJ e proposta comercial."""

from __future__ import annotations

from datetime import date

from ..config import settings
from ..core.cnpj import formatar as formatar_cnpj
from ..core.formatters import moeda, texto_ou
from ..core.models import Empresa
from ..core.tributario import Honorarios
from .pdf_base import DocumentoPDF

AVISO_COMPLIANCE = (
    "Este documento reflete exclusivamente dados cadastrais públicos (CNPJ). "
    "NÃO constitui certidão negativa de débitos. A regularidade fiscal, do FGTS "
    "e trabalhista exige emissão formal junto a RFB/PGFN (e-CAC), Caixa e TST."
)


def gerar_cartao_cnpj(empresa: Empresa) -> bytes:
    pdf = DocumentoPDF()
    pdf.add_page()

    pdf.fonte("B", 10)
    pdf.linha(5, "REPÚBLICA FEDERATIVA DO BRASIL", align="C")
    pdf.fonte("B", 12)
    pdf.linha(6, "CADASTRO NACIONAL DA PESSOA JURÍDICA", align="C")
    pdf.fonte("B", 9)
    pdf.linha(5, "COMPROVANTE DE INSCRIÇÃO E DE SITUAÇÃO CADASTRAL", align="C")
    pdf.ln(4)

    pdf.fonte("", 8)
    largura = pdf.w - 20
    pdf.cell(largura * 0.63, 9,
             pdf.txt(f"NÚMERO DE INSCRIÇÃO: {formatar_cnpj(empresa.cnpj)} "
                     f"({empresa.matriz_filial})"), border=1)
    pdf.linha(9, f"DATA DE ABERTURA: {empresa.data_abertura}",
              largura=largura * 0.37, border=1)

    for rotulo, valor in (
        ("NOME EMPRESARIAL", empresa.razao_social),
        ("NOME FANTASIA", empresa.nome_fantasia),
        ("ATIVIDADE ECONÔMICA PRINCIPAL", empresa.cnae_principal_str),
    ):
        pdf.paragrafo(6, f"{rotulo}: {valor}", border=1)

    secundarias = "; ".join(str(a) for a in empresa.atividades_secundarias) or "Não informada"
    pdf.paragrafo(5, f"ATIVIDADES ECONÔMICAS SECUNDÁRIAS: {secundarias}", border=1)
    pdf.paragrafo(6, f"NATUREZA JURÍDICA: {empresa.natureza_juridica}", border=1)
    pdf.paragrafo(6, f"ENDEREÇO: {empresa.endereco.linha_completa} "
                     f"[IBGE: {empresa.endereco.cod_ibge}]", border=1)

    pdf.cell(largura * 0.63, 9, pdf.txt(f"E-MAIL: {empresa.email_str}"), border=1)
    pdf.linha(9, f"TELEFONE: {empresa.telefone_str}", largura=largura * 0.37, border=1)
    pdf.cell(largura * 0.63, 9,
             pdf.txt(f"SITUAÇÃO CADASTRAL: {empresa.situacao.situacao_receita}"), border=1)
    pdf.linha(9, f"PORTE: {empresa.porte}", largura=largura * 0.37, border=1)

    pdf.ln(3)
    pdf.fonte("I", 7)
    pdf.paragrafo(4, "Documento gerado a partir de bases públicas "
                     f"({', '.join(empresa.fontes)}). Não substitui o comprovante "
                     "oficial emitido pela Receita Federal.")
    return pdf.bytes()


def gerar_dossie(empresa: Empresa) -> bytes:
    pdf = DocumentoPDF()
    pdf.add_page()

    pdf.set_fill_color(*settings.emissor.cor_marca)
    pdf.set_text_color(255, 255, 255)
    pdf.fonte("B", 14)
    pdf.linha(10, "DOSSIÊ CONTÁBIL E DIAGNÓSTICO DE ONBOARDING", align="C", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.fonte("B", 11)
    pdf.linha(6, empresa.razao_social)
    pdf.fonte("", 9)
    pdf.linha(5, f"CNPJ: {formatar_cnpj(empresa.cnpj)} | Fantasia: {empresa.nome_fantasia}")
    pdf.linha(5, f"Contato: {empresa.telefone_str} | {empresa.email_str}")
    pdf.linha(5, f"Situação: {empresa.situacao.situacao_receita} | "
                 f"Porte: {empresa.porte} | Capital: {moeda(empresa.capital_social)}")
    pdf.linha(5, f"Endereço: {empresa.endereco.linha_completa}")
    pdf.linha(5, f"Regime atual: {empresa.regime}")
    pdf.ln(3)

    # 1 ------------------------------------------------------------------ #
    pdf.secao("1. Situação cadastral verificada")
    pdf.linha(5, empresa.situacao.rotulo_receita)
    pdf.fonte("B", 8)
    pdf.linha(5, "NÃO verificado neste relatório (exige emissão formal):")
    pdf.fonte("", 8)
    for item in empresa.situacao.pendentes_de_verificacao:
        pdf.linha(4, f"  • {item}")
    pdf.ln(3)

    # 2 ------------------------------------------------------------------ #
    pdf.secao("2. Diagnóstico tributário e oportunidade fiscal")
    if empresa.atividade_principal:
        diag = empresa.atividade_principal.diagnostico
        pdf.linha(5, f"CNAE principal: {empresa.cnae_principal_str}")
        pdf.linha(5, f"Enquadramento: {diag.anexo}")
        pdf.linha(5, f"Alíquota: {diag.aliquota_inicial}")
        pdf.paragrafo(5, f"Orientação: {diag.dica_engenharia}")
    else:
        pdf.linha(5, "CNAE principal não localizado nas bases consultadas.")
    pdf.ln(3)

    # 3 ------------------------------------------------------------------ #
    pdf.secao("3. Quadro societário (QSA)")
    if empresa.socios:
        for socio in empresa.socios:
            pdf.linha(5, f"• {socio.nome} — {socio.qualificacao}")
        if empresa.tem_risco_societario:
            pdf.fonte("B", 8)
            pdf.paragrafo(4, "ALERTA: múltiplos sócios. Verificar participação ≥10% em "
                             "outras empresas do Simples — o faturamento é somado para o "
                             "limite de R$ 4,8 milhões/ano (art. 3º, §4º, LC 123/2006).")
            pdf.fonte("", 9)
    else:
        pdf.linha(5, "Empresário individual / MEI sem sócios no QSA.")
    pdf.ln(3)

    # 4 ------------------------------------------------------------------ #
    pdf.secao("4. Checklist de onboarding")
    pdf.fonte("", 8)
    for item in (
        ("Varejo/minimercado: solicitar relatório de vendas por NCM do totem "
         "para segregar PIS/COFINS monofásico e ICMS-ST."),
        "Serviços: levantar folha dos últimos 12 meses para apurar o Fator R.",
        "Validar o somatório de receita dos sócios em outras empresas do Simples.",
        "Emitir CND (e-CAC), CRF (Caixa) e CNDT (TST) com o certificado do cliente.",
        "Confirmar inscrições estadual e municipal ativas.",
    ):
        pdf.paragrafo(4, f"[ ] {item}")

    pdf.ln(4)
    pdf.fonte("I", 7)
    pdf.paragrafo(4, AVISO_COMPLIANCE)
    pdf.paragrafo(4, f"Emitido em {date.today():%d/%m/%Y} | Fontes: "
                     f"{', '.join(empresa.fontes) or 'n/d'}")
    return pdf.bytes()


def gerar_proposta(empresa: Empresa, honorarios: Honorarios,
                   incluir_dp: bool = True) -> bytes:
    precos, emissor = settings.precos, settings.emissor
    pdf = DocumentoPDF()
    pdf.add_page()

    pdf.set_fill_color(*emissor.cor_marca)
    pdf.rect(0, 0, 210, 16, "F")
    pdf.set_xy(0, 4)
    pdf.set_text_color(255, 255, 255)
    pdf.fonte("B", 11)
    pdf.linha(8, "MERCABILIZA — CONTABILIDADE PARA MINIMERCADOS", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    pdf.fonte("B", 14)
    pdf.linha(8, "PROPOSTA DE PRESTAÇÃO DE SERVIÇOS CONTÁBEIS")
    pdf.fonte("", 9)
    pdf.linha(5, f"Cliente: {empresa.razao_social} | CNPJ: {formatar_cnpj(empresa.cnpj)}")
    pdf.linha(5, f"Cidade/UF: {empresa.endereco.municipio}/{empresa.endereco.uf} "
                 f"| Contato: {texto_ou(empresa.telefone_principal, 'a confirmar')}")
    pdf.ln(4)

    pdf.secao("Sobre a Mercabiliza")
    pdf.fonte("", 8)
    pdf.paragrafo(4,
        "Especialista em soluções contábeis para minimercados autônomos, a Mercabiliza "
        "apoia operadores com inteligência contábil, segurança trabalhista e estratégias "
        "que impulsionam o crescimento: contabilidade focada em performance, análises "
        "tributárias personalizadas, departamento pessoal preventivo e processos "
        "otimizados com tecnologia.")
    pdf.ln(3)

    pdf.secao("1. Escopo dos serviços")
    blocos = [
        ("1.1 ÁREA CONTÁBIL", [
            "Classificação, registro e escrituração de todas as operações financeiras e patrimoniais.",
            "Elaboração do Balanço Patrimonial, DRE e apuração de resultados.",
            "Entrega das obrigações acessórias contábeis (ECD/ECF quando aplicável).",
        ]),
        ("1.2 ÁREA FISCAL", [
            "Escrituração fiscal e apuração do Simples Nacional com segregação de PIS/COFINS monofásico.",
            "Elaboração e entrega de SPED, DCTF, EFD-Reinf, GIA, DAS e DASN.",
            "Atendimento consultivo para planejamento tributário de bebidas e conveniência.",
        ]),
    ]
    if incluir_dp:
        blocos.append(("1.3 DEPARTAMENTO PESSOAL", [
            "Gestão de empregados, admissões, rescisões e folha em conformidade com a CLT.",
            "Emissão de guias de encargos (INSS, FGTS, IRRF) e transmissão de eSocial/DCTFWeb.",
        ]))

    for titulo, itens in blocos:
        pdf.fonte("B", 8)
        pdf.linha(5, titulo)
        pdf.fonte("", 8)
        for item in itens:
            pdf.paragrafo(4, f"• {item}")
        pdf.ln(1)

    pdf.secao("2. Investimento e honorários")
    pdf.fonte("", 9)
    pdf.linha(5, f"• Honorários recorrentes (mensalidade base): {moeda(honorarios.base)} / mês")
    if honorarios.adicional_cnpjs > 0:
        pdf.linha(5, f"• Adicional por unidades/CNPJs: {moeda(honorarios.adicional_cnpjs)} / mês")
    if honorarios.adicional_dp > 0:
        pdf.linha(5, f"• Adicional Departamento Pessoal ({honorarios.blocos_dp} bloco(s)): "
                     f"{moeda(honorarios.adicional_dp)} / mês")
    pdf.fonte("B", 10)
    pdf.linha(7, f"TOTAL MENSAL RECORRENTE: {moeda(honorarios.mensal)} / mês")
    pdf.fonte("", 9)

    if honorarios.pontuais:
        pdf.ln(2)
        pdf.fonte("B", 9)
        pdf.linha(5, "Serviços pontuais / taxa única de implantação:")
        pdf.fonte("", 9)
        for nome, valor in honorarios.pontuais.items():
            pdf.linha(5, f"• {nome}: {moeda(valor)} (parcela única)")
        pdf.fonte("B", 9)
        pdf.linha(6, f"Total pontual: {moeda(honorarios.total_pontual)}")
        pdf.fonte("", 9)

    pdf.ln(2)
    pdf.fonte("I", 8)
    pdf.paragrafo(4,
        "Serviços extras como IRPF, alterações contratuais complexas e licenças "
        "específicas serão cotados à parte. Após o aceite, enviaremos o Contrato de "
        "Prestação de Serviços formal.")
    pdf.ln(4)

    pdf.fonte("B", 9)
    pdf.linha(4, f"{emissor.nome} — {emissor.cargo}")
    pdf.fonte("", 8)
    pdf.linha(4, f"Telefone: {emissor.telefone} | E-mail: {emissor.email}")
    pdf.linha(4, f"Proposta emitida em {date.today():%d/%m/%Y} — válida por "
                 f"{precos.validade_proposta_dias} dias.")
    return pdf.bytes()
