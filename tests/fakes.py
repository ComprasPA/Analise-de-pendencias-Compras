"""Duplos de teste (fakes) que imitam a API do gspread usada pelos scripts
deste repo (upsert/reconciliar/carregar_chaves_pedidos), sem tocar em rede
nem em planilha real. Compartilhado pelos testes dos dois scripts
auxiliares."""


class FakeWorksheet:
  """Imita gspread.Worksheet o suficiente pra rodar upsert()/reconciliar()."""

  def __init__(self, values):
    # `values` é uma lista de listas, igual ao retorno de get_all_values()
    # (primeira linha = cabeçalho).
    self._values = values
    self.update_cells_calls = []
    self.append_rows_calls = []
    self.update_calls = []

  def get_all_values(self):
    return self._values

  def update(self, values, range_name=None):
    self.update_calls.append((values, range_name))

  def update_cells(self, cells, value_input_option="RAW"):
    self.update_cells_calls.append(list(cells))

  def append_rows(self, rows, value_input_option="RAW"):
    self.append_rows_calls.append(list(rows))


class FakeSpreadsheet:
  """Imita gspread.Spreadsheet só no que os scripts usam: spreadsheet.worksheet(nome)."""

  def __init__(self, worksheets_by_name):
    self._worksheets = dict(worksheets_by_name)

  def worksheet(self, nome):
    return self._worksheets[nome]
