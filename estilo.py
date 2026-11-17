"""Identidade visual do painel (CSS) - tokens de cor por tema + regras globais.

Fica separado de app.py pra manter o visual em um lugar só: trocar uma cor ou
a tipografia é mexer aqui, sem caçar CSS inline pelo painel. O app escolhe o
tema (claro/escuro) pelo toggle e injeta o resultado de gerar_css().
"""

FONTE = "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif"

TEMAS = {
    "escuro": {
        "bg": "#0b1220",
        "surface": "#111a2c",
        "surface2": "#17233a",
        "border": "#1f2d47",
        "text": "#e6ebf5",
        "muted": "#8d9ab5",
        "accent": "#5b8def",
        "accent_soft": "rgba(91, 141, 239, 0.16)",
        "shadow": "0 1px 2px rgba(0, 0, 0, 0.35), 0 8px 24px rgba(0, 0, 0, 0.18)",
        "grade": "#1f2d47",
        "texto_grafico": "#cbd5e6",
        "verde": "#4FA653",
        "laranja": "#F2951D",
        "eyebrow": "#F2951D",
    },
    "claro": {
        "bg": "#f3f5fa",
        "surface": "#ffffff",
        "surface2": "#f6f8fc",
        "border": "#e2e8f2",
        "text": "#1e293b",
        "muted": "#64748b",
        "accent": "#2f5bea",
        "accent_soft": "rgba(47, 91, 234, 0.10)",
        "shadow": "0 1px 2px rgba(15, 23, 42, 0.05), 0 8px 24px rgba(15, 23, 42, 0.05)",
        "grade": "#e2e8f2",
        "texto_grafico": "#334155",
        "verde": "#3E8E41",
        "laranja": "#F2861D",
        "eyebrow": "#CE6E10",
    },
}


def tokens(tema_claro):
  return TEMAS["claro" if tema_claro else "escuro"]


def gerar_css(tema_claro):
  t = tokens(tema_claro)
  variaveis = (
      ":root{"
      f"--bg:{t['bg']};--surface:{t['surface']};--surface2:{t['surface2']};"
      f"--border:{t['border']};--text:{t['text']};--muted:{t['muted']};"
      f"--accent:{t['accent']};--accent-soft:{t['accent_soft']};"
      f"--shadow:{t['shadow']};--font:{FONTE};"
      f"--pa-verde:{t['verde']};--pa-laranja:{t['laranja']};--pa-eyebrow:{t['eyebrow']};"
      "}"
      + (".pa-logo-escuro{display:none !important;}" if tema_claro else ".pa-logo-claro{display:none !important;}")
  )
  return (
      "<style>"
      "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Public+Sans:wght@700&family=Sora:wght@700&display=swap');"
      + variaveis
      + _REGRAS
      + "</style>"
  )


_REGRAS = """
/* ---------- base ---------- */
html, body, .stApp { background: var(--bg) !important; color: var(--text) !important; font-family: var(--font) !important; }
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stWidgetLabel"] p,
.stApp label, .stApp button, .stApp input, .stApp textarea,
.stApp [data-baseweb="select"] *:not(svg):not(path),
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: var(--font) !important; }
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stWidgetLabel"] p,
.stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: var(--text); }
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] * { color: var(--muted) !important; }

header[data-testid="stHeader"], [data-testid="stDecoration"], .viewerBadge_container__1QSob,
[data-testid="manage-app-button"], #MainMenu, footer { visibility: hidden; display: none !important; }
.block-container { max-width: 1680px !important; margin: 0 auto; padding: 1.1rem 2rem 4rem !important; }
hr { border: 0 !important; border-top: 1px solid var(--border) !important; margin: 1.6rem 0 1.2rem !important; opacity: 1 !important; }

/* ---------- cabecalho padrao dos portais PA (logo + faixa verde/laranja) ---------- */
div.st-key-header_card { background: var(--surface); padding: 14px 28px; border-radius: 14px; margin-bottom: 1rem; position: relative;
  overflow: hidden; border: 1px solid var(--border); box-shadow: var(--shadow); }
div.st-key-header_card::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
  background: linear-gradient(180deg, var(--pa-verde), var(--pa-laranja)); }
div.st-key-header_card img { width: 130px; display: block; }
.brand-text-block { display: flex; flex-direction: column; align-items: center; line-height: 1.35; }
.brand-eyebrow { font-family: 'Public Sans', sans-serif !important; font-weight: 700; font-size: 15px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--pa-eyebrow) !important; margin: 0; display: block; white-space: nowrap; }
.brand-subtitle { font-family: 'Sora', sans-serif !important; font-weight: 700; font-size: 22px; color: var(--muted) !important; display: block; white-space: nowrap; }
/* parametros de mercado (Selic / IPCA / dolar + Focus) ao lado do botao de atualizar */
.ind-mercado { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; margin-bottom: 4px;
  font-size: .72rem; line-height: 1.3; color: var(--muted) !important; }
.ind-linha { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: baseline; column-gap: .35rem; }
.ind-tit { font-size: .64rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; opacity: .8; margin-right: .15rem; }
.ind-item { white-space: nowrap; cursor: help; }
.ind-item b { color: var(--text) !important; font-weight: 600; font-variant-numeric: tabular-nums; }
.ind-sep { opacity: .5; }
@media (max-width: 640px) {
  .ind-mercado, .ind-linha { align-items: center; justify-content: center; }
  div.st-key-header_card { padding: 12px 18px; }
  .brand-eyebrow { font-size: 10.5px; letter-spacing: .06em; white-space: normal; text-align: center; }
  .brand-subtitle { font-size: 17px; white-space: normal; text-align: center; }
  div.st-key-header_card img { margin: 0 auto; width: 96px; }
}

/* ---------- titulo da pagina ---------- */
.app-header { display: flex; justify-content: space-between; align-items: center; gap: 1.5rem; flex-wrap: wrap; padding: .2rem 0 .8rem; }
.app-eyebrow { font-size: .7rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--accent) !important; margin-bottom: .3rem; }
.stApp h1.app-title { font-size: 1.35rem !important; font-weight: 700 !important; letter-spacing: -.01em; line-height: 1.2 !important; color: var(--text) !important; margin: 0 !important; padding: 0 !important; }
.app-subtitle { font-size: .84rem; color: var(--muted) !important; margin-top: .3rem; }
.app-chips { display: flex; gap: .5rem; flex-wrap: wrap; }
.chip { display: inline-flex; align-items: center; gap: .4rem; font-size: .76rem; font-weight: 500; color: var(--muted) !important;
  background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: .3rem .75rem; }
.chip b { color: var(--text) !important; font-weight: 600; }
.chip-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; display: inline-block; }

/* ---------- titulos de secao ---------- */
.section-header, .resumo-bar { background: transparent !important; color: var(--text) !important; text-align: left !important;
  font-size: .72rem !important; font-weight: 600 !important; letter-spacing: .08em !important; text-transform: uppercase !important;
  line-height: 1.25 !important; padding: .1rem 0 .1rem .75rem !important; margin: .3rem 0 .8rem !important;
  border: 0 !important; border-left: 3px solid var(--accent) !important; border-radius: 0 !important; }

/* ---------- cartoes ---------- */
div[data-testid="stPlotlyChart"] { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 0; box-shadow: var(--shadow); overflow: hidden; }
div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); }
div[data-testid="stExpander"] details { background: var(--surface); border: 1px solid var(--border) !important; border-radius: 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: .9rem 1rem; box-shadow: var(--shadow); }
.kpi-label { font-size: .7rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted) !important; }
.kpi-value { font-size: 2rem; font-weight: 700; letter-spacing: -.02em; line-height: 1.1; }
.kpi-sub { font-size: .78rem; color: var(--muted) !important; }
.gauge-footer { text-align: center; font-size: .95rem; font-weight: 600; margin-top: -4px; }

/* ---------- controles ---------- */
.stApp [data-baseweb="select"] > div, .stApp [data-baseweb="input"], .stApp [data-baseweb="base-input"],
.stApp [data-testid="stTextInputRootElement"] { background: var(--surface) !important; border: 1px solid var(--border) !important;
  border-radius: 10px !important; box-shadow: none !important; }
.stApp [data-baseweb="select"] *, .stApp input { color: var(--text) !important; }
.stApp input::placeholder { color: var(--muted) !important; opacity: .8; }
.stApp .react-aria-ComboBox [role="group"], .stApp [data-testid="stMultiSelect"] [role="group"],
.stApp [data-testid="stSelectbox"] [role="group"] { background: var(--surface) !important; border: 1px solid var(--border) !important;
  border-radius: 10px !important; box-shadow: none !important; }
.stApp [data-testid="stMultiSelect"] input, .stApp [data-testid="stSelectbox"] input { color: var(--text) !important; }
.stApp [data-testid="stMultiSelectTagsContainer"] *, .stApp [data-testid="stSelectbox"] [role="group"] * { color: var(--text); }
.stApp [data-testid="stMultiSelect"] svg, .stApp [data-testid="stSelectbox"] svg { fill: var(--muted); color: var(--muted); }
.stApp span[data-baseweb="tag"] { background: var(--accent-soft) !important; border-radius: 6px !important; }
.stApp span[data-baseweb="tag"] * { color: var(--accent) !important; }
div[data-baseweb="popover"] > div, div[data-baseweb="popover"] ul, div[data-baseweb="menu"] { background: var(--surface) !important; border: 1px solid var(--border); border-radius: 10px; }
div[data-baseweb="popover"] li, div[data-baseweb="popover"] li * { color: var(--text) !important; background: transparent !important; }
div[data-baseweb="popover"] li:hover { background: var(--accent-soft) !important; }
.stApp .stButton button { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: 10px !important;
  color: var(--text) !important; box-shadow: none !important; transition: border-color .15s, background .15s; }
.stApp .stButton button:hover { border-color: var(--accent) !important; background: var(--accent-soft) !important; }
.stApp .stButton button * { color: var(--text) !important; }
button[data-variant="pills"] { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: 999px !important;
  color: var(--muted) !important; font-size: .8rem !important; transition: all .15s; }
button[data-variant="pills"] * { color: inherit !important; }
button[data-variant="pills"]:hover { border-color: var(--accent) !important; }
button[data-variant="pills"][data-selected="true"] { background: var(--accent-soft) !important; border-color: var(--accent) !important; color: var(--accent) !important; font-weight: 600; }

/* ---------- popup ---------- */
div[data-testid="stDialog"] > div { background: var(--bg) !important; border: 1px solid var(--border); border-radius: 16px !important; }

/* ---------- assinatura ---------- */
.app-signature { position: fixed; left: 14px; bottom: 8px; z-index: 999; font-size: .7rem; font-weight: 500;
  letter-spacing: .04em; color: var(--muted) !important; opacity: .75; pointer-events: none; }

/* ---------- tabelas ---------- */
.stDataFrame td, .stDataFrame th { font-size: .82rem !important; }
div[data-testid="stDataFrame"] { max-width: 60% !important; margin-left: auto !important; margin-right: auto !important; }
.st-key-itens_criticos_wrap div[data-testid="stDataFrame"] { max-width: 100% !important; margin: 0 !important; }
"""


# Folga interna dos graficos dentro do cartao. Padding CSS no cartao nao serve:
# o Plotly mede o container com clientWidth (que inclui o padding) e o grafico
# vaza pra fora do cartao, cortando a borda direita. A folga entra, entao, como
# margem do proprio grafico (altura/largura do elemento nao mudam).
FOLGA_H = 16
FOLGA_V = 8


def instalar_folga_plotly():
  import streamlit as st

  if getattr(st.plotly_chart, "_pa_folga", False):
    return
  original = st.plotly_chart

  def plotly_chart(figure_or_data, *args, **kwargs):
    layout = getattr(figure_or_data, "layout", None)
    if layout is not None:
      margem = layout.margin
      figure_or_data.update_layout(
          margin=dict(
              l=(margem.l if margem.l is not None else 80) + FOLGA_H,
              r=(margem.r if margem.r is not None else 80) + FOLGA_H,
              t=(margem.t if margem.t is not None else 100) + FOLGA_V,
              b=(margem.b if margem.b is not None else 80) + FOLGA_V,
          )
      )
    return original(figure_or_data, *args, **kwargs)

  plotly_chart._pa_folga = True
  st.plotly_chart = plotly_chart
