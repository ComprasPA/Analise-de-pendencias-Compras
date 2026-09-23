"""Atualiza a aba "Criticidade_Solicitacoes" na planilha do Panorama com os
dados de Criticidade exportados da tela de Cotações do TOTVS.

Processo manual temporário: a base do TOTVS ainda não carrega o campo
Criticidade por Solicitação (troca de sistema em andamento), então esse
dado chega por fora, num export da tela de Cotações. Rode este script toda
vez que chegar um export novo - ele faz upsert por número de Solicitação
(coluna "Número Protheus" do export), então pode rodar quantas vezes for
preciso sem duplicar linha.

Uso:
    python atualizar_criticidade.py --arquivo "Cotações - ....xls" --secrets caminho\\secrets.toml
"""
import argparse
import tomllib

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

FILE_ID = "1e7pQ512ge5XMnXxsRODEO7V48KgWo6FpKeITFqBSg1o"
ABA_CRITICIDADE = "Criticidade_Solicitacoes"
CABECALHO = ["Solicitacao", "Criticidade", "Centro de Custo", "Descricao", "Status", "Comprador"]


def obter_client(secrets_path):
  with open(secrets_path, "rb") as f:
    dados = tomllib.load(f)
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(dados["gcp_service_account"], scopes=scope)
  return gspread.authorize(creds)


def resolver_coluna(colunas, contem, obrigatoria=True):
  achada = next((c for c in colunas if contem.lower() in c.lower()), None)
  if achada is None and obrigatoria:
    raise RuntimeError(f"Coluna contendo '{contem}' nao encontrada. Colunas do arquivo: {list(colunas)}")
  return achada


def carregar_arquivo(caminho):
  df = pd.read_excel(caminho, sheet_name=0, header=0)
  df.columns = df.columns.astype(str).str.strip()

  col_num = resolver_coluna(df.columns, "Protheus")
  col_crit = resolver_coluna(df.columns, "Criticidade")
  col_cc = resolver_coluna(df.columns, "Centro de Custo", obrigatoria=False)
  col_desc = resolver_coluna(df.columns, "Descri", obrigatoria=False)
  col_status = resolver_coluna(df.columns, "Status", obrigatoria=False)
  col_comprador = resolver_coluna(df.columns, "Comprador", obrigatoria=False)

  df = df.dropna(subset=[col_num]).copy()
  df["Solicitacao"] = df[col_num].apply(lambda v: str(int(v)))
  df = df.drop_duplicates(subset=["Solicitacao"], keep="last")

  def col_ou_vazio(col):
    return df[col].fillna("").astype(str).str.strip() if col else ""

  saida = pd.DataFrame({
      "Solicitacao": df["Solicitacao"],
      "Criticidade": col_ou_vazio(col_crit),
      "Centro de Custo": col_ou_vazio(col_cc),
      "Descricao": col_ou_vazio(col_desc),
      "Status": col_ou_vazio(col_status),
      "Comprador": col_ou_vazio(col_comprador),
  })
  return saida


def obter_ou_criar_aba(spreadsheet):
  try:
    return spreadsheet.worksheet(ABA_CRITICIDADE)
  except gspread.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=ABA_CRITICIDADE, rows=4000, cols=len(CABECALHO))
    worksheet.update([CABECALHO], "A1")
    return worksheet


def upsert(worksheet, novos_df):
  valores_existentes = worksheet.get_all_values()
  if not valores_existentes:
    worksheet.update([CABECALHO], "A1")
    valores_existentes = [CABECALHO]

  cabecalho = valores_existentes[0]
  idx_solic = cabecalho.index("Solicitacao")
  indice_linha = {
      linha[idx_solic]: i + 2
      for i, linha in enumerate(valores_existentes[1:])
      if len(linha) > idx_solic and linha[idx_solic]
  }

  celulas = []
  novas_linhas = []
  qtd_atualizadas = 0
  for _, row in novos_df.iterrows():
    valores_linha = [str(row.get(c, "")) for c in cabecalho]
    chave = row["Solicitacao"]
    linha_num = indice_linha.get(chave)
    if linha_num:
      qtd_atualizadas += 1
      for col_idx, valor in enumerate(valores_linha, start=1):
        celulas.append(gspread.Cell(linha_num, col_idx, valor))
    else:
      novas_linhas.append(valores_linha)

  if celulas:
    worksheet.update_cells(celulas, value_input_option="RAW")
  if novas_linhas:
    worksheet.append_rows(novas_linhas, value_input_option="RAW")

  return qtd_atualizadas, len(novas_linhas)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--arquivo", required=True)
  parser.add_argument("--secrets", required=True)
  args = parser.parse_args()

  client = obter_client(args.secrets)
  spreadsheet = client.open_by_key(FILE_ID)
  worksheet = obter_ou_criar_aba(spreadsheet)

  df = carregar_arquivo(args.arquivo)
  atualizadas, novas = upsert(worksheet, df)
  print(f"{novas} solicitacao(oes) nova(s), {atualizadas} atualizada(s). Total no arquivo: {len(df)}.")


if __name__ == "__main__":
  main()
