"""Migracao pontual (nao recorrente): copia as Solicitacoes de jan-mar/2026
da aba antiga "Solicitações" (parada em 2026-09-01, abandonada quando o
Panorama trocou pra ler da aba "Solicitacoes") pra dentro da aba
"Solicitacoes" atual, que so tem historico a partir de 01/04/2026 - essas
3 meses nunca foram migrados quando o processo trocou.

Confirmado antes de escrever:
- 1900 linhas unicas (Solicitacao+Item) em jan-mar/2026 na aba antiga, ZERO
  overlap de chave com a aba "Solicitacoes" atual (nao duplica nada).
- As 1900 tem Pedido preenchido (100%) - ou seja, sao SCs ja atendidas,
  nao entram na fila "em aberto" do painel, so contam no historico mensal
  de Atendidos.
- Tambem migra a Criticidade (a aba antiga tem essa coluna direto, quase
  toda preenchida - 1872 de 1900) pra "Criticidade_Solicitacoes", mesma
  aba/mecanismo que atualizar_criticidade.py usa.

CUIDADO com a pegadinha de data que quase causou uma migracao errada: as
celulas de data na aba antiga sao datas reais do Excel, que o pandas (lido
com dtype=str) devolve como texto ISO "AAAA-MM-DD HH:MM:SS" - MUITO
diferente do texto "DD/MM/AAAA" da aba nova. Usar dayfirst=True nesse
texto ISO SWAPA dia/mes por engano (ex: "2026-07-01" virava 07/jan em vez
de 01/jul) - por isso aqui NAO se usa dayfirst, e a data e reescrita no
formato DD/MM/AAAA (igual a aba nova) so na hora de gravar.

Uso (uma vez só, nao precisa rodar de novo depois):
    python migrar_historico_jan_mar_2026.py --secrets caminho\\secrets.toml [--dry-run]
"""
import argparse
import tomllib

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

FILE_ID = "1e7pQ512ge5XMnXxsRODEO7V48KgWo6FpKeITFqBSg1o"
ABA_ANTIGA = "Solicitações"
ABA_ATUAL = "Solicitacoes"
ABA_CRITICIDADE = "Criticidade_Solicitacoes"

CABECALHO_ATUAL = [
    "SOLICITAÇÃO", "ITEM SC", "COTAÇÃO", "PEDIDO", "PRODUTO", "DESCRICAO",
    "QTD", "UM", "CENTRO DE CUSTO", "DESC CENTRO DE CUSTO", "DATA EMISSAO",
    "DATA APROVACAO", "FILIAL", "QTD EM PEDIDO", "STATUS",
]


def obter_client(secrets_path):
  with open(secrets_path, "rb") as f:
    dados = tomllib.load(f)
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds = Credentials.from_service_account_info(dados["gcp_service_account"], scopes=scope)
  return gspread.authorize(creds)


def limpar_numero(valor) -> str:
  txt = str(valor).strip()
  if not txt or txt.lower() in ("nan", "none", "-", "-   "):
    return ""
  return txt.split(".")[0].strip()


def formatar_data(valor) -> str:
  dt = pd.to_datetime(valor, errors="coerce")  # SEM dayfirst - ver docstring
  if pd.isna(dt):
    return ""
  return dt.strftime("%d/%m/%Y")


def carregar_linhas_jan_mar(spreadsheet):
  ws_antiga = spreadsheet.worksheet(ABA_ANTIGA)
  valores = ws_antiga.get_all_values()
  cabecalho = [c.strip() for c in valores[0]]
  df = pd.DataFrame(valores[1:], columns=cabecalho)

  col_dt_emissao = cabecalho[14]
  dt_emissao = pd.to_datetime(df[col_dt_emissao], errors="coerce")
  mask = (dt_emissao >= "2026-01-01") & (dt_emissao <= "2026-03-31")
  df_jm = df[mask].copy()

  df_jm["_solic"] = df_jm[cabecalho[4]].apply(limpar_numero)
  df_jm["_item"] = df_jm[cabecalho[12]].apply(limpar_numero)
  df_jm = df_jm.drop_duplicates(subset=["_solic", "_item"])

  linhas_novas = []
  for _, row in df_jm.iterrows():
    linhas_novas.append([
        row["_solic"],
        row["_item"],
        limpar_numero(row[cabecalho[5]]),
        limpar_numero(row[cabecalho[6]]),
        limpar_numero(row[cabecalho[7]]).zfill(10) if limpar_numero(row[cabecalho[7]]) else "",
        str(row[cabecalho[8]]).strip(),
        limpar_numero(row[cabecalho[9]]),
        str(row[cabecalho[13]]).strip(),
        limpar_numero(row[cabecalho[10]]),
        str(row[cabecalho[11]]).strip(),
        formatar_data(row[cabecalho[14]]),
        formatar_data(row[cabecalho[15]]),
        str(row[cabecalho[16]]).strip(),
        limpar_numero(row[cabecalho[17]]),
        "",  # STATUS - fica em branco, semantica da aba nova e diferente (ver docstring do modulo)
    ])

  df_criticidade = df_jm[["_solic", cabecalho[1]]].rename(
      columns={"_solic": "Solicitacao", cabecalho[1]: "Criticidade"}
  )
  df_criticidade = df_criticidade[df_criticidade["Criticidade"].str.strip() != ""]
  df_criticidade = df_criticidade.drop_duplicates(subset=["Solicitacao"])

  return linhas_novas, df_criticidade


def migrar_criticidade(spreadsheet, df_criticidade):
  ws = spreadsheet.worksheet(ABA_CRITICIDADE)
  valores = ws.get_all_values()
  cabecalho = valores[0]
  idx_solic = cabecalho.index("Solicitacao")
  existentes = {linha[idx_solic] for linha in valores[1:] if len(linha) > idx_solic}

  novas = df_criticidade[~df_criticidade["Solicitacao"].isin(existentes)]
  if novas.empty:
    return 0

  linhas = []
  for _, row in novas.iterrows():
    linha = [""] * len(cabecalho)
    linha[idx_solic] = row["Solicitacao"]
    linha[cabecalho.index("Criticidade")] = row["Criticidade"]
    linhas.append(linha)
  ws.append_rows(linhas, value_input_option="RAW")
  return len(linhas)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--secrets", required=True)
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  client = obter_client(args.secrets)
  spreadsheet = client.open_by_key(FILE_ID)

  linhas_novas, df_criticidade = carregar_linhas_jan_mar(spreadsheet)
  print(f"{len(linhas_novas)} linha(s) de Solicitacoes prontas pra migrar (jan-mar/2026).")
  print(f"{len(df_criticidade)} Criticidade(s) prontas pra migrar.")

  if args.dry_run:
    print("--dry-run: nada foi gravado. Amostra das 3 primeiras linhas:")
    for linha in linhas_novas[:3]:
      print(linha)
    return

  ws_atual = spreadsheet.worksheet(ABA_ATUAL)
  ws_atual.append_rows(linhas_novas, value_input_option="RAW")
  print(f"OK: {len(linhas_novas)} linhas gravadas em '{ABA_ATUAL}'.")

  qtd_crit = migrar_criticidade(spreadsheet, df_criticidade)
  print(f"OK: {qtd_crit} Criticidade(s) gravadas em '{ABA_CRITICIDADE}'.")


if __name__ == "__main__":
  main()
