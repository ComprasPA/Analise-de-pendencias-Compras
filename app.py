import datetime
import io
import json
import gspread
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide", page_title="Panorama Executivo de Suprimentos")

FILE_ID = "1e7pQ512ge5XMnXxsRODEO7V48KgWo6FpKeITFqBSg1o"
GOOGLE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
ABA_HISTORICO = "Historico_Snapshots"


def obter_client_gspread():
  """Autentica no Google Sheets com a mesma service account usada pelos
  outros painéis (Portal do Comprador / Portal Gestão de Compras) - exige o
  secret 'gcp_service_account' configurado nos Secrets deste app."""
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(
      dict(st.secrets["gcp_service_account"]), scopes=scope
  )
  return gspread.authorize(creds)


def obter_aba_historico(client):
  """Garante que a aba de histórico existe na mesma planilha de
  Solicitações, criando com o cabeçalho padrão na primeira vez."""
  spreadsheet = client.open_by_key(FILE_ID)
  try:
    return spreadsheet.worksheet(ABA_HISTORICO)
  except gspread.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(
        title=ABA_HISTORICO, rows=1000, cols=2
    )
    worksheet.update([["Data", "Dados"]], "A1")
    return worksheet


def carregar_historico_dia(worksheet, data_str):
  """Lê o snapshot salvo pra uma data (YYYY-MM-DD); None se ainda não existir."""
  try:
    celula = worksheet.find(data_str, in_column=1)
  except gspread.exceptions.CellNotFound:
    return None
  if not celula:
    return None
  try:
    return json.loads(worksheet.cell(celula.row, 2).value)
  except (TypeError, ValueError):
    return None


def salvar_historico_dia(worksheet, data_str, snapshot):
  """Grava (ou atualiza, se já existir) o snapshot do dia."""
  dados_json = json.dumps(snapshot, ensure_ascii=False)
  try:
    celula = worksheet.find(data_str, in_column=1)
  except gspread.exceptions.CellNotFound:
    celula = None
  if celula:
    worksheet.update_cell(celula.row, 2, dados_json)
  else:
    worksheet.append_row([data_str, dados_json], value_input_option="RAW")

col_fonte, col_refresh, col_tema = st.columns([5, 0.6, 1])
with col_fonte:
  st.caption("🔗 Fonte: Google Sheets (Guia: Solicitações) — sincronização automática")
with col_refresh:
  if st.button("🔄", help="Atualizar dados agora"):
    st.cache_data.clear()
    st.rerun()
with col_tema:
  modo_escuro = st.toggle("☀️ / 🌙", value=True, help="Alternar entre tema claro e escuro")

tema_selecionado = "Escuro" if modo_escuro else "Claro"
data_base = datetime.date.today()

is_tema_claro = tema_selecionado == "Claro"

if tema_selecionado == "Escuro":
  css_tema = """
        .stApp { background-color: #0e1117 !important; color: #f8fafc !important; }
        .header-box { background-color: #1f3b58 !important; color: #ffffff !important; }
        .resumo-bar, .section-header { background-color: #2b4c7e !important; color: #ffffff !important; }
        p, span, label, div, h1, h2, h3, h4, h5, h6 { color: #f8fafc !important; }
    """
else:
  css_tema = """
        .stApp { background-color: #ffffff !important; color: #334155 !important; }
        .header-box { background-color: #1e3a8a !important; color: #ffffff !important; }
        .resumo-bar, .section-header { background-color: #3b82f6 !important; color: #ffffff !important; }
        p, span, label, div, h1, h2, h3, h4, h5, h6 { color: #334155 !important; }
    """

weight_title = "600" if is_tema_claro else "bold"
weight_sub = "400" if is_tema_claro else "bold"
weight_resumo = "600" if is_tema_claro else "bold"
weight_gauge = "600" if is_tema_claro else "800"
weight_th = "500" if is_tema_claro else "700"

st.markdown(
    f"""
    <style>
    header[data-testid="stHeader"], [data-testid="stDecoration"], .viewerBadge_container__1QSob, [data-testid="manage-app-button"], #MainMenu, footer {{
        visibility: hidden;
        display: none !important;
    }}
    .block-container {{
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        max-width: 100% !important;
    }}
    .header-box {{
        padding: 12px 20px;
        border-radius: 4px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }}
    .header-title {{ font-size: 1.8rem; font-weight: {weight_title}; color: #ffffff !important; }}
    .header-sub {{ font-size: 1.05rem; font-weight: {weight_sub}; color: #ffffff !important; }}
    .resumo-bar {{
        text-align: center;
        font-weight: {weight_resumo};
        font-size: 0.95rem;
        padding: 6px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 15px;
        border-radius: 2px;
        color: #ffffff !important;
    }}
    .section-header {{
        text-align: center;
        font-weight: {weight_resumo};
        font-size: 0.9rem;
        padding: 6px;
        text-transform: uppercase;
        border-radius: 2px;
        margin-bottom: 8px;
        color: #ffffff !important;
    }}
    .gauge-footer {{
        text-align: center;
        font-size: 1rem;
        font-weight: {weight_gauge};
        margin-top: -5px;
    }}
    div[data-testid="stDataFrame"] {{
        max-width: 60% !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }}
    .stDataFrame td, .stDataFrame th {{
        font-size: 0.82rem !important;
        font-weight: {weight_th} !important;
        padding: 2px 3px !important;
        text-align: center !important;
    }}
    {css_tema}
    </style>
""",
    unsafe_allow_html=True,
)

cor_texto_grafico = "#ffffff" if not is_tema_claro else "#334155"
familia_fonte_grafico = "Arial" if is_tema_claro else "Arial Black"

MAPA_COMPRADORES = {
    "1225": "Ednilson",
    "1235": "Ednilson",
    "1241": "Ednilson",
    "1236": "Ednilson",
    "1238": "Dayana",
    "1243": "Dayana",
    "1217": "Dayana",
    "1237": "Dayana",
    "1223": "Luiz",
    "1240": "Luiz",
    "9001": "Luiz",
    "2003": "Luiz",
    "2002": "Luiz",
    "2001": "Luiz",
    "3003": "Luiz",
    "2010": "Luiz",
    "3007": "Luiz",
    "3010": "Luiz",
    "3000": "Luiz",
    "3002": "Luiz",
    "3006": "Luiz",
    "1239": "Luiz",
    "3013": "Luiz",
    "3024": "Luiz",
    "1244": "Sílvio",
}

df = None

sla_geral_rot = 0
sla_geral_emg = 0


@st.cache_data(ttl=86400)
def carregar_dados_gsheets(url):
  response = requests.get(url)
  response.raise_for_status()
  xls = pd.ExcelFile(io.BytesIO(response.content))
  sheet_name = (
      "Solicitações" if "Solicitações" in xls.sheet_names else xls.sheet_names[0]
  )
  return pd.read_excel(io.BytesIO(response.content), sheet_name=sheet_name)


try:
  df = carregar_dados_gsheets(GOOGLE_SHEET_URL)
except Exception as e:
  st.error(f"⚠️ Erro ao conectar com o Google Sheets: {e}")

if df is not None:
  try:
    df.columns = df.columns.astype(str).str.strip()

    col_status = "STATUS" if "STATUS" in df.columns else None
    col_criticidade = "CRITICIDADE" if "CRITICIDADE" in df.columns else None
    col_sc = (
        "Solicitação"
        if "Solicitação" in df.columns
        else ("Cod SC. SCM" if "Cod SC. SCM" in df.columns else None)
    )
    col_cc = "Centro de Custo" if "Centro de Custo" in df.columns else None
    col_dt_emissao = (
        "Data Solicitação" if "Data Solicitação" in df.columns else None
    )
    col_dt_pedido = "Data Pedido" if "Data Pedido" in df.columns else None

    col_pedido_num = None
    for c in ["Pedido", "Nº Pedido", "Num. Pedido", "Nro Pedido", "Cod Pedido"]:
      if c in df.columns:
        col_pedido_num = c
        break

    hoje = pd.to_datetime(data_base)
    hoje_str = hoje.strftime("%Y-%m-%d")
    ontem_str = (hoje - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    df[col_dt_emissao] = pd.to_datetime(df[col_dt_emissao], errors="coerce")
    if col_dt_pedido:
      df[col_dt_pedido] = pd.to_datetime(df[col_dt_pedido], errors="coerce")

    df["CC_clean"] = (
        pd.to_numeric(df[col_cc], errors="coerce")
        .fillna(df[col_cc])
        .astype(str)
        .str.split(".")
        .str[0]
        .str.strip()
    )
    df["Comprador_Resp"] = df["CC_clean"].map(MAPA_COMPRADORES).fillna(
        "Não Mapeado / Outros"
    )

    def detalhar_status(x):
      x_str = str(x).strip().upper()
      if x_str == "FINALIZADO":
        return "Atendidas"
      elif "FORA" in x_str:
        return "Fora do Prazo"
      elif "ATENÇÃO" in x_str:
        return "Atenção"
      else:
        return "No Prazo"

    if col_status:
      df["Status_Detalhado"] = df[col_status].apply(detalhar_status)
    else:
      df["Status_Detalhado"] = "No Prazo"

    def calcular_sla(row):
      status = str(row.get(col_status, "")).strip().upper()
      dt_ini = row[col_dt_emissao]
      if pd.isna(dt_ini):
        return 0
      if (
          status == "FINALIZADO"
          and col_dt_pedido
          and not pd.isna(row[col_dt_pedido])
      ):
        return max((row[col_dt_pedido] - dt_ini).days, 0)
      else:
        return max((hoje - dt_ini).days, 0)

    df["Days"] = df.apply(calcular_sla, axis=1)

    if col_pedido_num:
      s_ped = df[col_pedido_num].dropna().astype(str).str.strip()
      has_pedido = (
          s_ped.str.contains(r"\d", regex=True)
          & (s_ped != "")
          & (s_ped.str.upper() != "NAN")
      )
      df["Tem_Pedido"] = has_pedido
    else:
      df["Tem_Pedido"] = False

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

    df_geral_crit = df.copy()
    if col_dt_emissao in df_geral_crit.columns:
      mask_luiz_antigo = (df_geral_crit["Comprador_Resp"] == "Luiz") & (
          df_geral_crit[col_dt_emissao] < pd.to_datetime("2026-07-06")
      )
      df_geral_crit = df_geral_crit[~mask_luiz_antigo]

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

    compradores_snapshot = ["Ednilson", "Dayana", "Luiz", "Sílvio"]
    for comp in compradores_snapshot:
      df_c = df[df["Comprador_Resp"] == comp]
      if comp == "Luiz" and col_dt_emissao in df_c.columns:
        df_c = df_c[df_c[col_dt_emissao] >= pd.to_datetime("2026-07-06")]

      sem_ped_comp = int(
          (~df_c["Tem_Pedido"].fillna(False).astype(bool)).sum()
      )
      pedidos_emitidos_comp = int(
          df_c["Tem_Pedido"].fillna(False).astype(bool).sum()
      )
      snapshot_atual["compradores"][comp] = {
          "total": int(len(df_c)),
          "sem_pedido": sem_ped_comp,
          "comprados": pedidos_emitidos_comp,
      }

    # Salva o snapshot de hoje e lê o de ontem numa aba da própria planilha
    # (não em disco local - o Streamlit Cloud tem disco efêmero e qualquer
    # arquivo salvo ali some a cada sono/redeploy do app, que é por isso o
    # histórico antigo nunca funcionava). Se as credenciais do Google Sheets
    # ainda não estiverem configuradas nos Secrets deste app, o comparativo
    # fica indisponível mas o resto do painel funciona normalmente.
    dados_ontem = None
    erro_historico = None
    try:
      client_hist = obter_client_gspread()
      worksheet_hist = obter_aba_historico(client_hist)
      dados_ontem = carregar_historico_dia(worksheet_hist, ontem_str)
      salvar_historico_dia(worksheet_hist, hoje_str, snapshot_atual)
    except Exception as e:
      erro_historico = str(e)

    st.markdown(
        f"""
        <div class="header-box">
            <span class="header-title">PANORAMA DE REQUISIÇÕES PENDENTES DE COMPRA (EM ABERTO)</span>
            <span class="header-sub">GOOGLE SHEETS | {hoje.strftime("%d/%m/%Y")}</span>
        </div>
        <div class="resumo-bar">DIAGNÓSTICO E VALIDAÇÃO ESTRATÉGICA (VOLUMETRIA, CRITICIDADE E STATUS)</div>
        """,
        unsafe_allow_html=True,
    )

    def criar_gauge(
        titulo, valor, max_val, cor_barra, sufixo="", altura=130, title_size=10
    ):
      fig = go.Figure(
          go.Indicator(
              mode="gauge+number",
              value=valor,
              number={
                  "suffix": sufixo,
                  "font": {
                      "size": 20,
                      "color": cor_texto_grafico,
                      "family": familia_fonte_grafico,
                  },
              },
              title={
                  "text": titulo,
                  "font": {
                      "size": title_size,
                      "color": cor_texto_grafico,
                      "family": familia_fonte_grafico,
                  },
              },
              gauge={
                  "axis": {
                      "range": [None, max_val],
                      "tickwidth": 1,
                      "tickcolor": "#475569",
                      "tickfont": {
                          "size": 9,
                          "color": cor_texto_grafico,
                          "family": familia_fonte_grafico,
                      },
                  },
                  "bar": {"color": cor_barra},
                  "bgcolor": "rgba(0,0,0,0)",
                  "borderwidth": 0,
                  "steps": [
                      {
                          "range": [0, max_val * 0.6],
                          "color": "#2a3b4c" if not is_tema_claro else "#f1f5f9",
                      },
                      {
                          "range": [max_val * 0.6, max_val],
                          "color": "#1f2937" if not is_tema_claro else "#e2e8f0",
                      },
                  ],
              },
          )
      )
      fig.update_layout(
          height=altura,
          margin=dict(l=20, r=20, t=40, b=5),
          paper_bgcolor="rgba(0,0,0,0)",
          plot_bgcolor="rgba(0,0,0,0)",
      )
      return fig

    row1_c1, row1_c2, row1_c3, row1_div, row1_c4, row1_c5, row1_c6 = st.columns(
        [1.5, 1, 1, 0.2, 1, 1, 1]
    )

    with row1_c1:
      if dados_ontem:
        texto_comparativo = f"Ontem: {dados_ontem.get('total_scs_aberto', '--')} SCs | {dados_ontem.get('sem_pedido_total', '--')} Itens"
      elif erro_historico:
        texto_comparativo = "Comparativo indisponível (configure as credenciais do Google Sheets)"
      else:
        texto_comparativo = "Comparativo vs Ontem: Aguardando 2º dia"

      border_ontem = "#cbd5e1" if is_tema_claro else "#334155"
      st.markdown(
          f"""
            <div style="border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px; text-align: center; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 0.95rem; font-weight: {weight_resumo}; margin-bottom: 2px;">VOLUMETRIA EM ABERTO</div>
                <div style="font-size: 1.95rem; font-weight: bold; color: #2563eb; line-height: 1.1;">{total_sc_unicas_aberto}</div>
                <div style="font-size: 0.85rem; font-weight: {weight_th};">Solicitações (SCs)</div>
                <div style="border-top: 1px dashed #cbd5e1; margin: 2px 0;"></div>
                <div style="font-size: 1.5rem; font-weight: bold; color: #d97706; line-height: 1.1;">{sem_pedido_total}</div>
                <div style="font-size: 0.85rem; font-weight: {weight_th};">Itens Sem Pedido</div>
                <div style="margin-top: 6px; padding: 4px 6px; border: 1px solid {border_ontem}; border-radius: 4px; font-size: 0.72rem; color: #64748b;">{texto_comparativo}</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

    def render_gauge(col, titulo, valor, max_val, cor, key_suffix):
      with col:
        st.plotly_chart(
            criar_gauge(titulo, valor, max_val, cor, altura=130),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"gauge_superior_{key_suffix}",
        )
        perc = (valor / max_val * 100) if max_val > 0 else 0
        st.markdown(
            f"<div class='gauge-footer' style='color: {cor};'>{perc:.1f}%</div>",
            unsafe_allow_html=True,
        )

    crit_counts = (
        df_aberto[col_criticidade].astype(str).str.upper().value_counts()
        if col_criticidade
        else {}
    )
    qtd_rot = crit_counts.get("ROTINEIRA", 0)
    qtd_emg = crit_counts.get("EMERGENCIAL", 0)
    status_counts = df_aberto["Status_Detalhado"].value_counts()
    qtd_no_prazo = status_counts.get("No Prazo", 0)
    qtd_atencao = status_counts.get("Atenção", 0)
    qtd_fora = status_counts.get("Fora do Prazo", 0)

    render_gauge(
        row1_c2,
        "ROTINEIRA",
        qtd_rot,
        total_linhas_aberto,
        "#3b82f6" if is_tema_claro else "#2b6cb0",
        "rot",
    )
    render_gauge(
        row1_c3,
        "EMERGENCIAL",
        qtd_emg,
        total_linhas_aberto,
        "#8b5cf6" if is_tema_claro else "#805ad5",
        "emg",
    )

    with row1_div:
      st.markdown(
          f"""
            <div style="border-left: 2px solid {'#cbd5e1' if is_tema_claro else '#333333'}; height: 140px; margin: auto; margin-top: 5px;"></div>
            """,
          unsafe_allow_html=True,
      )

    render_gauge(
        row1_c4,
        "NO PRAZO",
        qtd_no_prazo,
        total_linhas_aberto,
        "#22c55e" if is_tema_claro else "#388e3c",
        "no_prazo",
    )
    render_gauge(
        row1_c5,
        "ATENÇÃO",
        qtd_atencao,
        total_linhas_aberto,
        "#f59e0b" if is_tema_claro else "#d97706",
        "atencao",
    )
    render_gauge(
        row1_c6,
        "FORA DO PRAZO",
        qtd_fora,
        total_linhas_aberto,
        "#ef4444" if is_tema_claro else "#e53e3e",
        "fora_prazo",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("---")
    row2_c1, row2_c2, row2_c3 = st.columns(3)

    with row2_c1:
      st.markdown(
          '<div class="section-header">TOP 10 CC (VOLUME DE ITENS)</div>',
          unsafe_allow_html=True,
      )
      cc_volume = (
          df_aberto.groupby("CC_clean")
          .size()
          .reset_index(name="Quantidade")
          .sort_values(by="Quantidade", ascending=False)
          .head(10)
      )
      cc_volume["CC_clean"] = cc_volume["CC_clean"].astype(str)

      cores_barras = ["#2563eb"] + ["#f97316"] * (len(cc_volume) - 1)
      fig_cc_it = go.Figure(
          go.Bar(
              x=cc_volume.sort_values(by="Quantidade", ascending=True)[
                  "Quantidade"
              ],
              y=cc_volume.sort_values(by="Quantidade", ascending=True)[
                  "CC_clean"
              ],
              orientation="h",
              text=cc_volume.sort_values(by="Quantidade", ascending=True)[
                  "Quantidade"
              ],
              textposition="outside",
              textfont=dict(
                  size=11,
                  color=cor_texto_grafico,
                  family=familia_fonte_grafico,
              ),
              marker_color=cores_barras[::-1],
          )
      )
      fig_cc_it.update_layout(
          xaxis_title="Qtd. Itens",
          yaxis_title="",
          plot_bgcolor="rgba(0,0,0,0)",
          paper_bgcolor="rgba(0,0,0,0)",
          font=dict(color=cor_texto_grafico),
          margin=dict(l=5, r=10, t=10, b=10),
          height=320,
          xaxis=dict(
              showgrid=True,
              gridcolor="#e2e8f0" if is_tema_claro else "#333333",
          ),
          yaxis=dict(
              type="category",
              tickfont=dict(
                  family=familia_fonte_grafico,
                  size=10,
                  color=cor_texto_grafico,
              ),
          ),
      )
      st.plotly_chart(
          fig_cc_it,
          use_container_width=True,
          config={"displayModeBar": False},
          key="plotly_top10_cc_volume",
      )

    with row2_c2:
      st.markdown(
          '<div class="section-header">TOP 10 CC (QTD. REQUISIÇÕES)</div>',
          unsafe_allow_html=True,
      )
      cc_scs = (
          unique_scs_aberto.groupby("CC_clean")[col_sc]
          .nunique()
          .reset_index(name="Qtd_SCs")
          .sort_values(by="Qtd_SCs", ascending=False)
          .head(10)
      )
      cc_scs["CC_clean"] = cc_scs["CC_clean"].astype(str)

      cores_barras_sc = ["#3b82f6"] + ["#0d9488"] * (len(cc_scs) - 1)
      fig_cc_sc = go.Figure(
          go.Bar(
              x=cc_scs.sort_values(by="Qtd_SCs", ascending=True)["Qtd_SCs"],
              y=cc_scs.sort_values(by="Qtd_SCs", ascending=True)["CC_clean"],
              orientation="h",
              text=cc_scs.sort_values(by="Qtd_SCs", ascending=True)["Qtd_SCs"],
              textposition="outside",
              textfont=dict(
                  size=11,
                  color=cor_texto_grafico,
                  family=familia_fonte_grafico,
              ),
              marker_color=cores_barras_sc[::-1],
          )
      )
      fig_cc_sc.update_layout(
          xaxis_title="Qtd. Requisições (SCs)",
          yaxis_title="",
          plot_bgcolor="rgba(0,0,0,0)",
          paper_bgcolor="rgba(0,0,0,0)",
          font=dict(color=cor_texto_grafico),
          margin=dict(l=5, r=10, t=10, b=10),
          height=320,
          xaxis=dict(
              showgrid=True,
              gridcolor="#e2e8f0" if is_tema_claro else "#333333",
          ),
          yaxis=dict(
              type="category",
              tickfont=dict(
                  family=familia_fonte_grafico,
                  size=10,
                  color=cor_texto_grafico,
              ),
          ),
      )
      st.plotly_chart(
          fig_cc_sc,
          use_container_width=True,
          config={"displayModeBar": False},
          key="plotly_top10_cc_scs",
      )

    with row2_c3:
      st.markdown(
          '<div class="section-header">CRITICIDADE VS STATUS (QTD.'
          ' ITENS)</div>',
          unsafe_allow_html=True,
      )
      if col_criticidade and col_status:
        df_crit_stat = df_aberto[
            df_aberto[col_criticidade]
            .astype(str)
            .str.upper()
            .isin(["ROTINEIRA", "EMERGENCIAL"])
        ]
        if not df_crit_stat.empty:
          crit_stats = (
              df_crit_stat.groupby([col_criticidade, col_status])
              .size()
              .reset_index(name="Quantidade")
          )
          color_map = {
              "NO PRAZO": "#22c55e" if is_tema_claro else "#388e3c",
              "ATENÇÃO": "#f59e0b" if is_tema_claro else "#d97706",
              "FORA DO PRAZO": "#ef4444" if is_tema_claro else "#e53e3e",
          }
          fig_crit_stat = go.Figure()
          for status_val in ["NO PRAZO", "ATENÇÃO", "FORA DO PRAZO"]:
            df_sub = crit_stats[crit_stats[col_status].str.upper() == status_val]
            if not df_sub.empty:
              fig_crit_stat.add_trace(
                  go.Bar(
                      x=df_sub[col_criticidade],
                      y=df_sub["Quantidade"],
                      name=status_val.title(),
                      marker_color=color_map.get(status_val, "#718096"),
                      text=df_sub["Quantidade"],
                      textposition="auto",
                      textfont=dict(
                          size=11,
                          color=cor_texto_grafico,
                          family=familia_fonte_grafico,
                      ),
                  )
              )
          fig_crit_stat.update_layout(
              barmode="group",
              xaxis_title="",
              yaxis_title="Qtd. ITENS",
              plot_bgcolor="rgba(0,0,0,0)",
              paper_bgcolor="rgba(0,0,0,0)",
              height=320,
              font=dict(color=cor_texto_grafico),
              legend=dict(
                  orientation="h",
                  yanchor="bottom",
                  y=1.02,
                  xanchor="right",
                  x=1,
                  font=dict(
                      family=familia_fonte_grafico,
                      size=9,
                      color=cor_texto_grafico,
                  ),
              ),
              xaxis=dict(
                  showgrid=False,
                  tickfont=dict(
                      size=11,
                      family=familia_fonte_grafico,
                      color=cor_texto_grafico,
                  ),
              ),
              yaxis=dict(
                  showgrid=True,
                  gridcolor="#e2e8f0" if is_tema_claro else "#333333",
              ),
          )
          st.plotly_chart(
              fig_crit_stat,
              use_container_width=True,
              config={"displayModeBar": False},
              key="plotly_criticidade_vs_status",
          )

    st.markdown("---")
    row3_c1, row3_c2 = st.columns([1.50, 0.50])

    with row3_c1:
      st.markdown(
          '<div class="section-header">TOP 10 SOLICITAÇÕES DE COMPRA DIRETA'
          " (2026)</div>",
          unsafe_allow_html=True,
      )

      df_geral_completo = df.dropna(subset=[col_sc]).copy()
      df_geral_completo[col_sc] = (
          df_geral_completo[col_sc].astype(str).str.split(".").str[0].str.zfill(6)
      )

      col_tipo_candidatas = [
          c
          for c in df_geral_completo.columns
          if any(
              termo in c.upper()
              for termo in [
                  "TIPO",
                  "GRUPO",
                  "FORMA",
                  "COMPRA",
                  "CLASSIFICAÇÃO",
              ]
          )
      ]

      df_direta_total = df_geral_completo.drop_duplicates(
          subset=[col_sc]
      ).copy()
      filtrado_com_sucesso = False

      if col_tipo_candidatas:
        for c_cand in col_tipo_candidatas:
          mask = (
              df_direta_total[c_cand]
              .astype(str)
              .str.upper()
              .str.contains("DIRETA", na=False)
          )
          if mask.sum() > 0:
            df_direta_total = df_direta_total[mask]
            filtrado_com_sucesso = True
            break

      if not filtrado_com_sucesso:
        for col_str in df_geral_completo.select_dtypes(
            include=["object", "string"]
        ).columns:
          mask_gen = (
              df_geral_completo[col_str]
              .astype(str)
              .str.upper()
              .str.contains("DIRETA", na=False)
          )
          if mask_gen.sum() > 0:
            scs_diretas = df_geral_completo[mask_gen][col_sc].unique()
            df_direta_total = df_direta_total[
                df_direta_total[col_sc].isin(scs_diretas)
            ]
            filtrado_com_sucesso = True
            break

      if filtrado_com_sucesso and not df_direta_total.empty:
        cc_direta = (
            df_direta_total.groupby("CC_clean")[col_sc]
            .nunique()
            .reset_index(name="Qtd_SCs")
            .sort_values(by="Qtd_SCs", ascending=False)
            .head(10)
        )
        cc_direta["CC_clean"] = cc_direta["CC_clean"].astype(str)

        cores_direta = ["#3b82f6"] + ["#0d9488"] * (len(cc_direta) - 1)
        fig_direta = go.Figure(
            go.Bar(
                x=cc_direta.sort_values(by="Qtd_SCs", ascending=True)[
                    "Qtd_SCs"
                ],
                y=cc_direta.sort_values(by="Qtd_SCs", ascending=True)[
                    "CC_clean"
                ],
                orientation="h",
                text=cc_direta.sort_values(by="Qtd_SCs", ascending=True)[
                    "Qtd_SCs"
                ],
                textposition="outside",
                textfont=dict(
                    size=11,
                    color=cor_texto_grafico,
                    family=familia_fonte_grafico,
                ),
                marker_color=cores_direta[::-1],
            )
        )
        fig_direta.update_layout(
            xaxis_title="Qtd. Requisições (Compra Direta - 2026)",
            yaxis_title="",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=320,
            font=dict(color=cor_texto_grafico),
            margin=dict(l=5, r=20, t=10, b=10),
            xaxis=dict(
                showgrid=True,
                gridcolor="#e2e8f0" if is_tema_claro else "#333333",
            ),
            yaxis=dict(
                type="category",
                tickfont=dict(
                    family=familia_fonte_grafico, color=cor_texto_grafico
                ),
            ),
        )
        st.plotly_chart(
            fig_direta,
            use_container_width=True,
            config={"displayModeBar": False},
            key="plotly_top10_compra_direta",
        )
      else:
        st.info(
            "💡 Nenhum registro classificado como 'Direta' foi localizado na"
            " planilha completa."
        )

    with row3_c2:
      st.markdown(
          '<div class="section-header">ITENS CRÍTICOS</div>',
          unsafe_allow_html=True,
      )
      criticos_df = unique_scs_aberto[unique_scs_aberto["Days"] >= 20]
      top_critical = criticos_df.sort_values(by="Days", ascending=False)[
          [col_sc, "CC_clean", "Days"]
      ].head(7)
      top_critical.columns = ["Nº SC", "C. CUSTO", "ATRASO"]
      top_critical["ATRASO"] = top_critical["ATRASO"].astype(str) + " DIAS 🔥"
      st.dataframe(
          top_critical, use_container_width=True, height=270, hide_index=True
      )

    st.markdown("---")
    st.markdown(
        '<div class="section-header" style="background-color: #2b4c7e;">DESEMPENHO'
        " INDIVIDUAL POR COMPRADOR & PRODUTIVIDADE DIÁRIA</div>",
        unsafe_allow_html=True,
    )

    row4_c1, row4_c2, row4_c3, row4_c4 = st.columns(4)
    compradores = ["Ednilson", "Dayana", "Luiz", "Sílvio"]
    colunas_st = [row4_c1, row4_c2, row4_c3, row4_c4]

    color_status_map = {
        "No Prazo": "#22c55e" if is_tema_claro else "#388e3c",
        "Atenção": "#f59e0b" if is_tema_claro else "#d97706",
        "Fora do Prazo": "#ef4444" if is_tema_claro else "#e53e3e",
    }
    ordem_status_aberto = ["Fora do Prazo", "Atenção", "No Prazo"]

    for comp, col_st in zip(compradores, colunas_st):
      with col_st:
        st.markdown(
            f'<div style="text-align: center; font-weight: {weight_resumo}; font-size: 1.05rem; margin-bottom: 2px;">👤 {comp}</div>',
            unsafe_allow_html=True,
        )

        df_comp_total = df[df["Comprador_Resp"] == comp].copy()

        if comp == "Luiz" and col_dt_emissao in df_comp_total.columns:
          df_comp_total = df_comp_total[
              df_comp_total[col_dt_emissao] >= pd.to_datetime("2026-07-06")
          ]

        sem_ped_atual = int(
            (~df_comp_total["Tem_Pedido"].fillna(False).astype(bool)).sum()
        )
        comprados_atual = int(
            df_comp_total["Tem_Pedido"].fillna(False).astype(bool).sum()
        )

        comp_ontem_data = (
            dados_ontem.get("compradores", {}).get(comp, {})
            if dados_ontem
            else {}
        )
        sem_ped_ontem = comp_ontem_data.get("sem_pedido", None)
        comprados_ontem = comp_ontem_data.get("comprados", None)

        if sem_ped_ontem is not None and comprados_ontem is not None:
          delta_sem_ped = sem_ped_atual - sem_ped_ontem
          delta_comprados = comprados_atual - comprados_ontem
          s_sp = "+" if delta_sem_ped > 0 else ""
          s_cp = "+" if delta_comprados > 0 else ""
          texto_produtividade = f"Ontem S/Ped: {sem_ped_ontem} ({s_sp}{delta_sem_ped}) | Pedidos Fechados: {comprados_atual} ({s_cp}{delta_comprados})"
        elif erro_historico:
          texto_produtividade = "Produtividade Ontem: indisponível (Sheets não configurado)"
        else:
          texto_produtividade = "Produtividade Ontem: Aguardando 2º dia"

        if not df_comp_total.empty and "Status_Detalhado" in df_comp_total.columns:
          total_emitidas = len(df_comp_total)
          qtd_atendidas = len(
              df_comp_total[df_comp_total["Status_Detalhado"] == "Atendidas"]
          )
          taxa_rendimento_comp = (
              (qtd_atendidas / total_emitidas * 100)
              if total_emitidas > 0
              else 0
          )

          qtd_pedidos_gerados = comprados_atual

          if col_criticidade:
            df_comp_crit = df_comp_total[
                df_comp_total[col_criticidade]
                .astype(str)
                .str.upper()
                .isin(["ROTINEIRA", "EMERGENCIAL"])
            ]
          else:
            df_comp_crit = pd.DataFrame()

          sla_rot_val = (
              int(
                  round(
                      df_comp_crit[
                          df_comp_crit[col_criticidade]
                          .astype(str)
                          .str.upper()
                          == "ROTINEIRA"
                      ]["Days"].mean(),
                      0,
                  )
              )
              if not df_comp_crit.empty
              and not pd.isna(
                  df_comp_crit[
                      df_comp_crit[col_criticidade].astype(str).str.upper()
                      == "ROTINEIRA"
                  ]["Days"].mean()
              )
              else 0
          )
          sla_emg_val = (
              int(
                  round(
                      df_comp_crit[
                          df_comp_crit[col_criticidade]
                          .astype(str)
                          .str.upper()
                          == "EMERGENCIAL"
                      ]["Days"].mean(),
                      0,
                  )
              )
              if not df_comp_crit.empty
              and not pd.isna(
                  df_comp_crit[
                      df_comp_crit[col_criticidade].astype(str).str.upper()
                      == "EMERGENCIAL"
                  ]["Days"].mean()
              )
              else 0
          )

          cor_gauge_comp = (
              "#22c55e"
              if taxa_rendimento_comp >= 75
              else ("#f59e0b" if taxa_rendimento_comp >= 50 else "#ef4444")
          )
          fig_gauge = criar_gauge(
              "RENDIMENTO",
              taxa_rendimento_comp,
              100,
              cor_gauge_comp,
              sufixo="%",
              altura=110,
              title_size=10,
          )
          st.plotly_chart(
              fig_gauge,
              use_container_width=True,
              config={"displayModeBar": False},
              key=f"gauge_rendimento_{comp}",
          )

          df_comp_aberto = df_comp_total[
              df_comp_total["Status_Detalhado"] != "Atendidas"
          ].copy()

          if not df_comp_aberto.empty:
            comp_stats = (
                df_comp_aberto.groupby("Status_Detalhado")
                .size()
                .reset_index(name="Quantidade")
            )
            total_aberto = comp_stats["Quantidade"].sum()
            comp_stats["Percentual"] = (
                comp_stats["Quantidade"] / total_aberto * 100
            ).round(1)
            comp_stats["Status_Detalhado"] = pd.Categorical(
                comp_stats["Status_Detalhado"],
                categories=ordem_status_aberto,
                ordered=True,
            )
            comp_stats = comp_stats.sort_values("Status_Detalhado")

            cores = [
                color_status_map.get(s, "#718096")
                for s in comp_stats["Status_Detalhado"]
            ]
            comp_stats["Texto_Label"] = comp_stats.apply(
                lambda row: f"{int(row['Quantidade'])} ({row['Percentual']}%)",
                axis=1,
            )

            fig_comp_ind = go.Figure(
                go.Bar(
                    x=comp_stats["Percentual"],
                    y=comp_stats["Status_Detalhado"],
                    orientation="h",
                    text=comp_stats["Texto_Label"],
                    textposition="outside",
                    textfont=dict(
                        size=10,
                        color=cor_texto_grafico,
                        family=familia_fonte_grafico,
                    ),
                    marker_color=cores,
                )
            )
            fig_comp_ind.update_layout(
                xaxis_title="% Backlog",
                yaxis_title="",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=130,
                font=dict(color=cor_texto_grafico),
                margin=dict(l=5, r=25, t=0, b=10),
                xaxis=dict(
                    showgrid=True,
                    gridcolor="#e2e8f0" if is_tema_claro else "#333333",
                    range=[0, max(comp_stats["Percentual"].max() * 1.35, 100)],
                    tickfont=dict(size=8, color=cor_texto_grafico),
                ),
                yaxis=dict(
                    type="category",
                    tickfont=dict(
                        family=familia_fonte_grafico,
                        size=9,
                        color=cor_texto_grafico,
                    ),
                ),
            )
            st.plotly_chart(
                fig_comp_ind,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"bar_backlog_{comp}",
            )
          else:
            st.info(f"Fila limpa para {comp}.")

          bg_atendidos = "#f1f5f9" if is_tema_claro else "#1a202c"
          color_atendidos = "#2563eb" if is_tema_claro else "#63b3ed"
          border_atendidos = "transparent" if is_tema_claro else "#333333"

          st.markdown(
              f"""
                    <div style='text-align: center; font-size: 0.78rem; font-weight: {weight_resumo}; background-color: {bg_atendidos}; color: {color_atendidos}; padding: 6px; border-radius: 4px; margin-top: 8px; margin-bottom: 0px; border: 1px solid {border_atendidos};'>
                        ✅ {qtd_atendidas} Atendidas | 📦 {qtd_pedidos_gerados} C/ Pedido<br>
                        ⏳ <b>{sem_ped_atual} Itens S/ Pedido (Fila)</b><br>
                        <span style="font-size: 0.68rem; font-weight: 500; color: #64748b;">{texto_produtividade}</span>
                    </div>
                    """,
              unsafe_allow_html=True,
          )

          cor_rot = (
              "#ef4444"
              if sla_rot_val > 15
              else ("#3b82f6" if is_tema_claro else "#339af0")
          )
          fig_rot = go.Figure(
              go.Indicator(
                  mode="gauge+number",
                  value=sla_rot_val,
                  number={
                      "font": {
                          "size": 18,
                          "color": cor_texto_grafico,
                          "family": familia_fonte_grafico,
                      }
                  },
                  gauge={
                      "axis": {
                          "range": [0, 30],
                          "tickwidth": 1,
                          "tickcolor": "#475569",
                          "tickfont": {
                              "size": 8,
                              "color": cor_texto_grafico,
                              "family": familia_fonte_grafico,
                          },
                      },
                      "bar": {"color": cor_rot},
                      "bgcolor": "rgba(0,0,0,0)",
                      "borderwidth": 0,
                      "steps": [
                          {
                              "range": [0, 15],
                              "color": "#f1f5f9" if is_tema_claro else "#2a3b4c",
                          },
                          {
                              "range": [15, 30],
                              "color": "#fee2e2" if is_tema_claro else "#4a2525",
                          },
                      ],
                      "threshold": {
                          "line": {"color": "red", "width": 3},
                          "thickness": 0.75,
                          "value": 15,
                      },
                  },
              )
          )
          fig_rot.update_layout(
              height=90,
              margin=dict(l=5, r=5, t=20, b=5),
              paper_bgcolor="rgba(0,0,0,0)",
              plot_bgcolor="rgba(0,0,0,0)",
          )

          cor_emg = (
              "#ef4444"
              if sla_emg_val > 3
              else ("#8b5cf6" if is_tema_claro else "#b197fc")
          )
          fig_emg = go.Figure(
              go.Indicator(
                  mode="gauge+number",
                  value=sla_emg_val,
                  number={
                      "font": {
                          "size": 18,
                          "color": cor_texto_grafico,
                          "family": familia_fonte_grafico,
                      }
                  },
                  gauge={
                      "axis": {
                          "range": [0, 20],
                          "tickwidth": 1,
                          "tickcolor": "#475569",
                          "tickfont": {
                              "size": 8,
                              "color": cor_texto_grafico,
                              "family": familia_fonte_grafico,
                          },
                      },
                      "bar": {"color": cor_emg},
                      "bgcolor": "rgba(0,0,0,0)",
                      "borderwidth": 0,
                      "steps": [
                          {
                              "range": [0, 3],
                              "color": "#f1f5f9" if is_tema_claro else "#2a3b4c",
                          },
                          {
                              "range": [3, 20],
                              "color": "#fee2e2" if is_tema_claro else "#4a2525",
                          },
                      ],
                      "threshold": {
                          "line": {"color": "red", "width": 3},
                          "thickness": 0.75,
                          "value": 3,
                      },
                  },
              )
          )
          fig_emg.update_layout(
              height=90,
              margin=dict(l=5, r=5, t=20, b=5),
              paper_bgcolor="rgba(0,0,0,0)",
              plot_bgcolor="rgba(0,0,0,0)",
          )

          sub_c1, sub_c2 = st.columns(2)
          with sub_c1:
            st.markdown(
                "<div style='margin-top: 20px;'></div>", unsafe_allow_html=True
            )
            st.plotly_chart(
                fig_rot,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"gauge_sla_rot_{comp}",
            )
            st.markdown(
                f"<div style='text-align: center; font-size: 0.75rem; font-weight: {weight_resumo}; color: {cor_texto_grafico}; margin-top: -2px;'>SLA ROT.</div><div style='text-align: center; font-size: 0.68rem; color: #64748b;'>Máx: 15d</div>",
                unsafe_allow_html=True,
            )
          with sub_c2:
            st.markdown(
                "<div style='margin-top: 20px;'></div>", unsafe_allow_html=True
            )
            st.plotly_chart(
                fig_emg,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"gauge_sla_emg_{comp}",
            )
            st.markdown(
                f"<div style='text-align: center; font-size: 0.75rem; font-weight: {weight_resumo}; color: {cor_texto_grafico}; margin-top: -2px;'>SLA EMG.</div><div style='text-align: center; font-size: 0.68rem; color: #64748b;'>Máx: 3d</div>",
                unsafe_allow_html=True,
            )

        else:
          st.info(f"Sem dados para {comp}.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div class="section-header" style="background-color: #1e3a8a; border:'
        " 1px solid #1e3a8a; margin-bottom: 12px;'>📊 SLA MÉDIO GERAL"
        " CONSOLIDADO</div>",
        unsafe_allow_html=True,
    )

    col_box1, col_box2 = st.columns(2)
    bg_box = "#f8fafc" if is_tema_claro else "#111827"
    border_box = "#cbd5e1" if is_tema_claro else "#374151"
    color_box_title = "#2563eb" if is_tema_claro else "#60a5fa"

    with col_box1:
      cor_val_rot = (
          "#ef4444"
          if sla_geral_rot > 15
          else ("#2563eb" if is_tema_claro else "#339af0")
      )
      st.markdown(
          f"""
            <div style="background-color: {bg_box}; border: 1px solid {border_box}; border-radius: 6px; padding: 15px; text-align: center;">
                <div style="font-size: 1.0rem; font-weight: {weight_resumo}; color: {color_box_title}; margin-bottom: 0px; text-transform: uppercase;">SLA ROTINEIRA MÉDIO</div>
                <div style="font-size: 0.75rem; font-weight: {weight_th}; color: #64748b; margin-bottom: 6px;">(Limite: 15 dias)</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: {cor_val_rot}; line-height: 1.1;">{sla_geral_rot} dias</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

    with col_box2:
      cor_val_emg = (
          "#ef4444"
          if sla_geral_emg > 3
          else ("#8b5cf6" if is_tema_claro else "#b197fc")
      )
      st.markdown(
          f"""
            <div style="background-color: {bg_box}; border: 1px solid {border_box}; border-radius: 6px; padding: 15px; text-align: center;">
                <div style="font-size: 1.0rem; font-weight: {weight_resumo}; color: {color_box_title}; margin-bottom: 0px; text-transform: uppercase;">SLA EMERGENCIAL MÉDIO</div>
                <div style="font-size: 0.75rem; font-weight: {weight_th}; color: #64748b; margin-bottom: 6px;">(Limite: 3 dias)</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: {cor_val_emg}; line-height: 1.1;">{sla_geral_emg} dias</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

  except Exception as e:
    st.error(f"⚠️ Erro analítico no processamento: {e}")
