"""Etapa 2: tratamento.

Lê os CSVs brutos do INEP (latin-1, separador ';', tudo como texto) com DuckDB,
sem carregar nada inteiro na memória, e grava um Parquet tipado e enxuto:

- converte notas pra número e códigos pra inteiro (TRY_CAST: valor estranho vira nulo
  em vez de derrubar o pipeline, e a etapa de qualidade conta quantos foram);
- padroniza nomes de colunas entre edições;
- traduz códigos (renda, tipo de escola, cor/raça...) pra rótulos;
- cria colunas derivadas: presente nos dois dias e média geral.

A partir de 2024 o INEP divide os microdados em mais de um arquivo
(participantes e resultados). Quando os arquivos têm uma chave em comum, eles
são unidos; quando não têm, cada tabela segue separada e as análises usam o
que cada uma permite.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from . import dicionario as d

NOTAS = list(d.AREAS)
COMPETENCIAS = [f"NU_NOTA_COMP{i}" for i in range(1, 6)]
INTEIROS = [
    "NU_ANO", "TP_FAIXA_ETARIA", "TP_COR_RACA", "TP_ESCOLA", "TP_ST_CONCLUSAO", "IN_TREINEIRO",
    "TP_DEPENDENCIA_ADM_ESC", "TP_LOCALIZACAO_ESC", "CO_MUNICIPIO_ESC", "CO_MUNICIPIO_PROVA",
    "TP_PRESENCA_CN", "TP_PRESENCA_CH", "TP_PRESENCA_LC", "TP_PRESENCA_MT", "TP_STATUS_REDACAO",
]
TEXTOS = [
    "TP_SEXO", "SG_UF_ESC", "NO_MUNICIPIO_ESC", "SG_UF_PROVA", "NO_MUNICIPIO_PROVA",
    "Q001", "Q002", "Q006", "Q022", "Q024", "Q025",
]
CHAVES = ["NU_INSCRICAO", "NU_SEQUENCIAL"]


def ler_csv_sql(path: Path) -> str:
    return (f"read_csv('{path}', delim=';', header=true, all_varchar=true, "
            f"encoding='latin-1', quote='\"', ignore_errors=true)")


def colunas(con: duckdb.DuckDBPyConnection, path: Path) -> list[str]:
    return [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {ler_csv_sql(path)}").fetchall()]


def selecao_tipada(cols: list[str]) -> list[str]:
    s = []
    for c in cols:
        if c in CHAVES:
            s.append(f"{c}")
        elif c in NOTAS or c in COMPETENCIAS:
            s.append(f"TRY_CAST(REPLACE({c}, ',', '.') AS DOUBLE) AS {c}")
        elif c in INTEIROS:
            s.append(f"TRY_CAST({c} AS INTEGER) AS {c}")
        elif c in TEXTOS:
            s.append(f"NULLIF(TRIM({c}), '') AS {c}")
    return s


def tratar(ano: int, raw: Path, out: Path) -> dict:
    csv_dir = raw / str(ano) / "csv"
    csvs = sorted(csv_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"nenhum CSV em {csv_dir}")
    con = duckdb.connect()
    con.execute("PRAGMA threads=4; SET preserve_insertion_order=false")

    tabelas = {}
    for p in csvs:
        cols = colunas(con, p)
        sel = selecao_tipada(cols)
        if not any(c in cols for c in NOTAS + ["Q006", "TP_ESCOLA"]):
            print(f"[tratamento] ignorando {p.name} (sem notas nem questionário)")
            continue
        nome = p.stem.lower()
        con.execute(f"CREATE TABLE \"{nome}\" AS SELECT {', '.join(sel)} FROM {ler_csv_sql(p)}")
        tabelas[nome] = [c.split(" AS ")[-1] for c in sel]
        n = con.execute(f'SELECT COUNT(*) FROM "{nome}"').fetchone()[0]
        print(f"[tratamento] {p.name}: {n:,} linhas")

    # Tabela com notas = base. Outras tabelas com chave em comum são unidas a ela.
    base = next((t for t, c in tabelas.items() if "NU_NOTA_MT" in c), None)
    if base is None:
        raise ValueError("nenhum arquivo com notas encontrado")
    juncao, unidas = f'"{base}" b', [base]
    for t, cols in tabelas.items():
        if t == base:
            continue
        chave = next((k for k in CHAVES if k in cols and k in tabelas[base]), None)
        if chave:
            extras = [c for c in cols if c not in tabelas[base]]
            if extras:
                juncao += f' LEFT JOIN (SELECT {chave}, {", ".join(extras)} FROM "{t}") USING ({chave})'
                unidas.append(t)
    todas = set().union(*(tabelas[t] for t in unidas))

    def tem(*cs):
        return all(c in todas for c in cs)

    derivadas = [
        f"{ano} AS ano",
        "(TP_PRESENCA_CN = 1 AND TP_PRESENCA_CH = 1 AND TP_PRESENCA_LC = 1 AND TP_PRESENCA_MT = 1) AS presente_ambos"
        if tem("TP_PRESENCA_CN", "TP_PRESENCA_MT") else
        "(NU_NOTA_MT IS NOT NULL AND NU_NOTA_CH IS NOT NULL) AS presente_ambos",
        "(NU_NOTA_CN + NU_NOTA_CH + NU_NOTA_LC + NU_NOTA_MT + NU_NOTA_REDACAO) / 5 AS media_geral",
    ]
    if tem("TP_ESCOLA"):
        derivadas.append(d.case_sql("TP_ESCOLA", d.TP_ESCOLA, "escola"))
    if tem("TP_DEPENDENCIA_ADM_ESC"):
        derivadas.append(d.case_sql("TP_DEPENDENCIA_ADM_ESC", d.TP_DEPENDENCIA_ADM_ESC, "rede"))
    if tem("TP_SEXO"):
        derivadas.append(d.case_sql("TP_SEXO", d.TP_SEXO, "sexo"))
    if tem("TP_COR_RACA"):
        derivadas.append(d.case_sql("TP_COR_RACA", d.TP_COR_RACA, "cor_raca"))
    if tem("Q006"):
        derivadas.append(d.case_sql("Q006", d.RENDA, "renda"))
        derivadas.append(d.case_sql("Q006", d.RENDA_GRUPO, "renda_grupo"))
    if tem("Q002"):
        derivadas.append(d.case_sql("Q002", d.ESCOLARIDADE, "escolaridade_mae"))
    if tem("Q025"):
        derivadas.append(d.case_sql("Q025", d.SIM_NAO, "internet"))

    out.mkdir(parents=True, exist_ok=True)
    destino = out / f"enem_{ano}.parquet"
    con.execute(f"""
        COPY (SELECT *, {', '.join(derivadas)} FROM {juncao})
        TO '{destino}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)
    """)
    # Tabelas sem chave em comum (ex.: questionário separado) seguem em Parquets próprios.
    for t in tabelas:
        if t not in unidas:
            con.execute(f"COPY \"{t}\" TO '{out / f'{t}.parquet'}' (FORMAT parquet, COMPRESSION zstd)")

    info = {
        "ano": ano,
        "arquivos": [p.name for p in csvs],
        "tabela_base": base,
        "unidas": unidas,
        "separadas": [t for t in tabelas if t not in unidas],
        "linhas": con.execute(f"SELECT COUNT(*) FROM '{destino}'").fetchone()[0],
        "parquet_bytes": destino.stat().st_size,
        "csv_bytes": sum(p.stat().st_size for p in csvs),
        "colunas": sorted(todas),
    }
    (out / f"tratamento_{ano}.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--out", default="processed")
    a = ap.parse_args()
    print(json.dumps(tratar(a.ano, Path(a.raw), Path(a.out)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
