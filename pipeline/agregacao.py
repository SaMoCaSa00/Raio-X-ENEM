"""Etapa 4: agregação.

Transforma milhões de linhas em tabelas pequenas (alguns KB) que o app lê
direto do repositório. Só entram nas médias os participantes que fizeram os
dois dias de prova e não são treineiros. Grupos com menos de 30 pessoas são
descartados, pra não publicar média instável nem expor gente.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from .dicionario import AREAS

MIN_N = 30
NOTAS = list(AREAS)


def medias_sql() -> str:
    return ", ".join(f"ROUND(AVG({n}), 1) AS {n.replace('NU_NOTA_', 'media_').lower()}" for n in NOTAS) + \
        ", ROUND(AVG(media_geral), 1) AS media_geral"


def agregar(parquet: Path, out: Path, ano: int) -> dict:
    con = duckdb.connect()
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()}
    filtro = "presente_ambos" + (" AND IN_TREINEIRO = 0" if "IN_TREINEIRO" in cols else "")
    con.execute(f"CREATE VIEW p AS SELECT * FROM read_parquet('{parquet}') WHERE {filtro}")
    out.mkdir(parents=True, exist_ok=True)
    feitos = {}

    def salvar(nome: str, sql: str):
        con.execute(f"COPY ({sql}) TO '{out / f'{nome}.parquet'}' (FORMAT parquet)")
        feitos[nome] = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out / f'{nome}.parquet'}')").fetchone()[0]

    def por(grupo: str, nome: str, extra_where: str = ""):
        if grupo.split(",")[0].strip() not in cols:
            return
        where = f"WHERE {grupo.split(',')[0]} IS NOT NULL {extra_where}"
        salvar(nome, f"SELECT {grupo}, COUNT(*) AS n, {medias_sql()} FROM p {where} "
                     f"GROUP BY {grupo} HAVING COUNT(*) >= {MIN_N} ORDER BY {grupo}")

    # Resumo geral
    inscritos = con.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet}')").fetchone()[0]
    r = con.execute(f"SELECT COUNT(*), {medias_sql()}, COUNT(*) FILTER (WHERE NU_NOTA_REDACAO = 1000), "
                    f"ROUND(MAX(NU_NOTA_MT), 1), ROUND(MEDIAN(media_geral), 1) FROM p").fetchone()
    resumo = {
        "ano": ano, "inscritos": inscritos, "presentes_analisados": r[0],
        "medias": dict(zip([n.replace("NU_NOTA_", "").lower() for n in NOTAS] + ["geral"], r[1:7])),
        "redacoes_nota_mil": r[7], "maior_nota_mt": r[8], "mediana_geral": r[9],
    }
    if "IN_TREINEIRO" in cols:
        resumo["treineiros"] = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet}') WHERE IN_TREINEIRO = 1").fetchone()[0]

    por("SG_UF_PROVA", "por_uf")
    if "CO_MUNICIPIO_PROVA" in cols:
        por("CO_MUNICIPIO_PROVA, NO_MUNICIPIO_PROVA, SG_UF_PROVA", "por_municipio")
    por("escola", "por_escola", "AND escola <> 'Não respondeu'")
    por("rede", "por_rede")
    por("sexo", "por_sexo")
    por("cor_raca", "por_cor_raca")
    por("renda_grupo", "por_renda")
    por("Q006, renda", "por_renda_detalhe")
    por("escolaridade_mae", "por_escolaridade_mae")
    por("internet", "por_internet")
    if {"renda_grupo", "escola"} <= cols:
        por("renda_grupo, escola", "renda_x_escola", "AND escola IN ('Pública', 'Privada')")

    # Distribuição de notas em faixas de 20 pontos, por área
    partes = [f"SELECT '{AREAS[n]}' AS area, FLOOR({n} / 20) * 20 AS faixa, COUNT(*) AS n FROM p "
              f"WHERE {n} IS NOT NULL GROUP BY 1, 2" for n in NOTAS]
    salvar("distribuicao", " UNION ALL ".join(partes) + " ORDER BY 1, 2")

    # Redação: quantos tiraram cada nota (múltiplos de 20)
    salvar("redacao", "SELECT NU_NOTA_REDACAO AS nota, COUNT(*) AS n FROM p "
                      "WHERE NU_NOTA_REDACAO IS NOT NULL GROUP BY 1 ORDER BY 1")

    resumo["tabelas"] = feitos
    (out / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=float))
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--processed", default="processed")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    res = agregar(Path(a.processed) / f"enem_{a.ano}.parquet", Path(a.out) / str(a.ano), a.ano)
    print(json.dumps(res, indent=2, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
