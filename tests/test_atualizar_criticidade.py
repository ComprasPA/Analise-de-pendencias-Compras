import gspread
import pandas as pd
import pytest

from atualizar_criticidade import CABECALHO, carregar_arquivo, resolver_coluna, upsert
from tests.fakes import FakeWorksheet


# --- resolver_coluna -------------------------------------------------------

def test_resolver_coluna_encontra_por_substring_case_insensitive():
  colunas = ["Número Protheus", "Criticidade Solicitação", "Status Atual"]
  assert resolver_coluna(colunas, "protheus") == "Número Protheus"
  assert resolver_coluna(colunas, "CRITICIDADE") == "Criticidade Solicitação"


def test_resolver_coluna_obrigatoria_ausente_leva_erro():
  colunas = ["Foo", "Bar"]
  with pytest.raises(RuntimeError):
    resolver_coluna(colunas, "Protheus", obrigatoria=True)


def test_resolver_coluna_opcional_ausente_retorna_none():
  colunas = ["Foo", "Bar"]
  assert resolver_coluna(colunas, "Centro de Custo", obrigatoria=False) is None


# --- carregar_arquivo -------------------------------------------------------

def test_carregar_arquivo_normaliza_colunas_e_upsert_por_solicitacao(tmp_path):
  # Duas linhas com o mesmo número de Solicitação (a exportação do TOTVS
  # às vezes repete linha) - a última deve prevalecer (drop_duplicates keep="last").
  bruto = pd.DataFrame(
      {
          "Número Protheus": [1001, 1001, 1002, None],
          "Criticidade": ["ROTINEIRA", "EMERGENCIAL", "EMERGENCIAL", "ROTINEIRA"],
          "Centro de Custo": ["1225", "1225", "9999", "0000"],
          "Descrição": ["Parafusos", "Parafusos", "Tubo PVC", "Ignorar"],
          "Status": ["", "", "ABERTA", ""],
          "Comprador": ["Sílvio", "Sílvio", "Dayana", ""],
          "Número da Cotação": ["", "5001", "5002", ""],
      }
  )
  caminho = tmp_path / "cotacoes.xlsx"
  bruto.to_excel(caminho, index=False)

  saida = carregar_arquivo(str(caminho))

  # A linha com Protheus vazio (NaN) foi descartada.
  assert set(saida["Solicitacao"]) == {"1001", "1002"}
  # Duplicata: fica só a última ocorrência de 1001 (Criticidade EMERGENCIAL).
  linha_1001 = saida[saida["Solicitacao"] == "1001"].iloc[0]
  assert linha_1001["Criticidade"] == "EMERGENCIAL"
  assert linha_1001["Centro de Custo"] == "1225"
  assert linha_1001["Cotacao"] == "5001"

  linha_1002 = saida[saida["Solicitacao"] == "1002"].iloc[0]
  assert linha_1002["Criticidade"] == "EMERGENCIAL"
  assert linha_1002["Comprador"] == "Dayana"
  assert linha_1002["Cotacao"] == "5002"

  assert list(saida.columns) == [
      "Solicitacao", "Criticidade", "Centro de Custo", "Descricao", "Status", "Comprador", "Cotacao",
  ]


def test_carregar_arquivo_sem_colunas_opcionais_preenche_vazio(tmp_path):
  # Export mínimo, sem Centro de Custo / Descrição / Status / Comprador.
  bruto = pd.DataFrame({"Número Protheus": [2001], "Criticidade": ["ROTINEIRA"]})
  caminho = tmp_path / "cotacoes_minimo.xlsx"
  bruto.to_excel(caminho, index=False)

  saida = carregar_arquivo(str(caminho))

  assert saida.iloc[0]["Solicitacao"] == "2001"
  assert saida.iloc[0]["Centro de Custo"] == ""
  assert saida.iloc[0]["Descricao"] == ""
  assert saida.iloc[0]["Cotacao"] == ""


def test_carregar_arquivo_sem_coluna_criticidade_obrigatoria_falha(tmp_path):
  bruto = pd.DataFrame({"Número Protheus": [2001]})
  caminho = tmp_path / "sem_criticidade.xlsx"
  bruto.to_excel(caminho, index=False)

  with pytest.raises(RuntimeError):
    carregar_arquivo(str(caminho))


# --- upsert -----------------------------------------------------------------

def _novos_df(linhas):
  return pd.DataFrame(linhas, columns=CABECALHO)


def test_upsert_atualiza_linha_existente_e_adiciona_nova():
  valores_existentes = [
      CABECALHO,
      ["1001", "ROTINEIRA", "1225", "Parafusos", "", "Sílvio", ""],
  ]
  worksheet = FakeWorksheet(valores_existentes)

  novos = _novos_df([
      ["1001", "EMERGENCIAL", "1225", "Parafusos", "", "Sílvio", "5001"],  # atualiza
      ["1003", "ROTINEIRA", "9999", "Tubo", "", "Dayana", ""],  # nova
  ])

  atualizadas, novas = upsert(worksheet, novos)

  assert atualizadas == 1
  assert novas == 1
  # A atualização foi escrita via update_cells, na linha 2 (linha 1 é cabeçalho).
  celulas = worksheet.update_cells_calls[0]
  assert all(c.row == 2 for c in celulas)
  valores_por_coluna = {c.col: c.value for c in celulas}
  assert valores_por_coluna[1] == "1001"
  assert valores_por_coluna[2] == "EMERGENCIAL"
  assert valores_por_coluna[7] == "5001"
  # A linha nova foi enviada via append_rows.
  assert worksheet.append_rows_calls[0] == [["1003", "ROTINEIRA", "9999", "Tubo", "", "Dayana", ""]]


def test_upsert_planilha_vazia_escreve_cabecalho_primeiro():
  worksheet = FakeWorksheet([])
  novos = _novos_df([["2001", "ROTINEIRA", "", "", "", "", ""]])

  atualizadas, novas = upsert(worksheet, novos)

  assert atualizadas == 0
  assert novas == 1
  assert worksheet.update_calls[0] == ([CABECALHO], "A1")
  assert worksheet.append_rows_calls[0] == [["2001", "ROTINEIRA", "", "", "", "", ""]]


def test_upsert_nao_duplica_ao_rodar_duas_vezes_seguidas():
  """upsert deve ser idempotente: rodar duas vezes com o mesmo arquivo não
  deve gerar duas linhas novas pra mesma Solicitação (regra central do
  script - "pode rodar quantas vezes for preciso sem duplicar linha")."""
  worksheet = FakeWorksheet([CABECALHO])
  novos = _novos_df([["3001", "ROTINEIRA", "1225", "Item", "", "Sílvio", ""]])

  upsert(worksheet, novos)
  # Simula o efeito da 1a chamada: a linha nova apareceria na planilha.
  worksheet._values = [CABECALHO] + worksheet.append_rows_calls[0]

  atualizadas, novas = upsert(worksheet, novos)

  assert novas == 0
  assert atualizadas == 1


def test_upsert_migra_planilha_antiga_sem_coluna_cotacao():
  """Planilhas criadas antes da coluna "Cotacao" existir não têm essa
  coluna no cabeçalho - upsert deve estendê-lo (no fim) em vez de falhar
  ou descartar o dado novo."""
  cabecalho_antigo = ["Solicitacao", "Criticidade", "Centro de Custo", "Descricao", "Status", "Comprador"]
  valores_existentes = [
      cabecalho_antigo,
      ["1001", "ROTINEIRA", "1225", "Parafusos", "", "Sílvio"],
  ]
  worksheet = FakeWorksheet(valores_existentes)

  novos = _novos_df([["1001", "ROTINEIRA", "1225", "Parafusos", "", "Sílvio", "5001"]])

  atualizadas, novas = upsert(worksheet, novos)

  assert atualizadas == 1
  assert novas == 0
  # Cabeçalho estendido com "Cotacao" no fim, sem mexer nas colunas existentes.
  assert worksheet.update_calls[0] == ([cabecalho_antigo + ["Cotacao"]], "A1")
  celulas = worksheet.update_cells_calls[0]
  valores_por_coluna = {c.col: c.value for c in celulas}
  assert valores_por_coluna[7] == "5001"
