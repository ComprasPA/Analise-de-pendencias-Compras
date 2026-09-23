import pandas as pd
import pytest

from logica_panorama import classificar_aging, processar_panorama


# --- classificar_aging --------------------------------------------------------
# limites: EMERGENCIAL=3 dias, ROTINEIRA=15 dias, padrão (outra/"")=15 dias.
# Regra: dias > limite => "Fora do Prazo"; dias >= limite*0.7 => "Atenção";
# senão => "No Prazo".

@pytest.mark.parametrize(
    "criticidade, dias, esperado",
    [
        ("ROTINEIRA", 16, "Fora do Prazo"),   # 16 > 15
        ("ROTINEIRA", 15, "Atenção"),          # 15 >= 15*0.7=10.5, não > 15
        ("ROTINEIRA", 11, "Atenção"),          # 11 >= 10.5
        ("ROTINEIRA", 10, "No Prazo"),         # 10 < 10.5
        ("EMERGENCIAL", 4, "Fora do Prazo"),   # 4 > 3
        ("EMERGENCIAL", 3, "Atenção"),         # 3 >= 3*0.7=2.1, não > 3
        ("EMERGENCIAL", 2, "No Prazo"),        # 2 < 2.1
        ("", 16, "Fora do Prazo"),              # sem criticidade -> limite padrão 15
        ("", 10, "No Prazo"),
        ("emergencial", 4, "Fora do Prazo"),   # case-insensitive
    ],
)
def test_classificar_aging_limites_por_criticidade(criticidade, dias, esperado):
  row = {"CRITICIDADE": criticidade, "Days": dias}
  assert classificar_aging(row) == esperado


def test_classificar_aging_aceita_nome_de_coluna_alternativo():
  row = {"OUTRA_COL": "ROTINEIRA", "Days": 20}
  assert classificar_aging(row, col_criticidade="OUTRA_COL") == "Fora do Prazo"


# --- processar_panorama --------------------------------------------------------
# Data base fixa usada em todos os cenários - hoje = 13/09/2026.
HOJE = pd.Timestamp("2026-09-13")


def _df_solicitacoes():
  # DATA EMISSAO como string "DD/MM/AAAA" - é o formato que realmente
  # circula pelo Google Sheets/export neste projeto (ver observação sobre
  # pd.to_datetime(..., dayfirst=True) mais abaixo, no teste dedicado).
  return pd.DataFrame(
      {
          "SOLICITAÇÃO": ["100001", "100002", "100003", "100004", "100005", "100005"],
          "CENTRO DE CUSTO": ["1225", "9999", "1238", "1232", "1225", "1225"],
          "DATA EMISSAO": [
              "01/08/2026",  # A: 43 dias atrás
              "10/09/2026",  # B: 3 dias atrás
              "01/09/2026",  # C: 12 dias atrás
              "01/09/2026",  # D: 12 dias atrás
              "20/08/2026",  # E: 24 dias atrás
              "20/08/2026",  # F: 24 dias atrás (mesma SC de E, item diferente)
          ],
          "PEDIDO": ["", "", "4500123", "", "", ""],
          "STATUS": ["", "", "", "REJEITADO", "", ""],
          "PRODUTO": ["P1", "P2", "P3", "P4", "P5", "P5b"],
      }
  )


def _df_criticidade():
  return pd.DataFrame(
      {
          "Solicitacao": ["100001", "100002", "100003", "100005"],
          "Criticidade": ["EMERGENCIAL", "ROTINEIRA", "ROTINEIRA", "ROTINEIRA"],
          # SC 100004 fica de fora de propósito -> Criticidade "" (não
          # entra nos gauges/SLA de Rotineira/Emergencial).
      }
  )


def _df_pedidos():
  # SC 100002 / PRODUTO P2 tem "baixa" na aba Pedidos mesmo com a célula
  # PEDIDO da própria Solicitação ainda vazia - Pedido Gerado é Atendida
  # sempre, é o mesmo comportamento que atualizar_pendencias_abertas.py
  # também respeita.
  return pd.DataFrame({"SOLICITAÇÃO": ["100002"], "PRODUTO": ["P2"]})


@pytest.fixture
def resultado():
  return processar_panorama(_df_solicitacoes(), _df_criticidade(), _df_pedidos(), HOJE)


def test_comprador_responsavel_mapeado_por_centro_de_custo(resultado):
  df = resultado["df"]
  mapa = dict(zip(df["SOLICITAÇÃO"], df["Comprador_Resp"]))
  assert mapa["100001"] == "Sílvio"   # CC 1225 mapeado
  assert mapa["100003"] == "Ednilson"  # CC 1238 mapeado
  assert mapa["100002"] == "Dayana"    # CC 9999 não mapeado -> cai pra Dayana


def test_tem_pedido_via_propria_celula_e_via_aba_pedidos(resultado):
  df = resultado["df"]
  tem_pedido = dict(zip(df["SOLICITAÇÃO"] + df["PRODUTO"], df["Tem_Pedido"]))
  assert bool(tem_pedido["100003P3"]) is True  # pedido na própria linha
  assert bool(tem_pedido["100002P2"]) is True  # pedido só na aba Pedidos
  assert bool(tem_pedido["100001P1"]) is False  # sem pedido em lugar nenhum


def test_status_fechado_manual_e_atendidas_por_pedido(resultado):
  df = resultado["df"]
  status = dict(zip(df["SOLICITAÇÃO"] + df["PRODUTO"], df["Status_Detalhado"]))
  assert status["100004P4"] == "Atendidas"  # REJEITADO -> fora do backlog
  assert status["100003P3"] == "Atendidas"  # pedido próprio
  assert status["100002P2"] == "Atendidas"  # pedido via aba Pedidos


def test_aging_classifica_itens_em_aberto_por_criticidade(resultado):
  df = resultado["df"]
  status = dict(zip(df["SOLICITAÇÃO"] + df["PRODUTO"], df["Status_Detalhado"]))
  # A: Emergencial, 43 dias > 3 -> Fora do Prazo
  assert status["100001P1"] == "Fora do Prazo"
  # E/F: Rotineira, 24 dias > 15 -> Fora do Prazo
  assert status["100005P5"] == "Fora do Prazo"
  assert status["100005P5b"] == "Fora do Prazo"


def test_totais_do_backlog_em_aberto(resultado):
  # Em aberto: A, E, F (100001, 100005 x2) = 3 linhas, 2 SCs únicas.
  assert resultado["total_linhas_aberto"] == 3
  assert resultado["total_sc_unicas_aberto"] == 2
  # Nenhum item em aberto tem pedido (por definição - ver processar_panorama).
  assert resultado["sem_pedido_total"] == 3


def test_sla_medio_geral_rotineira_e_emergencial(resultado):
  # Emergencial em aberto: só A, 43 dias -> média 43.
  assert resultado["sla_geral_emg"] == 43
  # Rotineira em aberto: E e F, 24 dias cada -> média 24.
  assert resultado["sla_geral_rot"] == 24


def test_snapshot_por_comprador(resultado):
  snap = resultado["snapshot_atual"]
  assert snap["total_scs_aberto"] == 2
  assert snap["total_linhas_aberto"] == 3
  assert snap["sem_pedido_total"] == 3

  assert snap["compradores"]["Sílvio"] == {"total": 3, "sem_pedido": 3, "comprados": 0}
  assert snap["compradores"]["Ednilson"] == {"total": 2, "sem_pedido": 0, "comprados": 1}
  assert snap["compradores"]["Dayana"] == {"total": 1, "sem_pedido": 0, "comprados": 1}


def test_processar_panorama_nao_muta_o_dataframe_original():
  df_original = _df_solicitacoes()
  colunas_antes = list(df_original.columns)
  processar_panorama(df_original, _df_criticidade(), _df_pedidos(), HOJE)
  assert list(df_original.columns) == colunas_antes


# --- casos de borda: vazio / None / NaN ---------------------------------------

def test_processar_panorama_sem_criticidade_cadastrada():
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["200001"],
          "CENTRO DE CUSTO": ["1225"],
          "DATA EMISSAO": ["01/09/2026"],
          "PEDIDO": [""],
          "STATUS": [""],
          "PRODUTO": ["X1"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos_vazio = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos_vazio, HOJE)

  assert resultado["df"]["CRITICIDADE"].iloc[0] == ""
  # Sem Rotineira/Emergencial no backlog -> SLA geral fica 0 (nan tratado).
  assert resultado["sla_geral_rot"] == 0
  assert resultado["sla_geral_emg"] == 0


def test_processar_panorama_cotacao_vem_direto_da_propria_aba_solicitacoes():
  # COTAÇÃO já é uma coluna pronta na aba Solicitacoes (não vem de join
  # com nenhuma outra aba) - nem toda Solicitação teve cotação aberta,
  # então fica "" quando a célula está vazia.
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["200001", "200002"],
          "CENTRO DE CUSTO": ["1225", "1225"],
          "DATA EMISSAO": ["01/09/2026", "01/09/2026"],
          "COTAÇÃO": ["019895", ""],
          "PEDIDO": ["", ""],
          "STATUS": ["", ""],
          "PRODUTO": ["X1", "X2"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos_vazio = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos_vazio, HOJE)

  assert resultado["df"]["COTAÇÃO"].iloc[0] == "019895"
  assert resultado["df"]["COTAÇÃO"].iloc[1] == ""


def test_processar_panorama_cotacao_completa_com_zero_a_esquerda_ate_6_digitos():
  # Cotação sempre tem 6 dígitos - quando a célula virou número real (em
  # vez de texto) o zero à esquerda se perde e/ou sobra ".0" de float.
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["200004", "200005", "200006"],
          "CENTRO DE CUSTO": ["1225", "1225", "1225"],
          "DATA EMISSAO": ["01/09/2026", "01/09/2026", "01/09/2026"],
          "COTAÇÃO": ["21227.0", "787", "019895"],
          "PEDIDO": ["", "", ""],
          "STATUS": ["", "", ""],
          "PRODUTO": ["X4", "X5", "X6"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos_vazio = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos_vazio, HOJE)

  assert list(resultado["df"]["COTAÇÃO"]) == ["021227", "000787", "019895"]


def test_processar_panorama_sem_coluna_cotacao_na_planilha():
  # Planilha antiga/sem essa coluna ainda - não deve quebrar, só fica "".
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["200003"],
          "CENTRO DE CUSTO": ["1225"],
          "DATA EMISSAO": ["01/09/2026"],
          "PEDIDO": [""],
          "STATUS": [""],
          "PRODUTO": ["X3"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos_vazio = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos_vazio, HOJE)

  assert resultado["df"]["COTAÇÃO"].iloc[0] == ""


def test_processar_panorama_pedido_nan_e_none_conta_como_sem_pedido():
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["300001", "300002"],
          "CENTRO DE CUSTO": ["1225", "1225"],
          "DATA EMISSAO": ["01/09/2026", "01/09/2026"],
          "PEDIDO": [float("nan"), None],
          "STATUS": ["", ""],
          "PRODUTO": ["Y1", "Y2"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos_vazio = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos_vazio, HOJE)

  assert (~resultado["df"]["Tem_Pedido"]).all()


def test_processar_panorama_data_emissao_invalida_vira_zero_dias():
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["400001"],
          "CENTRO DE CUSTO": ["1225"],
          "DATA EMISSAO": ["não é uma data"],
          "PEDIDO": [""],
          "STATUS": [""],
          "PRODUTO": ["Z1"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos_vazio = pd.DataFrame(columns=["SOLICITAÇÃO", "PRODUTO"])

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos_vazio, HOJE)

  assert resultado["df"]["Days"].iloc[0] == 0


def test_processar_panorama_sc_sem_produto_correspondente_na_aba_pedidos():
  """Uma SC com PRODUTO que não existe na aba Pedidos não deve ser marcada
  como Tem_Pedido só porque a SC aparece lá com outro produto."""
  df = pd.DataFrame(
      {
          "SOLICITAÇÃO": ["500001"],
          "CENTRO DE CUSTO": ["1225"],
          "DATA EMISSAO": ["01/09/2026"],
          "PEDIDO": [""],
          "STATUS": [""],
          "PRODUTO": ["OUTRO_PRODUTO"],
      }
  )
  df_criticidade_vazio = pd.DataFrame(columns=["Solicitacao", "Criticidade"])
  df_pedidos = pd.DataFrame({"SOLICITAÇÃO": ["500001"], "PRODUTO": ["PRODUTO_DIFERENTE"]})

  resultado = processar_panorama(df, df_criticidade_vazio, df_pedidos, HOJE)

  assert resultado["df"]["Tem_Pedido"].iloc[0] == False


# --- documentação do comportamento conhecido de dayfirst ----------------------

def test_dayfirst_com_string_dd_mm_aaaa_funciona_corretamente():
  """Formato real que circula pelo Google Sheets neste projeto: string
  "DD/MM/AAAA". Com dayfirst=True o pandas interpreta corretamente."""
  resultado = pd.to_datetime("01/08/2026", dayfirst=True)
  assert resultado == pd.Timestamp("2026-08-01")


def test_dayfirst_com_string_iso_e_ambiguo_comportamento_conhecido_nao_e_bug_aqui():
  """Comportamento conhecido (documentado, não é um bug deste repo pra
  corrigir agora): se a DATA EMISSAO chegasse como string ISO (AAAA-MM-DD)
  em vez do formato real "DD/MM/AAAA", dayfirst=True ainda tenta ler
  dia-antes-de-mês e pode inverter dia/mês quando ambos são <=12. Ver
  observação equivalente no repo irmão (consulta-parente-andrade). Isso
  não afeta a produção aqui porque o dado real chega como "DD/MM/AAAA".
  """
  # "2026-08-01" é 1º de agosto em ISO, mas com dayfirst=True o pandas
  # tenta ler "26-08-01" como ano-mes-dia primeiro na prática moderna do
  # pandas isso é resolvido corretamente pro formato ISO completo (com
  # separador "-" de 4 dígitos de ano), então demonstramos aqui com um
  # Timestamp cru reformatado como str, que é o caso realmente ambíguo.
  valor_como_timestamp = pd.Timestamp("2026-08-01")
  reparseado = pd.to_datetime(str(valor_como_timestamp), dayfirst=True)
  # Comportamento real observado: vira 2026-01-08 (dia e mês trocados) em
  # vez de permanecer 2026-08-01, porque str(Timestamp) produz
  # "2026-08-01 00:00:00" e o parser, com dayfirst=True, prioriza dia
  # antes de mês quando a string tem esse formato ambíguo.
  assert reparseado != valor_como_timestamp
