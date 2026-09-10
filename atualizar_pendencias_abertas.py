"""Atualiza a aba "Pendencias_Abertas" na planilha do Panorama com a lista
de itens de Solicitação REALMENTE em aberto agora, segundo o browse
"Pendências SC" do TOTVS.

Diferente da aba "Solicitacoes" (que só cresce - o import de lá nunca marca
uma linha como fechada, só preenche campo em branco ou adiciona linha
nova), este arquivo É a verdade do que está aberto no TOTVS neste
instante: se uma Solicitação/Item não está nele, não está mais aberta,
ponto. Por isso este script SUBSTITUI o conteúdo da aba inteira a cada
execução (não faz upsert) - ele reflete um retrato do momento, não um
histórico acumulado.

Rode este script toda vez que chegar um novo export "Pendências SC".

Uso:
    python atualizar_pendencias_abertas.py --arquivo "Pendencias SC.xlsx" --secrets caminho\\secrets.toml
"""
import argparse
import tomllib

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

FILE_ID = "1e7pQ512ge5XMnXxsRODEO7V48KgWo6FpKeITFqBSg1o"
ABA_PENDENCIAS = "Pendencias_Abertas"
CABECALHO = ["Solicitacao", "Item"]


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


def carregar_arquivo(caminho):
  df = pd.read_excel(caminho, sheet_name="Listagem do Browse", header=1)
  df.columns = df.columns.astype(str).str.strip()

  col_solic = resolver_coluna(df.columns, "Numero da SC")
  col_item = resolver_coluna(df.columns, "Item da SC")

  df = df.dropna(subset=[col_solic, col_item]).copy()
  saida = pd.DataFrame({
      "Solicitacao": df[col_solic].apply(lambda v: str(int(v))),
      "Item": df[col_item].apply(lambda v: str(int(v))),
  })
  return saida.drop_duplicates()


def obter_ou_criar_aba(spreadsheet):
  try:
    return spreadsheet.worksheet(ABA_PENDENCIAS)
  except gspread.WorksheetNotFound:
    return spreadsheet.add_worksheet(title=ABA_PENDENCIAS, rows=2000, cols=len(CABECALHO))


def substituir(worksheet, df):
  worksheet.clear()
  linhas = [CABECALHO] + df.values.tolist()
  worksheet.update(linhas, "A1")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--arquivo", required=True)
  parser.add_argument("--secrets", required=True)
  args = parser.parse_args()

  client = obter_client(args.secrets)
  spreadsheet = client.open_by_key(FILE_ID)
  worksheet = obter_ou_criar_aba(spreadsheet)

  df = carregar_arquivo(args.arquivo)
  substituir(worksheet, df)
  print(f"Aba '{ABA_PENDENCIAS}' substituida: {len(df)} itens em aberto agora.")


if __name__ == "__main__":
  main()
