"""Logica pura de transformacao/calculo do Panorama de Requisicoes Pendentes,
extraida de app.py para poder ser testada sem depender do runtime do
Streamlit (session_state, st.cache_data, etc).

Cobre: normalizacao de Centro de Custo e Comprador responsavel, join de
Criticidade (aba separada, alimentada manualmente enquanto o TOTVS nao
carrega esse campo), calculo de idade (Days) e classificacao de
aging/SLA, marcacao de Tem_Pedido (propria linha OU aba Pedidos) e
separacao do backlog "em aberto", alem do snapshot diario usado no
comparativo historico.

Nenhuma funcao aqui chama st.* nem faz I/O de rede/planilha - so recebe
DataFrames/valores ja carregados (por quem os obteve, streamlit ou teste)
e devolve DataFrames/valores calculados. A logica foi movida de app.py
sem alteracoes de comportamento.
"""
import pandas as pd

COL_SC = "SOLICITAÇÃO"
COL_CC = "CENTRO DE CUSTO"
COL_DT_EMISSAO = "DATA EMISSAO"
COL_PEDIDO_NUM = "PEDIDO"
COL_CRITICIDADE = "CRITICIDADE"
COL_COTACAO = "COTAÇÃO"

MAPA_COMPRADORES = {
    "1225": "Sílvio",
    "1235": "Sílvio",
    "1244": "Sílvio",
    "1241": "Sílvio",
    "1245": "Sílvio",
    "1238": "Ednilson",
    "1243": "Ednilson",
    "1239": "Ednilson",
    "1232": "Ednilson",
}

# Status manuais lançados no Portal do Comprador (nunca mexidos por aqui,
# só lidos) - uma Solicitação nesses estados não entra no backlog "em
# aberto" deste painel. REVISAR é escrito pelo script
# atualizar_pendencias_abertas.py quando a Solicitação não aparece mais no
# browse "Pendências SC" do TOTVS nem tem Pedido - sinal de que fechou por
# algum caminho que a gente ainda não sabe qual, e o comprador precisa
# checar (rejeitou? virou contrato? etc).
STATUS_FORA_DO_BACKLOG = {"REJEITADO", "CONTRATO", "REVISAR"}

# Limite de SLA (dias) por criticidade - mesmo usado nos cartões "SLA Médio".
# Serve de base pra classificar a idade de um item ainda sem Pedido em
# No Prazo/Atenção/Fora do Prazo (ver classificar_aging).
LIMITE_SLA_DIAS = {"EMERGENCIAL": 3, "ROTINEIRA": 15}
LIMITE_SLA_PADRAO = 15

COMPRADORES_SNAPSHOT = ["Ednilson", "Dayana", "Sílvio"]


def classificar_aging(row, col_criticidade=COL_CRITICIDADE):
  limite = LIMITE_SLA_DIAS.get(
      str(row[col_criticidade]).strip().upper(), LIMITE_SLA_PADRAO
  )
  dias = row["Days"]
  if dias > limite:
    return "Fora do Prazo"
  elif dias >= limite * 0.7:
    return "Atenção"
  else:
    return "No Prazo"


def processar_panorama(df, df_criticidade, df_pedidos, hoje):
  """Recebe os 3 DataFrames crus (Solicitacoes, Criticidade, Pedidos) e a
  data base (pd.Timestamp), devolve um dict com tudo que app.py precisa
  pra renderizar: o df enriquecido, o recorte "em aberto", os totais e o
  snapshot do dia (pra comparativo histórico)."""
  df = df.copy()
  df.columns = df.columns.astype(str).str.strip()

  col_sc = COL_SC
  col_cc = COL_CC
  col_dt_emissao = COL_DT_EMISSAO
  col_pedido_num = COL_PEDIDO_NUM
  col_criticidade = COL_CRITICIDADE
  col_cotacao = COL_COTACAO

  df[col_dt_emissao] = pd.to_datetime(
      df[col_dt_emissao], errors="coerce", dayfirst=True
  )

  df["CC_clean"] = (
      pd.to_numeric(df[col_cc], errors="coerce")
      .fillna(df[col_cc])
      .astype(str)
      .str.split(".")
      .str[0]
      .str.strip()
  )
  # Qualquer Centro de Custo que não esteja explicitamente mapeado pra
  # Sílvio ou Ednilson acima é da Dayana.
  df["Comprador_Resp"] = df["CC_clean"].map(MAPA_COMPRADORES).fillna("Dayana")

  # Criticidade vem de uma aba separada ("Criticidade_Solicitacoes"),
  # alimentada manualmente enquanto o TOTVS não carrega esse campo (troca
  # de sistema em andamento - ver atualizar_criticidade.py). Faz join pelo
  # número da Solicitação; o que ainda não tem correspondência fica "" -
  # some naturalmente dos gauges de Rotineira/Emergencial até o próximo
  # arquivo de Cotações preencher.
  chave_solic = df[col_sc].astype(str).str.split(".").str[0].str.strip()
  mapa_criticidade = (
      df_criticidade.dropna(subset=["Solicitacao"])
      .set_index("Solicitacao")["Criticidade"]
      .to_dict()
  )
  df[col_criticidade] = chave_solic.map(mapa_criticidade).fillna("")

  # Número da Cotação já vem pronto na própria aba Solicitacoes (coluna
  # COTAÇÃO) - nem toda Solicitação teve cotação aberta, então fica ""
  # quando não há. Sem join nenhum, é só normalizar (mesma defesa contra
  # ".0" de coluna numérica usada em CC_clean acima) e completar com zero
  # à esquerda - o código de Cotação é sempre 6 dígitos, mas quando a
  # célula vira número real no Excel/Sheets (em vez de texto) o zero à
  # esquerda se perde (ex: "021227" vira "21227").
  if col_cotacao in df.columns:
    cotacao = (
        df[col_cotacao].fillna("").astype(str).str.split(".").str[0].str.strip()
    )
    eh_numerica = cotacao.str.match(r"^\d+$") & (cotacao != "")
    df[col_cotacao] = cotacao.where(~eh_numerica, cotacao.str.zfill(6))
  else:
    df[col_cotacao] = ""

  df["Days"] = (
      (hoje - df[col_dt_emissao]).dt.days.clip(lower=0).fillna(0).astype(int)
  )

  # Pedido Gerado = Atendida, sempre - seja porque a própria célula
  # PEDIDO da Solicitação já tem número, seja porque já existe uma linha
  # correspondente na aba Pedidos (a "baixa" oficial). Os dois sinais se
  # complementam: a célula pode estar preenchida antes da aba Pedidos
  # notar, ou vice-versa.
  s_ped = df[col_pedido_num].dropna().astype(str).str.strip()
  pedido_na_propria_linha = (
      s_ped.str.contains(r"\d", regex=True)
      & (s_ped != "")
      & (s_ped.str.upper() != "NAN")
  ).reindex(df.index, fill_value=False)

  chave_prod = df["PRODUTO"].astype(str).str.split(".").str[0].str.strip()
  chave_solic_produto = chave_solic + "|" + chave_prod
  if not df_pedidos.empty and "SOLICITAÇÃO" in df_pedidos.columns and "PRODUTO" in df_pedidos.columns:
    chaves_pedidos = set(
        df_pedidos["SOLICITAÇÃO"].astype(str).str.split(".").str[0].str.strip()
        + "|"
        + df_pedidos["PRODUTO"].astype(str).str.split(".").str[0].str.strip()
    )
  else:
    chaves_pedidos = set()
  pedido_na_aba_pedidos = chave_solic_produto.isin(chaves_pedidos)

  df["Tem_Pedido"] = pedido_na_propria_linha | pedido_na_aba_pedidos

  # Fora do backlog "em aberto": tem Pedido gerado, OU está num dos
  # status manuais/de revisão que tiram a Solicitação da fila (ver
  # STATUS_FORA_DO_BACKLOG). O resto é o que realmente ainda aguarda
  # compra, e aí sim entra na classificação de idade.
  status_fechado = (
      df["STATUS"].astype(str).str.strip().str.upper().isin(STATUS_FORA_DO_BACKLOG)
  )
  df["Status_Detalhado"] = pd.Series("Atendidas", index=df.index).where(
      df["Tem_Pedido"] | status_fechado, None
  )
  mask_sem_pedido = df["Status_Detalhado"].isna()
  df.loc[mask_sem_pedido, "Status_Detalhado"] = df.loc[mask_sem_pedido].apply(
      classificar_aging, axis=1
  )

  df_aberto = df[df["Status_Detalhado"] != "Atendidas"].copy()
  df_aberto = df_aberto.dropna(subset=[col_sc])
  df_aberto[col_sc] = (
      df_aberto[col_sc].astype(str).str.split(".").str[0].str.zfill(6)
  )

  total_linhas_aberto = int(len(df_aberto))
  unique_scs_aberto = df_aberto.drop_duplicates(subset=[col_sc]).copy()
  total_sc_unicas_aberto = int(len(unique_scs_aberto))

  # --- CORREÇÃO: Contagem de itens sem pedido restrita aos itens EM ABERTO ---
  sem_pedido_total = int(
      (~df_aberto["Tem_Pedido"].fillna(False).astype(bool)).sum()
  )

  # SLA médio só faz sentido pra itens ainda em aberto - "Days" mede idade
  # desde a Solicitação, e uma vez com Pedido isso deixa de ser uma
  # espera de compra (o acompanhamento daí em diante é no Portal Gestão
  # de Compras, não aqui).
  df_geral_crit = df[df["Status_Detalhado"] != "Atendidas"].copy()

  if col_criticidade:
    df_geral_crit = df_geral_crit[
        df_geral_crit[col_criticidade]
        .astype(str)
        .str.upper()
        .isin(["ROTINEIRA", "EMERGENCIAL"])
    ]

  mean_rot = (
      df_geral_crit[
          df_geral_crit[col_criticidade].astype(str).str.upper() == "ROTINEIRA"
      ]["Days"].mean()
      if col_criticidade and not df_geral_crit.empty
      else float("nan")
  )
  mean_emg = (
      df_geral_crit[
          df_geral_crit[col_criticidade].astype(str).str.upper() == "EMERGENCIAL"
      ]["Days"].mean()
      if col_criticidade and not df_geral_crit.empty
      else float("nan")
  )

  sla_geral_rot = int(round(mean_rot, 0)) if not pd.isna(mean_rot) else 0
  sla_geral_emg = int(round(mean_emg, 0)) if not pd.isna(mean_emg) else 0

  snapshot_atual = {
      "total_scs_aberto": total_sc_unicas_aberto,
      "total_linhas_aberto": total_linhas_aberto,
      "sem_pedido_total": sem_pedido_total,
      "compradores": {},
  }

  for comp in COMPRADORES_SNAPSHOT:
    df_c = df[df["Comprador_Resp"] == comp]
    df_c_aberto = df_c[df_c["Status_Detalhado"] != "Atendidas"]

    sem_ped_comp = int(
        (~df_c_aberto["Tem_Pedido"].fillna(False).astype(bool)).sum()
    )
    pedidos_emitidos_comp = int(
        df_c["Tem_Pedido"].fillna(False).astype(bool).sum()
    )
    snapshot_atual["compradores"][comp] = {
        "total": int(len(df_c)),
        "sem_pedido": sem_ped_comp,
        "comprados": pedidos_emitidos_comp,
    }

  return {
      "df": df,
      "df_aberto": df_aberto,
      "unique_scs_aberto": unique_scs_aberto,
      "total_linhas_aberto": total_linhas_aberto,
      "total_sc_unicas_aberto": total_sc_unicas_aberto,
      "sem_pedido_total": sem_pedido_total,
      "sla_geral_rot": sla_geral_rot,
      "sla_geral_emg": sla_geral_emg,
      "snapshot_atual": snapshot_atual,
  }
