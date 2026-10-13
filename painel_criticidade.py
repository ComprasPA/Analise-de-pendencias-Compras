"""Secao "Criticidade das Solicitacoes" do painel: filtros, KPIs, rosca,
evolucao mensal e tabela por centro de custo com detalhamento (popup) das
solicitacoes. Usa so os dados que o painel ja carrega (abas Solicitacoes e
Criticidade_Solicitacoes, via logica_panorama.processar_panorama).

Toda a regra (agrupamento por SC, filtros, agregacoes) vive em
logica_criticidade.py; aqui fica so a renderizacao Streamlit/Plotly. Roda
como fragmento: mexer num filtro daqui re-executa so esta secao, nao o
painel inteiro.
"""
import plotly.graph_objects as go
import streamlit as st

from logica_criticidade import (
    CATS,
    MESES_NOME,
    SEM_CRITICIDADE,
    agregado_por_cc,
    aplicar_filtros,
    contagem_por_criticidade,
    evolucao_mensal,
    preparar_solicitacoes,
    rotulo_mes,
)

COR_CAT = {
    "Rotineira": "#2F6F5E",
    "Compras direta": "#C98A2B",
    "Emergencial": "#B4462C",
    "Correção de Processo": "#6B6E9A",
    SEM_CRITICIDADE: "#8C8F87",
}
COMPRADORES = ["Ednilson", "Dayana", "Sílvio"]


def _n(valor):
  return f"{int(valor):,}".replace(",", ".")


def _pct(valor):
  return f"{valor:.1f}".replace(".", ",")


def _data_br(ts):
  return ts.strftime("%d/%m/%Y")


def _limpar_filtros():
  st.session_state["crit_ano"] = []
  st.session_state["crit_mes"] = []
  st.session_state["crit_cc"] = []
  st.session_state["crit_comp"] = list(COMPRADORES)
  st.session_state["crit_cat"] = list(CATS)
  st.session_state["crit_busca"] = ""


def _abrir_detalhe(df, cc, filtros):
  """Popup com as solicitacoes de um centro de custo (respeita ano/mes/
  comprador/busca, ignora os filtros globais de centro de custo e criticidade)."""

  @st.dialog(f"Centro de custo {cc}", width="large")
  def _dialogo():
    base = aplicar_filtros(
        df, anos=filtros["anos"], meses=filtros["meses"], comps=filtros["comps"],
        busca=filtros["busca"], ignorar_cc_crit=True,
    )
    base = base[base["cc"] == cc]
    totais = {"Todas": len(base), **contagem_por_criticidade(base)}
    escolha = st.pills(
        "Criticidade",
        ["Todas"] + CATS,
        selection_mode="single",
        default="Todas",
        key="crit_dlg_cat",
        format_func=lambda c: f"{c} ({_n(totais[c])})",
    ) or "Todas"

    lista = base if escolha == "Todas" else base[base["crit"] == escolha]
    lista = lista.sort_values("dt", ascending=False)
    st.caption(
        f"{_n(len(lista))} solicitação(ões)"
        + ("" if escolha == "Todas" else f' — criticidade "{escolha}"')
    )
    if lista.empty:
      st.info("Nenhuma solicitação encontrada para esse filtro.")
      return
    tabela = lista.assign(Data=lista["dt"].dt.strftime("%d/%m/%y"))[
        ["sol", "cot", "desc", "crit", "comp", "status", "itens", "Data"]
    ].rename(
        columns={
            "sol": "Solicitação", "cot": "Cotação", "desc": "Descrição",
            "crit": "Criticidade", "comp": "Comprador", "status": "Status", "itens": "Itens",
        }
    )
    st.dataframe(tabela, hide_index=True, use_container_width=True, height=420)

  _dialogo()


@st.fragment
def _secao(df, tema):
  cor_texto = tema["cor_texto"]
  fonte = tema["fonte"]
  fundo_card = "#f1f5f9" if tema["claro"] else "#1a202c"
  borda = "#e2e8f0" if tema["claro"] else "#333333"
  mudo = "#64748b" if tema["claro"] else "#94a3b8"
  grade = "#e2e8f0" if tema["claro"] else "#333333"

  st.markdown(
      "<style>"
      ".st-key-crit_tabela_wrap div[data-testid='stDataFrame']"
      "{max-width:100% !important;margin:0 !important;}"
      f".st-key-crit_limpar button{{background:{fundo_card} !important;border:1px solid {borda} !important;}}"
      f".st-key-crit_limpar button p{{color:{cor_texto} !important;}}"
      "</style>",
      unsafe_allow_html=True,
  )

  anos_disp = sorted(df["ano"].unique())
  meses_disp = sorted(df["mes"].unique())
  ccs_disp = sorted(df["cc"].unique(), key=lambda c: (len(c), c))

  c_ano, c_mes, c_cc, c_comp, c_busca = st.columns([0.9, 1.2, 1.4, 2.0, 2.2])
  with c_ano:
    anos = st.multiselect("Ano", anos_disp, placeholder="Todos os anos", key="crit_ano")
  with c_mes:
    meses = st.multiselect(
        "Mês", meses_disp, placeholder="Todos os meses", key="crit_mes",
        format_func=lambda m: MESES_NOME.get(m, m),
    )
  with c_cc:
    ccs = st.multiselect("Centro de custo", ccs_disp, placeholder="Todos os centros", key="crit_cc")
  with c_comp:
    comps_sel = st.pills(
        "Comprador", COMPRADORES, selection_mode="multi", default=COMPRADORES, key="crit_comp",
    )
  with c_busca:
    busca = st.text_input(
        "Buscar (descrição, comprador, nº da SC ou cotação)",
        placeholder="Ex.: robô, 141398, 021028…", key="crit_busca",
    )

  c_cat, c_limpar = st.columns([6, 1])
  with c_cat:
    crits_sel = st.pills(
        "Criticidade", CATS, selection_mode="multi", default=CATS, key="crit_cat",
    )
  with c_limpar:
    st.markdown("<div style='height: 1.7rem'></div>", unsafe_allow_html=True)
    st.button("Limpar filtros", on_click=_limpar_filtros, key="crit_limpar", use_container_width=True)

  comps = comps_sel or COMPRADORES
  crits = crits_sel or CATS
  filtros = {"anos": anos, "meses": meses, "comps": comps, "busca": busca}

  filtrado = aplicar_filtros(
      df, anos=anos, meses=meses, ccs=ccs, crits=crits, comps=comps, busca=busca
  )

  ativos = []
  if anos:
    ativos.append(f"Ano: {', '.join(anos)}")
  if meses:
    ativos.append(f"Mês: {', '.join(MESES_NOME[m] for m in meses)}")
  if ccs:
    ativos.append(f"CC {', '.join(ccs)}")
  if len(crits) < len(CATS):
    ativos.append(", ".join(crits))
  if len(comps) < len(COMPRADORES):
    ativos.append(", ".join(comps))
  if busca:
    ativos.append(f'"{busca}"')
  if ativos:
    st.caption(f"Filtros ativos: {' · '.join(ativos)} — {_n(len(filtrado))} de {_n(len(df))} solicitações")
  else:
    st.caption(f"Sem filtros aplicados — {_n(len(df))} solicitações no período")

  st.markdown(
      f"<div style='display:flex;justify-content:space-between;align-items:baseline;margin:4px 0 10px;'>"
      f"<span style='font-size:0.8rem;color:{mudo} !important;'>"
      f"{_data_br(df['dt'].min())} — {_data_br(df['dt'].max())}</span>"
      f"<span style='font-size:1.6rem;font-weight:bold;color:{cor_texto} !important;'>"
      f"{_n(len(filtrado))} <span style='font-size:0.8rem;font-weight:normal;color:{mudo} !important;'>solicitações</span></span>"
      f"</div>",
      unsafe_allow_html=True,
  )

  contagem = contagem_por_criticidade(filtrado)
  total = len(filtrado)

  for coluna, cat in zip(st.columns(len(CATS)), CATS):
    with coluna:
      pct = contagem[cat] / total * 100 if total else 0
      st.markdown(
          f"<div style='background:{fundo_card};border:1px solid {borda};"
          f"border-left:4px solid {COR_CAT[cat]};border-radius:4px;padding:12px 16px;'>"
          f"<div style='font-size:0.85rem;color:{mudo} !important;'>{cat}</div>"
          f"<div style='font-size:1.7rem;font-weight:bold;line-height:1.15;white-space:nowrap;color:{cor_texto} !important;'>{_pct(pct)}%</div>"
          f"<div style='font-size:0.78rem;color:{mudo} !important;'>{_n(contagem[cat])} solicitações</div>"
          f"</div>",
          unsafe_allow_html=True,
      )

  st.markdown("<div style='height: 14px'></div>", unsafe_allow_html=True)
  st.markdown('<div class="section-header">VISÃO GERAL</div>', unsafe_allow_html=True)
  if total == 0:
    st.info("Nenhum registro corresponde aos filtros selecionados.")
    return

  col_rosca, col_legenda = st.columns([1, 1.6])
  with col_rosca:
    fig_rosca = go.Figure(
        go.Pie(
            labels=CATS,
            values=[contagem[c] for c in CATS],
            marker=dict(colors=[COR_CAT[c] for c in CATS]),
            hole=0.68,
            sort=False,
            textinfo="none",
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    fig_rosca.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        height=260,
        margin=dict(l=10, r=10, t=10, b=10),
        annotations=[
            dict(
                text=f"<b>{_n(total)}</b><br>solicitações", x=0.5, y=0.5, showarrow=False,
                font=dict(size=14, family=fonte, color=cor_texto),
            )
        ],
    )
    st.plotly_chart(
        fig_rosca, use_container_width=True, config={"displayModeBar": False}, key="crit_rosca"
    )
  with col_legenda:
    linhas = "".join(
        f"<div style='display:grid;grid-template-columns:14px 190px 48px 64px;justify-content:start;align-items:center;gap:12px;margin:12px 0;'>"
        f"<span style='width:12px;height:12px;border-radius:2px;background:{COR_CAT[c]};display:inline-block;'></span>"
        f"<span style='font-size:0.95rem;color:{cor_texto} !important;'>{c}</span>"
        f"<span style='font-size:0.85rem;text-align:right;color:{mudo} !important;'>{_n(contagem[c])}</span>"
        f"<span style='font-size:1.1rem;font-weight:bold;text-align:right;color:{COR_CAT[c]} !important;'>"
        f"{_pct(contagem[c] / total * 100)}%</span></div>"
        for c in CATS
    )
    st.markdown(
        f"<div style='padding-top:10px;'><div style='font-size:0.82rem;color:{mudo} !important;'>"
        f"Participação de cada criticidade sobre {_n(total)} solicitações no recorte atual.</div>{linhas}</div>",
        unsafe_allow_html=True,
    )

  st.markdown('<div class="section-header">EVOLUÇÃO MENSAL</div>', unsafe_allow_html=True)
  evolucao = evolucao_mensal(filtrado)
  rotulos = [rotulo_mes(ym) for ym in evolucao.index]
  totais_mes = evolucao.sum(axis=1)
  fig_mensal = go.Figure()
  for cat in CATS:
    fig_mensal.add_trace(
        go.Bar(
            x=rotulos, y=evolucao[cat], name=cat, marker_color=COR_CAT[cat],
            hovertemplate=f"{cat}: %{{y}}<extra></extra>",
        )
    )
  fig_mensal.add_trace(
      go.Scatter(
          x=rotulos, y=totais_mes, mode="text", text=totais_mes, textposition="top center",
          textfont=dict(color=cor_texto, family=fonte, size=11),
          showlegend=False, hoverinfo="skip",
      )
  )
  fig_mensal.update_layout(
      barmode="stack",
      plot_bgcolor="rgba(0,0,0,0)",
      paper_bgcolor="rgba(0,0,0,0)",
      height=340,
      margin=dict(l=50, r=10, t=40, b=40),
      font=dict(color=cor_texto),
      legend=dict(
          traceorder="normal",
          orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
          font=dict(family=fonte, size=10, color=cor_texto),
      ),
      xaxis=dict(type="category", showgrid=False, tickfont=dict(size=11, family=fonte, color=cor_texto)),
      yaxis=dict(
          title="Qtd. solicitações", showgrid=True, gridcolor=grade,
          range=[0, max(int(totais_mes.max()) * 1.15, 1)],
      ),
  )
  st.plotly_chart(
      fig_mensal, use_container_width=True, config={"displayModeBar": False}, key="crit_mensal"
  )

  st.markdown('<div class="section-header">POR CENTRO DE CUSTO</div>', unsafe_allow_html=True)
  st.caption("Selecione uma linha para abrir o detalhamento — contagem por criticidade e a lista das solicitações.")
  busca_cc = st.text_input("Buscar centro de custo na tabela", key="crit_busca_cc", placeholder="Ex.: 1238")
  agg = agregado_por_cc(filtrado)
  if busca_cc.strip():
    agg = agg[agg["cc"].str.contains(busca_cc.strip(), case=False, regex=False)]
  agg = agg.reset_index(drop=True)
  st.caption(f"{len(agg)} centros de custo no recorte atual")

  tabela = agg.rename(columns={"cc": "Centro de Custo"})
  config = {f"% {c}": st.column_config.NumberColumn(f"% {c}", format="%.1f%%") for c in CATS}
  with st.container(key="crit_tabela_wrap"):
    evento = st.dataframe(
        tabela, hide_index=True, use_container_width=True, column_config=config,
        on_select="rerun", selection_mode="single-row", key="crit_tabela_cc",
    )

  linhas_sel = evento.selection.rows if evento else []
  if linhas_sel and linhas_sel[0] < len(tabela):
    cc = tabela.iloc[linhas_sel[0]]["Centro de Custo"]
    if st.session_state.get("crit_cc_aberto") != cc:
      st.session_state["crit_cc_aberto"] = cc
      st.session_state["crit_dlg_cat"] = "Todas"
      _abrir_detalhe(df, cc, filtros)
  else:
    st.session_state["crit_cc_aberto"] = None

  st.caption(
      "Fonte: abas Solicitacoes e Criticidade_Solicitacoes · Unidade: Solicitação (SC) · "
      "Data de referência: Data de Aprovação (Data de Emissão quando vazia)"
  )


def renderizar_criticidade_solicitacoes(df_proc, is_tema_claro, cor_texto, fonte):
  st.markdown("---")
  st.markdown('<div class="section-header">CRITICIDADE DAS SOLICITAÇÕES</div>', unsafe_allow_html=True)
  st.caption(
      "Explore por ano, mês, centro de custo, comprador ou texto livre. Cada linha é uma Solicitação (SC)."
  )
  df = preparar_solicitacoes(df_proc)
  if df.empty:
    st.info("Sem solicitações para exibir.")
    return
  _secao(df, {"claro": is_tema_claro, "cor_texto": cor_texto, "fonte": fonte})
