import requests

import indicadores_mercado as im


class FakeResp:
  def __init__(self, dados, status=200):
    self._dados = dados
    self.status_code = status

  def raise_for_status(self):
    if self.status_code >= 400:
      raise requests.HTTPError(str(self.status_code))

  def json(self):
    return self._dados


FOCUS = {"value": [
    {"Indicador": "IPCA", "Data": "2026-11-06", "DataReferencia": "2027", "Mediana": 4.95},
    {"Indicador": "IPCA", "Data": "2026-11-13", "DataReferencia": "2027", "Mediana": 4.9},
    {"Indicador": "Câmbio", "Data": "2026-11-13", "DataReferencia": "2027", "Mediana": 5.4},
    {"Indicador": "PIB Total", "Data": "2026-11-13", "DataReferencia": "2027", "Mediana": 1.15},
]}


def fake_get(falhar=()):
  def get(url, timeout=None):
    for trecho in falhar:
      if trecho in url:
        raise requests.ConnectionError("sem rede")
    if "olinda" in url:
      return FakeResp(FOCUS)
    if "sgs.432/" in url:
      return FakeResp([{"data": "16/11/2026", "valor": "15.00"}])
    if "sgs.13522/" in url:
      return FakeResp([{"data": "01/10/2026", "valor": "4.68"}])
    if "sgs.1/" in url:
      return FakeResp([{"data": "16/11/2026", "valor": "5.3214"}])
    raise AssertionError(url)
  return get


def test_busca_todos_os_indicadores():
  r = im.buscar_indicadores(2027, fake_get())
  assert r["selic"] == {"valor": 15.0, "data": "16/11/2026"}
  assert r["ipca_12m"]["valor"] == 4.68
  assert r["dolar"]["valor"] == 5.3214
  # Focus: pega a mediana da data mais recente
  assert r["focus_ipca"] == {"valor": 4.9, "data": "13/11/2026"}
  assert r["focus_dolar"]["valor"] == 5.4
  assert r["focus_pib"]["valor"] == 1.15


def test_falha_de_uma_fonte_nao_derruba_as_outras():
  r = im.buscar_indicadores(2027, fake_get(falhar=["sgs.1/", "olinda"]))
  assert set(r) == {"selic", "ipca_12m"}


def test_url_focus_filtra_ano_e_indicadores():
  url = im.url_focus(2027)
  assert "DataReferencia%20eq%20%272027%27" in url
  assert "C%C3%A2mbio" in url and "PIB%20Total" in url


def test_mesclar_prefere_bcb_depois_salvo_depois_referencia():
  atuais = {"dolar": {"valor": 5.32, "data": "16/11/2026"}}
  salvos = {"selic": {"valor": 15.0, "data": "14/11/2026"}, "dolar": {"valor": 5.1, "data": "01/11/2026"}}
  r = im.mesclar(atuais, salvos)
  assert r["dolar"]["origem"] == "bcb" and r["dolar"]["valor"] == 5.32
  assert r["selic"]["origem"] == "salvo"
  assert r["focus_ipca"]["origem"] == "referencia" and r["focus_ipca"]["valor"] == 4.9
  assert "ipca_12m" not in r  # sem nenhuma fonte, fica de fora


def test_formatacao_pt_br():
  assert im.formatar_valor("dolar", 5.3214) == "R$ 5,32"
  assert im.formatar_valor("selic", 13.75) == "13,75% a.a."
  assert im.formatar_valor("focus_pib", 1.15) == "1,15%"


def test_html_parametros():
  ind = im.mesclar(im.buscar_indicadores(2027, fake_get()), {})
  h = im.html_parametros(ind, 2027)
  assert "Hoje (16/11)" in h and "Focus 2027" in h
  assert "R$ 5,32" in h and "15,00% a.a." in h and "4,90%" in h
  assert "*" not in h  # tudo veio do BCB, sem marca de valor antigo


def test_html_marca_valor_que_nao_veio_do_bcb():
  h = im.html_parametros(im.mesclar({}, {}), 2027)
  assert "13,75% a.a.*" in h and "Radar de Compras" in h


def test_sgs_ignora_data_futura_e_pega_o_ultimo_valor_ate_hoje():
  import datetime

  def get(url, timeout=None):
    return FakeResp([
        {"data": "05/11/2026", "valor": "13.75"},
        {"data": "08/12/2026", "valor": "13.25"},  # reunião futura já agendada
    ])

  obs = im.buscar_sgs(432, get, hoje=datetime.date(2026, 11, 16))
  assert obs == {"valor": 13.75, "data": "05/11/2026"}
