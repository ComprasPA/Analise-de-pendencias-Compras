"""Indicadores de mercado exibidos no cabeçalho do Panorama (parâmetros ao
lado do botão de atualizar): cotação do dia (Selic meta, IPCA acumulado em
12 meses e dólar PTAX) e projeções do Boletim Focus para o próximo ano
(IPCA, câmbio e PIB).

Fontes (APIs públicas do Banco Central, sem chave):
  - SGS:   https://api.bcb.gov.br/dados/serie/bcdata.sgs.<codigo>/dados/ultimos/1
  - Focus: https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/

Nada aqui chama st.* - a busca recebe a função de GET por parâmetro (pra
poder ser testada sem rede) e o app.py cuida de cache e de salvar/ler o
último valor na planilha. Se o BCB não responder, o app usa o último valor
salvo e, na falta dele, os valores de referência abaixo.
"""
import datetime
import html
from urllib.parse import quote

import requests

TIMEOUT = 8
JANELA_DIAS = 120  # cobre a série mensal (IPCA) e o fim de semana do dólar

URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={inicio}&dataFinal={fim}"
URL_FOCUS = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoAnuais"
)

# chave -> código da série no SGS
SERIES_SGS = {
    "selic": 432,       # Meta Selic definida pelo Copom (% a.a.)
    "ipca_12m": 13522,  # IPCA acumulado em 12 meses (%)
    "dolar": 1,         # Dólar PTAX venda (R$)
}

# nome do indicador no Focus -> chave
INDICADORES_FOCUS = {
    "IPCA": "focus_ipca",
    "Câmbio": "focus_dolar",
    "PIB Total": "focus_pib",
}

ORDEM = ["selic", "ipca_12m", "dolar", "focus_ipca", "focus_dolar", "focus_pib"]

ROTULOS = {
    "selic": "Selic",
    "ipca_12m": "IPCA 12m",
    "dolar": "Dólar",
    "focus_ipca": "IPCA",
    "focus_dolar": "Dólar",
    "focus_pib": "PIB",
}

FONTES = {
    "selic": "BCB/SGS 432 – meta Selic",
    "ipca_12m": "BCB/SGS 13522 – IPCA acumulado 12 meses",
    "dolar": "BCB/SGS 1 – dólar PTAX venda",
    "focus_ipca": "Boletim Focus – mediana",
    "focus_dolar": "Boletim Focus – mediana",
    "focus_pib": "Boletim Focus – mediana",
}

# Último recurso, se o BCB não responder e nada tiver sido salvo ainda:
# Radar de Compras ed. 05 (semana de 09 a 13/11/2026).
VALORES_REFERENCIA = {
    "selic": {"valor": 13.75, "data": "13/11/2026"},
    "focus_ipca": {"valor": 4.90, "data": "13/11/2026"},
    "focus_dolar": {"valor": 5.40, "data": "13/11/2026"},
    "focus_pib": {"valor": 1.15, "data": "13/11/2026"},
}


def _get_json(get, url):
  resp = get(url, timeout=TIMEOUT)
  resp.raise_for_status()
  return resp.json()


def _numero(valor):
  if isinstance(valor, (int, float)):
    return float(valor)
  return float(str(valor).replace(",", "."))


def buscar_sgs(codigo, get=requests.get, hoje=None):
  """Último valor de uma série do SGS até hoje: {'valor': float, 'data': 'dd/mm/aaaa'}.
  A meta Selic (432) é uma série diária que já traz datas futuras - "ultimos/N"
  devolveria só o futuro. Por isso a busca é por janela de datas, terminando hoje."""
  hoje = hoje or datetime.date.today()
  inicio = hoje - datetime.timedelta(days=JANELA_DIAS)
  url = URL_SGS.format(
      codigo=codigo, inicio=inicio.strftime("%d/%m/%Y"), fim=hoje.strftime("%d/%m/%Y")
  )
  dados = _get_json(get, url)
  validos = []
  for linha in dados:
    data = datetime.datetime.strptime(linha["data"], "%d/%m/%Y").date()
    if data <= hoje:
      validos.append((data, linha))
  if not validos:
    raise ValueError(f"série {codigo} sem observação até {hoje}")
  ultimo = max(validos, key=lambda x: x[0])[1]
  return {"valor": _numero(ultimo["valor"]), "data": ultimo["data"]}


def url_focus(ano):
  nomes = " or ".join(f"Indicador eq '{n}'" for n in INDICADORES_FOCUS)
  filtro = f"({nomes}) and DataReferencia eq '{ano}' and baseCalculo eq 0"
  return (
      f"{URL_FOCUS}?$top=60&$format=json&$orderby=Data%20desc"
      f"&$select=Indicador,Data,DataReferencia,Mediana"
      f"&$filter={quote(filtro)}"
  )


def buscar_focus(ano, get=requests.get):
  """Mediana mais recente do Focus para cada indicador, no ano informado."""
  linhas = _get_json(get, url_focus(ano)).get("value", [])
  linhas = sorted(linhas, key=lambda r: r.get("Data", ""), reverse=True)
  resultado = {}
  for linha in linhas:
    chave = INDICADORES_FOCUS.get(linha.get("Indicador"))
    if not chave or chave in resultado or linha.get("Mediana") is None:
      continue
    a, m, d = linha["Data"][:10].split("-")
    resultado[chave] = {"valor": _numero(linha["Mediana"]), "data": f"{d}/{m}/{a}"}
  return resultado


def buscar_indicadores(ano_focus, get=requests.get):
  """Busca tudo o que conseguir; o que falhar simplesmente fica de fora."""
  resultado = {}
  for chave, codigo in SERIES_SGS.items():
    try:
      resultado[chave] = buscar_sgs(codigo, get)
    except Exception:  # rede, HTTP, JSON inesperado: segue sem esse valor
      pass
  if ano_focus is not None:
    try:
      resultado.update(buscar_focus(ano_focus, get))
    except Exception:
      pass
  return resultado


def mesclar(atuais, salvos, referencia=VALORES_REFERENCIA):
  """Para cada indicador: valor do BCB agora; senão o último salvo; senão a
  referência. Cada item ganha 'origem' ('bcb', 'salvo' ou 'referencia')."""
  saida = {}
  for chave in ORDEM:
    for origem, fonte in (("bcb", atuais), ("salvo", salvos or {}), ("referencia", referencia)):
      item = fonte.get(chave)
      if item and item.get("valor") is not None:
        saida[chave] = {"valor": float(item["valor"]), "data": item.get("data", ""), "origem": origem}
        break
  return saida


def _br(valor, casas=2):
  return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_valor(chave, valor):
  if chave in ("dolar", "focus_dolar"):
    return f"R$ {_br(valor)}"
  if chave == "selic":
    return f"{_br(valor)}% a.a."
  return f"{_br(valor)}%"


def _item_html(chave, item):
  if not item:
    return ""
  dica = f"{FONTES[chave]} · {item['data']}"
  marca = ""
  if item["origem"] == "salvo":
    dica += " · BCB indisponível, último valor salvo"
    marca = "*"
  elif item["origem"] == "referencia":
    dica += " · BCB indisponível, valor de referência (Radar de Compras ed. 05)"
    marca = "*"
  return (
      f'<span class="ind-item" title="{html.escape(dica)}">'
      f'<span class="ind-rot">{html.escape(ROTULOS[chave])}</span> '
      f'<b>{html.escape(formatar_valor(chave, item["valor"]))}{marca}</b></span>'
  )


def _linha_html(titulo, chaves, indicadores):
  itens = [h for h in (_item_html(c, indicadores.get(c)) for c in chaves) if h]
  if not itens:
    return ""
  sep = '<span class="ind-sep">·</span>'
  return f'<div class="ind-linha"><span class="ind-tit">{titulo}</span>{sep.join(itens)}</div>'


def html_parametros(indicadores, ano_focus):
  """Faixa compacta de parâmetros para o cabeçalho (duas linhas)."""
  dolar = indicadores.get("dolar")
  titulo_hoje = f"Hoje ({dolar['data'][:5]})" if dolar and dolar.get("data") else "Hoje"
  linhas = [_linha_html(titulo_hoje, ["selic", "ipca_12m", "dolar"], indicadores)]
  if ano_focus is not None:
    linhas.append(_linha_html(f"Focus {ano_focus}", ["focus_ipca", "focus_dolar", "focus_pib"], indicadores))
  corpo = "".join(l for l in linhas if l)
  return f'<div class="ind-mercado">{corpo}</div>' if corpo else ""
