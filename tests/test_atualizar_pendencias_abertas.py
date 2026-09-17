import openpyxl
import pytest

from atualizar_pendencias_abertas import (
    STATUS_REVISAR,
    carregar_chaves_pedidos,
    carregar_pendencias_totvs,
    reconciliar,
    resolver_coluna,
)
from tests.fakes import FakeSpreadsheet, FakeWorksheet


# --- resolver_coluna ---------------------------------------------------------

def test_resolver_coluna_encontra_por_substring():
  assert resolver_coluna(["Numero da SC", "Item da SC"], "numero da sc") == "Numero da SC"


def test_resolver_coluna_ausente_sempre_levanta_erro():
  # Esta versão de resolver_coluna (script de pendências) não tem parâmetro
  # `obrigatoria` - toda coluna pedida é obrigatória.
  with pytest.raises(RuntimeError):
    resolver_coluna(["Foo", "Bar"], "Numero da SC")


# --- carregar_pendencias_totvs -----------------------------------------------

def _escrever_browse_totvs(caminho, linhas_dados, titulo_linha1="Listagem do Browse - Pendências SC"):
  """Monta um .xlsx no mesmo formato do export TOTVS: aba "Listagem do
  Browse", uma linha de título antes do cabeçalho real (por isso
  carregar_pendencias_totvs usa header=1)."""
  wb = openpyxl.Workbook()
  ws = wb.active
  ws.title = "Listagem do Browse"
  ws.append([titulo_linha1])
  ws.append(["Numero da SC", "Item da SC", "Outra Coluna"])
  for linha in linhas_dados:
    ws.append(linha)
  wb.save(caminho)


def test_carregar_pendencias_totvs_retorna_chaves_solicitacao_item(tmp_path):
  caminho = tmp_path / "pendencias.xlsx"
  _escrever_browse_totvs(
      caminho,
      [
          [100001, 1, "x"],
          [100001, 2, "x"],
          [100002, 1, "x"],
          [None, None, "linha em branco, deve ser ignorada"],
      ],
  )

  chaves = carregar_pendencias_totvs(str(caminho))

  assert chaves == {("100001", "1"), ("100001", "2"), ("100002", "1")}


# --- carregar_chaves_pedidos --------------------------------------------------

def test_carregar_chaves_pedidos_normaliza_numeros_com_ponto_decimal():
  valores_pedidos = [
      ["SOLICITAÇÃO", "PRODUTO", "OUTRA"],
      ["100002.0", "P2.0", "x"],
      ["100003", "P3", "x"],
      ["", "", "linha vazia ignorada"],
  ]
  spreadsheet = FakeSpreadsheet({"Pedidos": FakeWorksheet(valores_pedidos)})

  chaves = carregar_chaves_pedidos(spreadsheet)

  assert chaves == {("100002", "P2"), ("100003", "P3")}


def test_carregar_chaves_pedidos_planilha_vazia_retorna_conjunto_vazio():
  spreadsheet = FakeSpreadsheet({"Pedidos": FakeWorksheet([])})
  assert carregar_chaves_pedidos(spreadsheet) == set()


# --- reconciliar --------------------------------------------------------------

CABECALHO_SOLIC = ["SOLICITAÇÃO", "ITEM SC", "PEDIDO", "PRODUTO", "STATUS"]


def _worksheet_solicitacoes(linhas):
  return FakeWorksheet([CABECALHO_SOLIC] + linhas)


def test_reconciliar_marca_revisar_quando_some_do_totvs_sem_pedido():
  worksheet = _worksheet_solicitacoes([
      ["100001", "1", "", "P1", ""],  # não está mais pendente no TOTVS, sem pedido
  ])
  pendentes_totvs = set()  # nada mais pendente
  chaves_pedidos = set()

  marcadas, desmarcadas = reconciliar(worksheet, pendentes_totvs, chaves_pedidos)

  assert marcadas == 1
  assert desmarcadas == 0
  celulas = worksheet.update_cells_calls[0]
  assert len(celulas) == 1
  assert celulas[0].row == 2
  assert celulas[0].value == STATUS_REVISAR


def test_reconciliar_nao_marca_se_ainda_pendente_no_totvs():
  worksheet = _worksheet_solicitacoes([
      ["100001", "1", "", "P1", ""],
  ])
  pendentes_totvs = {("100001", "1")}

  marcadas, desmarcadas = reconciliar(worksheet, pendentes_totvs, set())

  assert marcadas == 0
  assert desmarcadas == 0
  assert worksheet.update_cells_calls == []


def test_reconciliar_desmarca_revisar_quando_ganha_pedido_na_propria_linha():
  worksheet = _worksheet_solicitacoes([
      ["100001", "1", "4500999", "P1", "REVISAR"],
  ])
  marcadas, desmarcadas = reconciliar(worksheet, set(), set())

  assert marcadas == 0
  assert desmarcadas == 1
  celulas = worksheet.update_cells_calls[0]
  assert celulas[0].value == ""


def test_reconciliar_desmarca_revisar_quando_pedido_via_aba_pedidos():
  """Pedido Gerado é Atendida sempre, mesmo que a célula PEDIDO da própria
  Solicitação ainda não tenha sido preenchida - por isso cruza com a aba
  Pedidos (por SOLICITAÇÃO+PRODUTO) antes de decidir REVISAR."""
  worksheet = _worksheet_solicitacoes([
      ["100001", "1", "", "P1", "REVISAR"],
  ])
  chaves_pedidos = {("100001", "P1")}

  marcadas, desmarcadas = reconciliar(worksheet, set(), chaves_pedidos)

  assert marcadas == 0
  assert desmarcadas == 1


def test_reconciliar_nunca_mexe_em_status_manuais_protegidos():
  worksheet = _worksheet_solicitacoes([
      ["100001", "1", "", "P1", "REJEITADO"],
      ["100002", "1", "", "P2", "CONTRATO"],
  ])
  # Nenhuma das duas está pendente no TOTVS nem tem pedido - mas o script
  # nunca deve tocar em REJEITADO/CONTRATO (decisão do comprador).
  marcadas, desmarcadas = reconciliar(worksheet, set(), set())

  assert marcadas == 0
  assert desmarcadas == 0
  assert worksheet.update_cells_calls == []


def test_reconciliar_ignora_linha_sem_solicitacao_ou_item():
  worksheet = _worksheet_solicitacoes([
      ["", "", "", "", ""],
      ["100001", "", "", "P1", ""],
  ])
  marcadas, desmarcadas = reconciliar(worksheet, set(), set())

  assert marcadas == 0
  assert desmarcadas == 0


def test_reconciliar_planilha_vazia_retorna_zero_zero():
  worksheet = FakeWorksheet([])
  assert reconciliar(worksheet, set(), set()) == (0, 0)
