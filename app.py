import base64
import datetime
import io
from pathlib import Path
import json
import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from google.oauth2.service_account import Credentials

import estilo
import indicadores_mercado
from painel_criticidade import renderizar_criticidade_solicitacoes
from logica_panorama import (
    COL_COTACAO,
    COL_DT_EMISSAO,
    LIMITE_SLA_DIAS,
    LIMITE_SLA_PADRAO,
    MAPA_COMPRADORES,
    STATUS_FORA_DO_BACKLOG,
    periodo_fechamento,
    processar_panorama,
)

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

ABA_INDICADORES = "Indicadores_Mercado"


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_indicadores_mercado(data_str, ano_focus):
  """Selic, IPCA e dólar do dia + Focus, direto do BCB. O resultado fica
  salvo na aba Indicadores_Mercado (uma linha por dia), de onde vem o
  último valor quando o BCB não responder. Cache de 1h; o botão ↻ limpa."""
  atuais = indicadores_mercado.buscar_indicadores(ano_focus)
  salvos = {}
  try:
    spreadsheet = obter_client_gspread().open_by_key(FILE_ID)
    try:
      worksheet = spreadsheet.worksheet(ABA_INDICADORES)
    except gspread.WorksheetNotFound:
      worksheet = spreadsheet.add_worksheet(title=ABA_INDICADORES, rows=1000, cols=2)
      worksheet.update([["Data", "Dados"]], "A1")
    linhas = worksheet.get_all_values()
    if len(linhas) > 1:
      try:
        salvos = json.loads(linhas[-1][1])
      except (IndexError, TypeError, ValueError):
        salvos = {}
    if atuais:
      salvar_historico_dia(worksheet, data_str, {**salvos, **atuais})
  except Exception:
    # sem planilha (secrets/rede) o painel segue só com o que veio do BCB
    pass
  return indicadores_mercado.mesclar(atuais, salvos)


@st.cache_data(show_spinner=False)
def logo_base64(nome):
  try:
    return base64.b64encode((Path(__file__).parent / "assets" / nome).read_bytes()).decode()
  except OSError:
    return ""


with st.container(key="header_card"):
  col_logo, col_marca, col_acoes = st.columns([2, 6, 2], vertical_alignment="center")
  with col_logo:
    st.markdown(
        f'<img class="pa-logo pa-logo-claro" src="data:image/png;base64,{logo_base64("logo.png")}" alt="Parente Andrade">'
        f'<img class="pa-logo pa-logo-escuro" src="data:image/png;base64,{logo_base64("logo_escuro.png")}" alt="Parente Andrade">',
        unsafe_allow_html=True,
    )
  with col_marca:
    st.markdown(
        """
        <div class="brand-text-block">
            <span class="brand-eyebrow">Coordenação de Suprimentos</span>
            <span class="brand-subtitle">Panorama Executivo de Suprimentos</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
  with col_acoes:
    col_refresh, col_tema = st.columns([1, 2.6], vertical_alignment="center")
    with col_refresh:
      if st.button("↻", help="Atualizar dados agora"):
        st.cache_data.clear()
        st.rerun()
    with col_tema:
      modo_escuro = st.toggle("Tema escuro", value=True, help="Alternar entre tema claro e escuro")

# Parâmetros de mercado: linha discreta logo abaixo do quadro do título.
_hoje = datetime.date.today()
st.markdown(
    indicadores_mercado.html_parametros(
        carregar_indicadores_mercado(_hoje.isoformat(), None), None
    ),
    unsafe_allow_html=True,
)

tema_selecionado = "Escuro" if modo_escuro else "Claro"
data_base = datetime.date.today()

is_tema_claro = tema_selecionado == "Claro"

weight_title = "600" if is_tema_claro else "bold"
weight_sub = "400" if is_tema_claro else "bold"
weight_resumo = "600" if is_tema_claro else "bold"
weight_gauge = "600" if is_tema_claro else "800"
weight_th = "500" if is_tema_claro else "700"

st.markdown(estilo.gerar_css(is_tema_claro), unsafe_allow_html=True)
estilo.instalar_folga_plotly()
st.markdown('<div class="app-signature">Created by SS.</div>', unsafe_allow_html=True)

tokens_tema = estilo.tokens(is_tema_claro)
cor_texto_grafico = tokens_tema["texto_grafico"]
familia_fonte_grafico = "Inter, Arial, sans-serif"

df = None
df_criticidade = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
df_pedidos = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

sla_geral_rot = 0
sla_geral_emg = 0

ABA_SOLICITACOES = "Solicitacoes"
ABA_CRITICIDADE = "Criticidade_Solicitacoes"
ABA_PEDIDOS = "Pedidos"

# Status manuais lançados no Portal do Comprador, e limites de SLA por
# criticidade: ver constantes STATUS_FORA_DO_BACKLOG / LIMITE_SLA_DIAS /
# LIMITE_SLA_PADRAO em logica_panorama.py (importadas acima) - documentação
# do porquê está lá junto da lógica que as usa.


@st.cache_data(ttl=300)
def carregar_dados_gsheets(url):
  response = requests.get(url)
  response.raise_for_status()
  conteudo = response.content
  df_sol = pd.read_excel(io.BytesIO(conteudo), sheet_name=ABA_SOLICITACOES)
  try:
    df_crit = pd.read_excel(
        io.BytesIO(conteudo), sheet_name=ABA_CRITICIDADE, dtype=str
    )
  except ValueError:
    df_crit = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_ped = pd.read_excel(io.BytesIO(conteudo), sheet_name=ABA_PEDIDOS, dtype=str)
  return df_sol, df_crit, df_ped


try:
  df, df_criticidade, df_pedidos = carregar_dados_gsheets(GOOGLE_SHEET_URL)
except Exception as e:
  st.error(f"⚠️ Erro ao conectar com o Google Sheets: {e}")

if df is not None:
  try:
    df.columns = df.columns.astype(str).str.strip()

    col_sc = "SOLICITAÇÃO"
    col_criticidade = "CRITICIDADE"

    hoje = pd.to_datetime(data_base)
    hoje_str = hoje.strftime("%Y-%m-%d")
    ontem_str = (hoje - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # Toda a transformação/cálculo puro (normalização de CC, join de
    # Criticidade, Days, Tem_Pedido, aging, backlog "em aberto", SLA médio
    # e o snapshot do dia) vive em logica_panorama.processar_panorama - só
    # DataFrame in, DataFrame/valores out, sem nenhuma chamada st.*, o que
    # permite testar essa lógica sem rodar o Streamlit (ver tests/).
    resultado = processar_panorama(df, df_criticidade, df_pedidos, hoje)
    df = resultado["df"]
    df_aberto = resultado["df_aberto"]
    unique_scs_aberto = resultado["unique_scs_aberto"]
    total_linhas_aberto = resultado["total_linhas_aberto"]
    total_sc_unicas_aberto = resultado["total_sc_unicas_aberto"]
    sem_pedido_total = resultado["sem_pedido_total"]
    sla_geral_rot = resultado["sla_geral_rot"]
    sla_geral_emg = resultado["sla_geral_emg"]
    snapshot_atual = resultado["snapshot_atual"]

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
        <div class="app-header">
            <div>
                <h1 class="app-title">Panorama de Requisições Pendentes de Compra</h1>
                <div class="app-subtitle">Diagnóstico e validação estratégica — volumetria, criticidade e status dos itens em aberto</div>
            </div>
            <div class="app-chips">
                <span class="chip"><span class="chip-dot"></span>Google Sheets</span>
                <span class="chip">Atualizado em <b>{hoje.strftime("%d/%m/%Y")}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    def criar_gauge(
        titulo, valor, max_val, cor_barra, sufixo="", altura=130, title_size=10, rodape=None
    ):
      fig = go.Figure(
          go.Indicator(
              mode="gauge+number",
              value=valor,
              number={
                  "suffix": sufixo,
                  "font": {
                      "size": 24,
                      "color": tokens_tema["text"],
                      "family": familia_fonte_grafico,
                  },
              },
              title={
                  "text": titulo,
                  "font": {
                      "size": title_size + 1,
                      "color": tokens_tema["muted"],
                      "family": familia_fonte_grafico,
                  },
              },
              gauge={
                  "axis": {"range": [None, max_val], "visible": False},
                  "bar": {"color": cor_barra, "thickness": 0.32},
                  "bgcolor": tokens_tema["surface2"],
                  "borderwidth": 0,
              },
          )
      )
      if rodape:
        fig.add_annotation(
            text=rodape, x=0.5, y=0, xref="paper", yref="paper",
            xanchor="center", yanchor="top", yshift=-6, showarrow=False,
            font=dict(size=13, color=cor_barra, family=familia_fonte_grafico),
        )
      fig.update_layout(
          height=altura,
          margin=dict(l=20, r=20, t=40, b=30 if rodape else 5),
          paper_bgcolor="rgba(0,0,0,0)",
          plot_bgcolor="rgba(0,0,0,0)",
      )
      return fig

    def criar_gauge_sla(valor, max_val, limite, cor_barra):
      fig = go.Figure(
          go.Indicator(
              mode="gauge+number",
              value=valor,
              number={
                  "font": {
                      "size": 20,
                      "color": tokens_tema["text"],
                      "family": familia_fonte_grafico,
                  }
              },
              gauge={
                  "axis": {"range": [0, max_val], "visible": False},
                  "bar": {"color": cor_barra, "thickness": 0.32},
                  "bgcolor": tokens_tema["surface2"],
                  "borderwidth": 0,
                  "threshold": {
                      "line": {"color": "#ef4444", "width": 2},
                      "thickness": 0.9,
                      "value": limite,
                  },
              },
          )
      )
      fig.update_layout(
          height=96,
          margin=dict(l=10, r=10, t=16, b=4),
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

      st.markdown(
          f"""
            <div class="card" style="display: flex; flex-direction: column; justify-content: center; box-sizing: border-box; height: 150px; padding: .6rem 1rem;">
                <div class="kpi-label">Volumetria em aberto</div>
                <div style="display: flex; gap: 1.6rem; margin-top: .3rem;">
                    <div>
                        <div class="kpi-value" style="color: {tokens_tema['accent']} !important;">{total_sc_unicas_aberto}</div>
                        <div class="kpi-sub">Solicitações (SCs)</div>
                    </div>
                    <div>
                        <div class="kpi-value" style="color: #f59e0b !important;">{sem_pedido_total}</div>
                        <div class="kpi-sub">Itens sem pedido</div>
                    </div>
                </div>
                <div style="margin-top: .45rem; padding-top: .4rem; border-top: 1px solid var(--border); font-size: .72rem; color: var(--muted) !important;">{texto_comparativo}</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

    def render_gauge(col, titulo, valor, max_val, cor, key_suffix):
      with col:
        perc = (valor / max_val * 100) if max_val > 0 else 0
        st.plotly_chart(
            criar_gauge(titulo, valor, max_val, cor, altura=150, rodape=f"{perc:.1f}%"),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"gauge_superior_{key_suffix}",
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
        "#3b82f6",
        "rot",
    )
    render_gauge(
        row1_c3,
        "EMERGENCIAL",
        qtd_emg,
        total_linhas_aberto,
        "#8b5cf6",
        "emg",
    )

    with row1_div:
      st.markdown(
          f"""
            <div style="border-left: 1px solid var(--border); height: 120px; margin: auto; margin-top: 5px;"></div>
            """,
          unsafe_allow_html=True,
      )

    render_gauge(
        row1_c4,
        "NO PRAZO",
        qtd_no_prazo,
        total_linhas_aberto,
        "#22c55e",
        "no_prazo",
    )
    render_gauge(
        row1_c5,
        "ATENÇÃO",
        qtd_atencao,
        total_linhas_aberto,
        "#f59e0b",
        "atencao",
    )
    render_gauge(
        row1_c6,
        "FORA DO PRAZO",
        qtd_fora,
        total_linhas_aberto,
        "#ef4444",
        "fora_prazo",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("---")
    row2_c1, row2_c2 = st.columns(2)

    with row2_c1:
      st.markdown(
          '<div class="section-header">TOP 10 CC (VOLUME DE ITENS EM ABERTO)</div>',
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
              cliponaxis=False,
              textfont=dict(
                  size=11,
                  color=cor_texto_grafico,
                  family=familia_fonte_grafico,
              ),
              marker_color=cores_barras[::-1],
          )
      )
      fig_cc_it.update_layout(
          xaxis_title="Qtd. Itens em aberto",
          yaxis_title="",
          plot_bgcolor="rgba(0,0,0,0)",
          paper_bgcolor="rgba(0,0,0,0)",
          font=dict(color=cor_texto_grafico),
          margin=dict(l=5, r=34, t=10, b=10),
          height=320,
          xaxis=dict(
              showgrid=True,
              gridcolor=tokens_tema["grade"],
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
          '<div class="section-header">TOP 10 CC (QTD. REQUISIÇÕES EM ABERTO)</div>',
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
              cliponaxis=False,
              textfont=dict(
                  size=11,
                  color=cor_texto_grafico,
                  family=familia_fonte_grafico,
              ),
              marker_color=cores_barras_sc[::-1],
          )
      )
      fig_cc_sc.update_layout(
          xaxis_title="Qtd. Requisições (SCs) em aberto",
          yaxis_title="",
          plot_bgcolor="rgba(0,0,0,0)",
          paper_bgcolor="rgba(0,0,0,0)",
          font=dict(color=cor_texto_grafico),
          margin=dict(l=5, r=34, t=10, b=10),
          height=320,
          xaxis=dict(
              showgrid=True,
              gridcolor=tokens_tema["grade"],
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

    st.markdown("---")
    # Top 10 centros de custo por nº de Solicitações (SCs únicas) de cada
    # criticidade no ano - mesma base e mesma regra de CRITICIDADE do relatório
    # "Criticidade das Solicitações" (a aba Solicitacoes/Criticidade_Solicitacoes).
    df_top10_ano = df.dropna(subset=[col_sc]).copy()
    df_top10_ano = df_top10_ano[df_top10_ano[COL_DT_EMISSAO].dt.year == hoje.year]
    df_top10_ano["_sc_top10"] = (
        df_top10_ano[col_sc].astype(str).str.split(".").str[0].str.zfill(6)
    )
    df_top10_ano["_crit_top10"] = (
        df_top10_ano[col_criticidade].astype(str).str.strip().str.upper()
        # A base usa "COMPRA DIRETA" (singular) desde 2026-11-23; aceita o
        # plural antigo caso alguma linha ainda venha assim.
        .replace({"COMPRAS DIRETA": "COMPRA DIRETA"})
    )
    top10_criticidades = [
        ("EMERGENCIAL", "EMERGENCIAL", "#B4462C", "plotly_top10_emergencial"),
        ("ROTINEIRA", "ROTINEIRA", "#2F6F5E", "plotly_top10_rotineira"),
        ("COMPRA DIRETA", "COMPRA DIRETA", "#C98A2B", "plotly_top10_compra_direta"),
    ]
    for coluna_top10, (valor_crit, rotulo_crit, cor_crit, chave_crit) in zip(
        st.columns(3), top10_criticidades
    ):
      with coluna_top10:
        st.markdown(
            f'<div class="section-header">TOP 10 SOLICITAÇÕES {rotulo_crit}'
            f" ({hoje.year})</div>",
            unsafe_allow_html=True,
        )
        top10_crit = (
            df_top10_ano[df_top10_ano["_crit_top10"] == valor_crit]
            .groupby("CC_clean")["_sc_top10"]
            .nunique()
            .sort_values(ascending=False)
            .head(10)
            .sort_values(ascending=True)
        )
        if top10_crit.empty:
          st.info(f"Nenhuma solicitação {rotulo_crit.lower()} em {hoje.year}.")
          continue
        fig_top10_crit = go.Figure(
            go.Bar(
                x=top10_crit.values,
                y=top10_crit.index.astype(str),
                orientation="h",
                text=top10_crit.values,
                textposition="outside",
                cliponaxis=False,
                textfont=dict(
                    size=11, color=cor_texto_grafico, family=familia_fonte_grafico
                ),
                marker=dict(
                    color=cor_crit,
                    opacity=[0.8] * (len(top10_crit) - 1) + [1],
                ),
            )
        )
        fig_top10_crit.update_layout(
            xaxis_title="Qtd. Solicitações",
            yaxis_title="",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=320,
            font=dict(color=cor_texto_grafico),
            margin=dict(l=5, r=45, t=10, b=10),
            xaxis=dict(
                showgrid=True,
                gridcolor=tokens_tema["grade"],
                range=[0, int(top10_crit.max()) * 1.3],
            ),
            yaxis=dict(
                type="category",
                tickfont=dict(family=familia_fonte_grafico, color=cor_texto_grafico),
            ),
        )
        st.plotly_chart(
            fig_top10_crit,
            use_container_width=True,
            config={"displayModeBar": False},
            key=chave_crit,
        )

    st.markdown("---")
    st.markdown(
        '<div class="section-header" style="background-color: #2b4c7e;">DESEMPENHO'
        " INDIVIDUAL POR COMPRADOR & PRODUTIVIDADE DIÁRIA</div>",
        unsafe_allow_html=True,
    )

    row4_c1, row4_c2, row4_c3 = st.columns(3)
    compradores = ["Ednilson", "Dayana", "Sílvio"]
    colunas_st = [row4_c1, row4_c2, row4_c3]

    color_status_map = {
        "No Prazo": "#22c55e",
        "Atenção": "#f59e0b",
        "Fora do Prazo": "#ef4444",
    }
    ordem_status_aberto = ["Fora do Prazo", "Atenção", "No Prazo"]

    def criar_dialog_solicitacoes_abertas(comp):
      # st.dialog identifica o elemento internamente pelo título + local de
      # definição - se a função fosse definida uma vez só (fora do loop) e
      # chamada pra 3 compradores diferentes, uma seleção "grudada" de um
      # gráfico anterior (o Plotly não limpa selection sozinho) podia
      # coincidir com a de outro no mesmo rerun e colidir ("multiple dialog
      # elements with the same auto-generated ID"). Título com o nome do
      # comprador dá um ID único por comprador.
      @st.dialog(f"Solicitações em Aberto — {comp}", width="large")
      def mostrar_solicitacoes_abertas_dialog(df_lista, status_clicado=None):
        rotulo = f"{comp} — {status_clicado}" if status_clicado else comp
        st.markdown(f"**{rotulo}** — {len(df_lista)} item(ns)")
        colunas_disponiveis = [
            c
            for c in [col_sc, COL_COTACAO, "CENTRO DE CUSTO", "PRODUTO", "DESCRICAO", col_criticidade, "Days"]
            if c in df_lista.columns
        ]
        tabela_dialog = (
            df_lista[colunas_disponiveis]
            .rename(columns={
                col_sc: "Solicitação",
                COL_COTACAO: "Cotação",
                col_criticidade: "Criticidade",
                "Days": "Dias",
            })
            .sort_values("Dias", ascending=False)
        )
        st.dataframe(
            tabela_dialog, use_container_width=True, hide_index=True, height=420,
            column_config=estilo.colunas_centralizadas(
                tabela_dialog,
                ["Solicitação", "Cotação", "CENTRO DE CUSTO", "PRODUTO", "Dias"],
            ),
        )

      return mostrar_solicitacoes_abertas_dialog

    for comp, col_st in zip(compradores, colunas_st):
      with col_st:
        st.markdown(
            f'<div style="text-align: center; font-weight: {weight_resumo}; font-size: 1.05rem; margin-bottom: 2px;">👤 {comp}</div>',
            unsafe_allow_html=True,
        )

        df_comp_total = df[df["Comprador_Resp"] == comp].copy()
        df_comp_aberto = df_comp_total[
            df_comp_total["Status_Detalhado"] != "Atendidas"
        ].copy()

        # "Fila" é o backlog atual - só itens ainda em aberto, senão soma
        # junto solicitações já Atendidas que nunca tiveram Pedido formal
        # (compra direta, serviço, rejeitado etc.) e o número não bate com
        # a soma das barras de No Prazo/Atenção/Fora do Prazo logo abaixo.
        sem_ped_atual = int(
            (~df_comp_aberto["Tem_Pedido"].fillna(False).astype(bool)).sum()
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
            df_comp_crit = df_comp_aberto[
                df_comp_aberto[col_criticidade]
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
              altura=140,
              title_size=10,
          )
          st.plotly_chart(
              fig_gauge,
              use_container_width=True,
              config={"displayModeBar": False},
              key=f"gauge_rendimento_{comp}",
          )

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

            comp_stats["Texto_Label"] = comp_stats.apply(
                lambda row: f"{int(row['Quantidade'])} ({row['Percentual']}%)",
                axis=1,
            )

            fig_comp_ind = px.bar(
                comp_stats,
                x="Percentual",
                y="Status_Detalhado",
                orientation="h",
                text="Texto_Label",
                color="Status_Detalhado",
                color_discrete_map=color_status_map,
            )
            fig_comp_ind.update_traces(
                textposition="outside",
                textfont=dict(
                    size=10,
                    color=cor_texto_grafico,
                    family=familia_fonte_grafico,
                ),
            )
            fig_comp_ind.update_layout(
                showlegend=False,
                xaxis_title="% Backlog",
                yaxis_title="",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=158,
                font=dict(color=cor_texto_grafico),
                margin=dict(l=5, r=25, t=6, b=36),
                xaxis=dict(
                    showgrid=True,
                    gridcolor=tokens_tema["grade"],
                    range=[0, max(comp_stats["Percentual"].max() * 1.35, 100)],
                    tickfont=dict(size=8, color=cor_texto_grafico),
                ),
                yaxis=dict(
                    type="category",
                    categoryorder="array",
                    categoryarray=ordem_status_aberto,
                    tickfont=dict(
                        family=familia_fonte_grafico,
                        size=9,
                        color=cor_texto_grafico,
                    ),
                ),
            )
            evento_clique = st.plotly_chart(
                fig_comp_ind,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"bar_backlog_{comp}",
                on_select="rerun",
                selection_mode="points",
            )
            st.markdown(
                "<div style='text-align: center; font-size: 0.68rem; color: #64748b; margin-top: -8px;'>💡 Clique numa barra pra ver as solicitações</div>",
                unsafe_allow_html=True,
            )

            pontos_selecionados = (
                evento_clique.get("selection", {}).get("points", [])
                if evento_clique
                else []
            )
            if pontos_selecionados:
                status_clicado = pontos_selecionados[0].get("y")
                if status_clicado in comp_stats["Status_Detalhado"].values:
                  df_status_clicado = df_comp_aberto[
                      df_comp_aberto["Status_Detalhado"] == status_clicado
                  ]
                  criar_dialog_solicitacoes_abertas(comp)(df_status_clicado, status_clicado)
          else:
            st.info(f"Fila limpa para {comp}.")

          st.markdown(
              f"""
                    <div class="card" style="text-align: center; padding: .8rem 1rem; margin-top: 8px; font-size: .78rem; line-height: 1.55;">
                        <span style="color: #22c55e !important; font-weight: 600;">✓ {qtd_atendidas} atendidas</span>
                        <span style="color: var(--muted) !important;"> · </span>
                        <span style="color: {tokens_tema['accent']} !important; font-weight: 600;">{qtd_pedidos_gerados} c/ pedido</span><br>
                        <span style="font-weight: 600;">⏳ {sem_ped_atual} itens s/ pedido (fila)</span><br>
                        <span style="font-size: .68rem; color: var(--muted) !important;">{texto_produtividade}</span>
                    </div>
                    """,
              unsafe_allow_html=True,
          )

          cor_rot = "#ef4444" if sla_rot_val > 15 else "#3b82f6"
          fig_rot = criar_gauge_sla(sla_rot_val, 30, 15, cor_rot)

          cor_emg = "#ef4444" if sla_emg_val > 3 else "#8b5cf6"
          fig_emg = criar_gauge_sla(sla_emg_val, 20, 3, cor_emg)

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

    st.markdown("---")
    st.markdown(
        '<div class="section-header">SLA MÉDIO GERAL CONSOLIDADO</div>',
        unsafe_allow_html=True,
    )

    col_box1, col_box2 = st.columns(2)

    for coluna_sla, titulo_sla, limite_sla, valor_sla, cor_ok_sla in (
        (col_box1, "SLA Rotineira médio", 15, sla_geral_rot, "#3b82f6"),
        (col_box2, "SLA Emergencial médio", 3, sla_geral_emg, "#8b5cf6"),
    ):
      with coluna_sla:
        cor_val_sla = "#ef4444" if valor_sla > limite_sla else cor_ok_sla
        st.markdown(
            f"""
            <div class="card" style="text-align: center; border-top: 3px solid {cor_val_sla};">
                <div class="kpi-label">{titulo_sla}</div>
                <div class="kpi-sub" style="margin-bottom: .35rem;">limite: {limite_sla} dias</div>
                <div class="kpi-value" style="color: {cor_val_sla} !important;">{valor_sla} <span style="font-size: 1rem; font-weight: 500;">dias</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    _, crit_status_c1, crit_status_c2, _ = st.columns([0.8, 1.2, 0.8, 0.8])

    with crit_status_c1:
      st.markdown(
          '<div class="section-header">CRITICIDADE VS STATUS (QTD.'
          ' ITENS)</div>',
          unsafe_allow_html=True,
      )
      if col_criticidade:
        df_crit_stat = df_aberto[
            df_aberto[col_criticidade]
            .astype(str)
            .str.upper()
            .isin(["ROTINEIRA", "EMERGENCIAL"])
        ]
        if not df_crit_stat.empty:
          crit_stats = (
              df_crit_stat.groupby([col_criticidade, "Status_Detalhado"])
              .size()
              .reset_index(name="Quantidade")
          )
          color_map = {
              "NO PRAZO": "#22c55e",
              "ATENÇÃO": "#f59e0b",
              "FORA DO PRAZO": "#ef4444",
          }
          fig_crit_stat = go.Figure()
          for status_val in ["NO PRAZO", "ATENÇÃO", "FORA DO PRAZO"]:
            df_sub = crit_stats[
                crit_stats["Status_Detalhado"].str.upper() == status_val
            ]
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
                  xanchor="center",
                  x=0.5,
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
                  gridcolor=tokens_tema["grade"],
              ),
          )
          st.plotly_chart(
              fig_crit_stat,
              use_container_width=True,
              config={"displayModeBar": False},
              key="plotly_criticidade_vs_status",
          )

    with crit_status_c2:
      st.markdown(
          '<div class="section-header">ITENS CRÍTICOS</div>',
          unsafe_allow_html=True,
      )
      criticos_df = unique_scs_aberto[unique_scs_aberto["Days"] >= 20]
      top_critical = criticos_df.sort_values(by="Days", ascending=False)[
          [col_sc, "CC_clean", "Days"]
      ].head(8)
      top_critical.columns = ["Nº SC", "C. CUSTO", "ATRASO"]
      top_critical["ATRASO"] = top_critical["ATRASO"].astype(str) + " DIAS 🔥"
      # Mesma altura do gráfico ao lado (320px) pra as duas caixas alinharem.
      with st.container(key="itens_criticos_wrap"):
        st.dataframe(
            top_critical, use_container_width=True, height=320, hide_index=True
        )

    st.markdown("---")
    MESES_PT = {
        1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
        7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
    }

    st.markdown(
        '<div class="section-header">FECHAMENTO MÊS DE ATENDIMENTO DE'
        " SOLICITAÇÃO</div>",
        unsafe_allow_html=True,
    )

    # O widget em si só é desenhado mais abaixo (depois do gráfico, a
    # pedido) - o valor já lido aqui vem do session_state da rodada
    # anterior, que o Streamlit já atualiza antes do script re-executar.
    cc_selecionados_mensal = st.session_state.get("filtro_cc_panorama_mensal", [])

    df_mensal = df.dropna(subset=[COL_DT_EMISSAO]).copy()
    if cc_selecionados_mensal:
      df_mensal = df_mensal[df_mensal["CC_clean"].isin(cc_selecionados_mensal)]
    df_mensal["_periodo"] = periodo_fechamento(df_mensal[COL_DT_EMISSAO])
    df_mensal["_atendido"] = df_mensal["Status_Detalhado"] == "Atendidas"

    # Jan do ano corrente até o mês de fechamento em andamento (ciclo 26 a
    # 25: de 26/set em diante já é "out") - meses passados aparecem mesmo
    # com 0 (pra não mascarar uma lacuna real na base), meses futuros nem
    # entram na lista (não faz sentido mostrar um mês que ainda não chegou).
    periodo_atual = periodo_fechamento(pd.Series([hoje])).iloc[0]
    periodos_ano = pd.period_range(
        start=f"{periodo_atual.year}-01", end=periodo_atual, freq="M"
    )
    resumo_mensal = (
        df_mensal.groupby("_periodo")["_atendido"]
        .agg(Atendidos="sum", Total="count")
        .reindex(periodos_ano, fill_value=0)
        .reset_index()
        .rename(columns={"index": "_periodo"})
    )
    resumo_mensal["Pendentes"] = resumo_mensal["Total"] - resumo_mensal["Atendidos"]
    resumo_mensal["_mes_label"] = resumo_mensal["_periodo"].apply(
        lambda p: f"{MESES_PT[p.month]}/{str(p.year)[-2:]}"
    )

    cor_atendido = "#22c55e"
    cor_pendente = "#f59e0b"

    acumulado_atendidos = int(resumo_mensal["Atendidos"].sum())
    acumulado_pendentes = int(resumo_mensal["Pendentes"].sum())

    # Headroom no eixo Y pra rótulo "outside" (barra baixa) não cortar no
    # topo do gráfico - "auto" já escolhe dentro/fora conforme cabe, isso
    # só garante espaço quando escolhe fora. Só considera os meses (o
    # Acumulado vira um cartão à parte, não uma barra - senão ele sozinho
    # estoura a escala e some com a variação entre os meses).
    maior_valor = max(
        int(resumo_mensal["Atendidos"].max() or 0),
        int(resumo_mensal["Pendentes"].max() or 0),
    )
    teto_eixo_y = maior_valor * 1.18 if maior_valor > 0 else 1

    col_grafico_mensal, col_acumulado_mensal = st.columns([4, 1])

    with col_grafico_mensal:
      fig_mensal = go.Figure()
      fig_mensal.add_trace(
          go.Bar(
              x=resumo_mensal["_mes_label"],
              y=resumo_mensal["Atendidos"],
              name="Atendidos",
              marker_color=cor_atendido,
              text=resumo_mensal["Atendidos"],
              textposition="auto",
              textfont=dict(color=cor_texto_grafico, family=familia_fonte_grafico),
          )
      )
      fig_mensal.add_trace(
          go.Bar(
              x=resumo_mensal["_mes_label"],
              y=resumo_mensal["Pendentes"],
              name="Pendentes",
              marker_color=cor_pendente,
              text=resumo_mensal["Pendentes"],
              textposition="auto",
              textfont=dict(color=cor_texto_grafico, family=familia_fonte_grafico),
          )
      )
      fig_mensal.update_layout(
          barmode="group",
          xaxis_title="",
          yaxis_title="Qtd. Itens",
          plot_bgcolor="rgba(0,0,0,0)",
          paper_bgcolor="rgba(0,0,0,0)",
          height=340,
          margin=dict(l=50, r=24, t=50, b=40),
          font=dict(color=cor_texto_grafico),
          legend=dict(
              orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
              font=dict(family=familia_fonte_grafico, size=10, color=cor_texto_grafico),
          ),
          xaxis=dict(
              showgrid=False,
              tickfont=dict(size=11, family=familia_fonte_grafico, color=cor_texto_grafico),
          ),
          yaxis=dict(
              showgrid=True,
              gridcolor=tokens_tema["grade"],
              range=[0, teto_eixo_y],
          ),
      )
      st.plotly_chart(
          fig_mensal,
          use_container_width=True,
          config={"displayModeBar": False},
          key="plotly_panorama_mensal",
      )

    with col_acumulado_mensal:
      total_acumulado = acumulado_atendidos + acumulado_pendentes
      fig_acumulado = go.Figure(
          go.Pie(
              labels=["Atendidos", "Pendentes"],
              values=[acumulado_atendidos, acumulado_pendentes],
              marker=dict(colors=[cor_atendido, cor_pendente]),
              hole=0.6,
              textinfo="value+percent",
              textposition="outside",
              textfont=dict(color=cor_texto_grafico, family=familia_fonte_grafico, size=10),
              sort=False,
              # Com só 2 fatias, os rótulos "outside" nascem nos pontos médios
              # de cada fatia - que ficam quase opostos um do outro. Sem
              # girar, esse ponto cai perto de cima/baixo do gráfico (bate no
              # "Acumulado" embaixo). Rotacionar 90° joga os dois pontos pra
              # esquerda/direita, fora da área de cima e de baixo.
              rotation=90,
          )
      )
      fig_acumulado.update_layout(
          showlegend=False,
          paper_bgcolor="rgba(0,0,0,0)",
          height=300,
          margin=dict(l=55, r=55, t=30, b=10),
          font=dict(color=cor_texto_grafico),
          annotations=[
              dict(
                  text=f"<b>{total_acumulado}</b><br>Total",
                  x=0.5, y=0.5,
                  showarrow=False,
                  font=dict(size=14, family=familia_fonte_grafico, color=cor_texto_grafico),
              )
          ],
      )
      st.plotly_chart(
          fig_acumulado,
          use_container_width=True,
          config={"displayModeBar": False},
          key="plotly_acumulado_mensal",
      )
      st.markdown(
          f'<div class="kpi-label" style="text-align: center; margin-top: -6px;">Acumulado atual</div>',
          unsafe_allow_html=True,
      )

    col_filtro_cc_mensal, _ = st.columns([1, 4])
    with col_filtro_cc_mensal:
      opcoes_cc_mensal = sorted(df["CC_clean"].dropna().unique().tolist())
      st.multiselect(
          "Centro de Custo:",
          options=opcoes_cc_mensal,
          default=[],
          placeholder="Todos",
          key="filtro_cc_panorama_mensal",
      )

    with st.expander("Ver dados em formato de tabela"):
      tabela_mensal = resumo_mensal[["_mes_label", "Atendidos", "Pendentes", "Total"]].rename(
          columns={"_mes_label": "Mês"}
      )
      linha_acumulado = pd.DataFrame([{
          "Mês": "Acumulado",
          "Atendidos": int(tabela_mensal["Atendidos"].sum()),
          "Pendentes": int(tabela_mensal["Pendentes"].sum()),
          "Total": int(tabela_mensal["Total"].sum()),
      }])
      tabela_mensal = pd.concat([tabela_mensal, linha_acumulado], ignore_index=True)
      st.dataframe(tabela_mensal, use_container_width=True, hide_index=True)

    renderizar_criticidade_solicitacoes(
        df, is_tema_claro, cor_texto_grafico, familia_fonte_grafico
    )

  except Exception as e:
    st.error(f"⚠️ Erro analítico no processamento: {e}")
