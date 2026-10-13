"""Logica pura do relatorio "Criticidade das Solicitacoes": uma linha por
Solicitacao (SC), montada a partir do DataFrame ja processado por
logica_panorama.processar_panorama (aba Solicitacoes + Criticidade). Filtros
e agregacoes (KPIs, evolucao mensal, tabela por centro de custo).

Sem chamadas st.* nem I/O - so recebe/devolve DataFrames, pra poder ser
testada sem o Streamlit (ver tests/).

A unidade e a Solicitacao, nao a cotacao: nem toda compra tem cotacao
(Compras direta nao tem codigo de cotacao na aba Solicitacoes), mas toda SC
tem uma criticidade. Os codigos de cotacao da SC aparecem como informacao.
"""
import pandas as pd

SEM_CRITICIDADE = "Sem criticidade"
CATS = ["Rotineira", "Compras direta", "Emergencial", "Correção de Processo", SEM_CRITICIDADE]
MESES_NOME = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
    "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
    "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro",
}
MESES_ABREV = {
    "01": "jan", "02": "fev", "03": "mar", "04": "abr", "05": "mai", "06": "jun",
    "07": "jul", "08": "ago", "09": "set", "10": "out", "11": "nov", "12": "dez",
}

_CAT_POR_UPPER = {c.upper(): c for c in CATS if c != SEM_CRITICIDADE}

# Do mais grave pro menos: o status da SC e o do item mais atrasado dela.
_ORDEM_STATUS = ["Fora do Prazo", "Atenção", "No Prazo", "Atendidas"]


def _chave_sc(serie):
  return serie.astype(str).str.split(".").str[0].str.strip()


def _status_da_sc(status_itens):
  presentes = set(status_itens)
  for status in _ORDEM_STATUS:
    if status in presentes:
      return status
  return next(iter(presentes), "")


def preparar_solicitacoes(df_proc):
  """Uma linha por SC: colunas sol, cot, crit, cc, desc, comp, status, itens,
  dt, ano, mes, ym. Data = Data Aprovacao (cai pra Data Emissao quando a
  aprovacao esta vazia/invalida); criticidade fora das 4 conhecidas
  (vazia, "NAO CLASSIFICADO"...) vira "Sem criticidade"."""
  df = df_proc.copy()
  df["_sol"] = _chave_sc(df["SOLICITAÇÃO"])
  df = df[df["_sol"].ne("") & df["_sol"].ne("nan")]

  aprovacao = pd.to_datetime(df.get("DATA APROVACAO"), dayfirst=True, errors="coerce")
  emissao = pd.to_datetime(df["DATA EMISSAO"], errors="coerce")
  df["_dt"] = aprovacao.fillna(emissao)
  df = df.dropna(subset=["_dt"])

  df["_crit"] = (
      df["CRITICIDADE"].fillna("").astype(str).str.strip().str.upper()
      .map(_CAT_POR_UPPER).fillna(SEM_CRITICIDADE)
  )
  df["_cot"] = df["COTAÇÃO"].fillna("").astype(str).str.strip()
  df["_desc"] = df["DESCRICAO"].fillna("").astype(str).str.strip()

  agrupado = df.groupby("_sol", sort=False)
  saida = pd.DataFrame({
      "sol": agrupado["_sol"].first(),
      "cot": agrupado["_cot"].agg(lambda s: ", ".join(dict.fromkeys(c for c in s if c))),
      "crit": agrupado["_crit"].first(),
      "cc": agrupado["CC_clean"].first().astype(str),
      "desc": agrupado["_desc"].first(),
      "comp": agrupado["Comprador_Resp"].first().astype(str),
      "status": agrupado["Status_Detalhado"].agg(_status_da_sc),
      "itens": agrupado.size(),
      "dt": agrupado["_dt"].min(),
  }).reset_index(drop=True)

  saida["ano"] = saida["dt"].dt.strftime("%Y")
  saida["mes"] = saida["dt"].dt.strftime("%m")
  saida["ym"] = saida["dt"].dt.strftime("%Y-%m")
  return saida


def _casa_busca(df, termo):
  termo = (termo or "").strip().lower()
  if not termo:
    return pd.Series(True, index=df.index)
  palheiro = (df["desc"] + " " + df["comp"] + " " + df["cot"] + " " + df["sol"]).str.lower()
  return palheiro.str.contains(termo, regex=False)


def aplicar_filtros(df, anos=(), meses=(), ccs=(), crits=(), comps=(), busca="", ignorar_cc_crit=False):
  """Filtros vazios = sem filtro. ignorar_cc_crit=True e o recorte usado no
  detalhe de um centro de custo (respeita ano/mes/comprador/busca, mas nao
  os filtros globais de centro de custo e criticidade)."""
  mascara = pd.Series(True, index=df.index)
  if anos:
    mascara &= df["ano"].isin(anos)
  if meses:
    mascara &= df["mes"].isin(meses)
  if comps:
    mascara &= df["comp"].isin(comps)
  if not ignorar_cc_crit:
    if ccs:
      mascara &= df["cc"].isin(ccs)
    if crits:
      mascara &= df["crit"].isin(crits)
  mascara &= _casa_busca(df, busca)
  return df[mascara]


def contagem_por_criticidade(df):
  contagem = df["crit"].value_counts()
  return {cat: int(contagem.get(cat, 0)) for cat in CATS}


def evolucao_mensal(df):
  """DataFrame indexado por 'AAAA-MM' (ordenado) com uma coluna por criticidade."""
  if df.empty:
    return pd.DataFrame(columns=CATS)
  tabela = df.groupby(["ym", "crit"]).size().unstack(fill_value=0)
  return tabela.reindex(columns=CATS, fill_value=0).sort_index()


def agregado_por_cc(df):
  """Uma linha por centro de custo: Total, contagem e % de cada criticidade."""
  colunas = ["cc", "Total"] + CATS + [f"% {c}" for c in CATS]
  if df.empty:
    return pd.DataFrame(columns=colunas)
  contagens = df.groupby(["cc", "crit"]).size().unstack(fill_value=0)
  contagens = contagens.reindex(columns=CATS, fill_value=0)
  contagens["Total"] = contagens.sum(axis=1)
  for cat in CATS:
    contagens[f"% {cat}"] = (contagens[cat] / contagens["Total"] * 100).round(1)
  contagens = contagens.sort_values("Total", ascending=False).reset_index()
  return contagens[colunas]


def rotulo_mes(ym):
  ano, mes = ym.split("-")
  return f"{MESES_ABREV[mes]}/{ano[2:]}"
