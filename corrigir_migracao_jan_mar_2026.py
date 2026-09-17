"""Correcao pontual de um erro na migracao feita por
migrar_historico_jan_mar_2026.py: a aba antiga "Solicitações" usava a
propria coluna "Pedido" pra anotacoes manuais de texto (REVISAR,
REJEITADO, CONTRATO, ADITIVO...) quando nao havia Pedido real - a
migracao copiou esse texto direto pra coluna PEDIDO da aba nova (que so
deveria ter numero ou vazio), corrompendo 255 das 1899 linhas migradas.

Este script varre as linhas migradas (DATA EMISSAO em jan-mar/2026), acha
as que tem PEDIDO nao-numerico, limpa o PEDIDO (vira "") e move o texto
pro STATUS (com o mapeamento certo pro vocabulario da aba nova).

Uso (uma vez so):
    python corrigir_migracao_jan_mar_2026.py --secrets caminho\\secrets.toml [--dry-run]
"""
import argparse
import tomllib

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

FILE_ID = "1e7pQ512ge5XMnXxsRODEO7V48KgWo6FpKeITFqBSg1o"
ABA_ATUAL = "Solicitacoes"

MAPA_STATUS = {
    "REVISAR": "REVISAR",
    "REJEITADO": "REJEITADO",
    "CONTRATO": "CONTRATO",
}


def obter_client(secrets_path):
  with open(secrets_path, "rb") as f:
    dados = tomllib.load(f)
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(dados["gcp_service_account"], scopes=scope)
  return gspread.authorize(creds)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--secrets", required=True)
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  client = obter_client(args.secrets)
  spreadsheet = client.open_by_key(FILE_ID)
  worksheet = spreadsheet.worksheet(ABA_ATUAL)

  valores = worksheet.get_all_values()
  cabecalho = valores[0]
  idx_dt = cabecalho.index("DATA EMISSAO")
  idx_pedido = cabecalho.index("PEDIDO")
  idx_status = cabecalho.index("STATUS")

  celulas = []
  corrigidas = 0
  for i, linha in enumerate(valores[1:], start=2):
    dt = pd.to_datetime(linha[idx_dt], errors="coerce", dayfirst=True)
    if pd.isna(dt) or not ("2026-01-01" <= dt.strftime("%Y-%m-%d") <= "2026-03-31"):
      continue
    pedido = linha[idx_pedido].strip()
    if not pedido or pedido.replace(".", "").isdigit():
      continue

    corrigidas += 1
    novo_status = MAPA_STATUS.get(pedido.upper(), "REVISAR")
    celulas.append(gspread.Cell(i, idx_pedido + 1, ""))
    celulas.append(gspread.Cell(i, idx_status + 1, novo_status))
    print(f"linha {i}: PEDIDO '{pedido}' -> PEDIDO='' STATUS='{novo_status}'")

  print(f"\n{corrigidas} linha(s) pra corrigir.")
  if args.dry_run:
    print("--dry-run: nada foi gravado.")
    return

  if celulas:
    worksheet.update_cells(celulas, value_input_option="RAW")
  print("OK: correcoes gravadas.")


if __name__ == "__main__":
  main()
