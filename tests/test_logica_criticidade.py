import pandas as pd

from logica_criticidade import (
    CATS,
    SEM_CRITICIDADE,
    agregado_por_cc,
    aplicar_filtros,
    contagem_por_criticidade,
    evolucao_mensal,
    preparar_solicitacoes,
    rotulo_mes,
)


def _proc():
  """DataFrame no formato que sai de processar_panorama (nivel de item)."""
  return pd.DataFrame(
      {
          "SOLICITAÇÃO": ["100", "100", "200", "300", "400", "500", "600"],
          "COTAÇÃO": ["019895", "019896", "", "021028", "", "", "021500"],
          "CRITICIDADE": ["ROTINEIRA", "ROTINEIRA", "COMPRAS DIRETA", "EMERGENCIAL", "NÃO CLASSIFICADO", "", "CORREÇÃO DE PROCESSO"],
          "DESCRICAO": ["Parafusos", "Porcas", "NF 10", "Robô roçador", "Serviço x", "Item y", "Correção de CNPJ"],
          "CC_clean": ["1225", "1225", "1238", "1238", "1237", "1237", "2003"],
          "Comprador_Resp": ["Sílvio", "Sílvio", "Ednilson", "Ednilson", "Dayana", "Dayana", "Dayana"],
          "Status_Detalhado": ["Atendidas", "Fora do Prazo", "Atendidas", "No Prazo", "Atenção", "No Prazo", "Atendidas"],
          "DATA APROVACAO": ["10/01/2026", "12/01/2026", "03/02/2026", "15/02/2026", "", "20/03/2026", "01/04/2026"],
          "DATA EMISSAO": pd.to_datetime(
              ["2026-01-09", "2026-01-09", "2026-02-02", "2026-02-14", "2026-03-05", "2026-03-19", "2026-03-31"]
          ),
      }
  )


def test_preparar_agrupa_por_sc_e_junta_cotacoes_distintas():
  df = preparar_solicitacoes(_proc())
  assert list(df["sol"]) == ["100", "200", "300", "400", "500", "600"]
  sc100 = df[df["sol"] == "100"].iloc[0]
  assert sc100["itens"] == 2
  assert sc100["cot"] == "019895, 019896"
  # data = menor Data Aprovacao entre os itens da SC.
  assert sc100["dt"] == pd.Timestamp("2026-01-10")
  # o status da SC é o do item mais atrasado.
  assert sc100["status"] == "Fora do Prazo"


def test_data_cai_pra_emissao_quando_aprovacao_vazia():
  df = preparar_solicitacoes(_proc())
  assert df[df["sol"] == "400"].iloc[0]["dt"] == pd.Timestamp("2026-03-05")


def test_criticidade_desconhecida_ou_vazia_vira_sem_criticidade():
  df = preparar_solicitacoes(_proc())
  assert df[df["sol"] == "400"].iloc[0]["crit"] == SEM_CRITICIDADE
  assert df[df["sol"] == "500"].iloc[0]["crit"] == SEM_CRITICIDADE
  assert df[df["sol"] == "200"].iloc[0]["crit"] == "Compras direta"
  assert df[df["sol"] == "600"].iloc[0]["crit"] == "Correção de Processo"


def test_sc_com_numero_float_agrupa_igual():
  bruto = _proc()
  bruto.loc[1, "SOLICITAÇÃO"] = "100.0"
  assert len(preparar_solicitacoes(bruto)) == 6


def test_contagem_por_criticidade_inclui_categorias_zeradas():
  contagem = contagem_por_criticidade(preparar_solicitacoes(_proc()))
  assert contagem == {
      "Rotineira": 1, "Compras direta": 1, "Emergencial": 1,
      "Correção de Processo": 1, SEM_CRITICIDADE: 2,
  }


def test_filtros_vazios_nao_filtram_e_combinam_com_and():
  df = preparar_solicitacoes(_proc())
  assert len(aplicar_filtros(df)) == 6
  assert len(aplicar_filtros(df, meses=["02"])) == 2
  assert len(aplicar_filtros(df, meses=["02"], ccs=["1238"], crits=["Emergencial"])) == 1
  assert len(aplicar_filtros(df, comps=["Dayana"])) == 3


def test_busca_livre_procura_em_descricao_comprador_e_codigos():
  df = preparar_solicitacoes(_proc())
  assert list(aplicar_filtros(df, busca="ROBÔ")["sol"]) == ["300"]
  assert list(aplicar_filtros(df, busca="021028")["sol"]) == ["300"]
  assert list(aplicar_filtros(df, busca="019896")["sol"]) == ["100"]
  assert len(aplicar_filtros(df, busca="dayana")) == 3


def test_ignorar_cc_crit_mantem_demais_filtros():
  df = preparar_solicitacoes(_proc())
  recorte = aplicar_filtros(df, ccs=["9999"], crits=["Emergencial"], meses=["02"], ignorar_cc_crit=True)
  assert len(recorte) == 2


def test_evolucao_mensal_ordenada_e_com_todas_as_colunas():
  evolucao = evolucao_mensal(preparar_solicitacoes(_proc()))
  assert list(evolucao.index) == ["2026-01", "2026-02", "2026-03", "2026-04"]
  assert list(evolucao.columns) == CATS
  assert evolucao.loc["2026-02", "Emergencial"] == 1
  assert evolucao.loc["2026-03", SEM_CRITICIDADE] == 2


def test_agregado_por_cc_total_e_percentual():
  agg = agregado_por_cc(preparar_solicitacoes(_proc()))
  linha_1237 = agg[agg["cc"] == "1237"].iloc[0]
  assert linha_1237["Total"] == 2
  assert linha_1237[SEM_CRITICIDADE] == 2
  assert linha_1237[f"% {SEM_CRITICIDADE}"] == 100.0
  linha_1238 = agg[agg["cc"] == "1238"].iloc[0]
  assert linha_1238["% Emergencial"] == 50.0
  assert linha_1238["% Compras direta"] == 50.0


def test_agregado_e_evolucao_de_recorte_vazio_nao_quebram():
  vazio = preparar_solicitacoes(_proc()).iloc[0:0]
  assert agregado_por_cc(vazio).empty
  assert evolucao_mensal(vazio).empty


def test_rotulo_mes():
  assert rotulo_mes("2026-09") == "set/26"
