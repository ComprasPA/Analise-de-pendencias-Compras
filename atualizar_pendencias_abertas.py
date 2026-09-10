"""Reconcilia a aba "Solicitacoes" com o browse "Pendências SC" do TOTVS,
marcando como "REVISAR" toda Solicitação que:
  - não tem Pedido preenchido, e
  - não está mais listada no export de Pendências (ou seja, o TOTVS não
    considera mais ela em aberto, mas por algum motivo isso nunca virou um
    Pedido nem foi classificado como Rejeitado/Contrato pelo comprador).

Isso pede pro comprador checar manualmente essas solicitações no Portal do
Comprador (rejeitou? virou contrato? outra coisa?) - é ele quem decide,
este script só sinaliza.

NUNCA mexe em: linhas com Pedido preenchido, nem em REJEITADO/CONTRATO já
lançados manualmente (esses são decisão do comprador, não deste script).
Se uma Solicitação marcada REVISAR volta a aparecer num export novo de
Pendências, o script desfaz a marcação (volta pra status em branco).

Uso:
    python atualizar_pendencias_abertas.py --arquivo "Pendencias SC.xlsx" --secrets caminho\\secrets.toml
"""
import argparse
import tomllib

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

FILE_ID = "1e7pQ512ge5XMnXxsRODEO7V48KgWo6FpKeITFqBSg1o"
ABA_SOLICITACOES = "Solicitacoes"
STATUS_REVISAR = "REVISAR"
STATUS_MANUAIS_PROTEGIDOS = {"REJEITADO", "CONTRATO"}


def obter_client(secrets_path):
  with open(secrets_path, "rb") as f:
    dados = tomllib.load(f)
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(dados["gcp_service_account"], scopes=scope)
  return gspread.authorize(creds)


def resolver_coluna(colunas, contem):
  achada = next((c for c in colunas if contem.lower() in c.lower()), None)
  if achada is None:
    raise RuntimeError(f"Coluna contendo '{contem}' nao encontrada. Colunas do arquivo: {list(colunas)}")
  return achada


def carregar_pendencias_totvs(caminho):
  """Retorna o conjunto de (Solicitacao, Item) que o TOTVS considera em
  aberto agora, segundo o export "Pendências SC"."""
  df = pd.read_excel(caminho, sheet_name="Listagem do Browse", header=1)
  df.columns = df.columns.astype(str).str.strip()

  col_solic = resolver_coluna(df.columns, "Numero da SC")
  col_item = resolver_coluna(df.columns, "Item da SC")

  df = df.dropna(subset=[col_solic, col_item])
  return set(
      zip(
          df[col_solic].apply(lambda v: str(int(v))),
          df[col_item].apply(lambda v: str(int(v))),
      )
  )


def reconciliar(worksheet, pendentes_totvs):
  valores = worksheet.get_all_values()
  if not valores:
    return 0, 0

  cabecalho = valores[0]
  idx_solic = cabecalho.index("SOLICITAÇÃO")
  idx_item = cabecalho.index("ITEM SC")
  idx_pedido = cabecalho.index("PEDIDO")
  idx_status = cabecalho.index("STATUS")
  n_cols = len(cabecalho)

  celulas = []
  qtd_marcadas = 0
  qtd_desmarcadas = 0

  for i, linha in enumerate(valores[1:], start=2):
    linha_pad = linha + [""] * (n_cols - len(linha))

    solic = str(linha_pad[idx_solic]).strip()
    item = str(linha_pad[idx_item]).strip()
    if not solic or not item:
      continue
    solic = solic.split(".")[0]
    item = item.split(".")[0]

    pedido = linha_pad[idx_pedido].strip()
    if pedido and pedido.lower() != "nan":
      continue  # tem Pedido - nao mexe

    status_atual = linha_pad[idx_status].strip().upper()
    if status_atual in STATUS_MANUAIS_PROTEGIDOS:
      continue  # decisao do comprador - nao mexe

    esta_pendente_totvs = (solic, item) in pendentes_totvs

    if status_atual == STATUS_REVISAR:
      if esta_pendente_totvs:
        celulas.append(gspread.Cell(i, idx_status + 1, ""))
        qtd_desmarcadas += 1
    else:
      if not esta_pendente_totvs:
        celulas.append(gspread.Cell(i, idx_status + 1, STATUS_REVISAR))
        qtd_marcadas += 1

  if celulas:
    worksheet.update_cells(celulas, value_input_option="RAW")

  return qtd_marcadas, qtd_desmarcadas


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--arquivo", required=True)
  parser.add_argument("--secrets", required=True)
  args = parser.parse_args()

  client = obter_client(args.secrets)
  spreadsheet = client.open_by_key(FILE_ID)
  worksheet = spreadsheet.worksheet(ABA_SOLICITACOES)

  pendentes_totvs = carregar_pendencias_totvs(args.arquivo)
  qtd_marcadas, qtd_desmarcadas = reconciliar(worksheet, pendentes_totvs)
  print(
      f"{qtd_marcadas} solicitacao(oes) marcada(s) como REVISAR, "
      f"{qtd_desmarcadas} desmarcada(s) (voltaram a aparecer no TOTVS)."
  )


if __name__ == "__main__":
  main()
