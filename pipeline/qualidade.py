"""Etapa 3: qualidade.

Regras de validação rodadas sobre o Parquet tratado. Cada regra devolve quantas
linhas a violam. Regras "bloqueantes" derrubam o pipeline (dado claramente
quebrado); as outras só entram no relatório, porque fazem parte da realidade dos
dados (ex.: quem faltou não tem nota).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from .dicionario import AREAS

NOTAS = list(AREAS)
# Uma regra bloqueante só reprova o lote se o problema for sistemático.
# Casos isolados (ex.: 1 redação em 3,9 milhões com soma inconsistente) entram
# no relatório como anomalia, mas não descartam o ano inteiro.
TOLERANCIA_PCT = 0.001


def regras(cols: set[str]) -> list[tuple[str, str, bool]]:
    """(nome, condição que indica violação, bloqueante)"""
    r = []
    for n in NOTAS:
        if n in cols:
            r.append((f"{n} fora de 0 a 1000", f"{n} < 0 OR {n} > 1000", True))
    if {"NU_NOTA_COMP1", "NU_NOTA_REDACAO"} <= cols:
        soma = " + ".join(f"NU_NOTA_COMP{i}" for i in range(1, 6))
        r.append(("redação diferente da soma das 5 competências",
                  f"NU_NOTA_REDACAO IS NOT NULL AND ABS(({soma}) - NU_NOTA_REDACAO) > 0.01", True))
        for i in range(1, 6):
            r.append((f"competência {i} fora de 0 a 200",
                      f"NU_NOTA_COMP{i} < 0 OR NU_NOTA_COMP{i} > 200", True))
    for sigla in ("CN", "CH", "LC", "MT"):
        p, n = f"TP_PRESENCA_{sigla}", f"NU_NOTA_{sigla}"
        if {p, n} <= cols:
            r.append((f"presente em {sigla} sem nota", f"{p} = 1 AND {n} IS NULL", False))
            r.append((f"ausente em {sigla} com nota", f"{p} = 0 AND {n} IS NOT NULL", True))
    if "NU_INSCRICAO" in cols:
        r.append(("inscrição nula", "NU_INSCRICAO IS NULL", True))
    if "Q006" in cols:
        r.append(("renda (Q006) fora do dicionário", "Q006 IS NOT NULL AND renda IS NULL", True))
    if "TP_ESCOLA" in cols:
        r.append(("TP_ESCOLA fora do dicionário", "TP_ESCOLA IS NOT NULL AND escola IS NULL", True))
    if "SG_UF_PROVA" in cols:
        r.append(("UF da prova inválida", "SG_UF_PROVA IS NOT NULL AND LENGTH(SG_UF_PROVA) <> 2", True))
    return r


def avaliar(parquet: Path) -> dict:
    con = duckdb.connect()
    src = f"read_parquet('{parquet}')"
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}
    total = con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
    rs = regras(cols)
    if not rs:
        raise ValueError("nenhuma regra aplicável: colunas inesperadas")
    soma = ", ".join(f"COUNT(*) FILTER (WHERE {cond})" for _, cond, _ in rs)
    contagens = con.execute(f"SELECT {soma} FROM {src}").fetchone()
    resultado = [
        {"regra": nome, "violacoes": int(v), "pct": round(100 * v / total, 4) if total else 0, "bloqueante": b}
        for (nome, _, b), v in zip(rs, contagens)
    ]
    nulos = con.execute(
        "SELECT " + ", ".join(f"COUNT(*) FILTER (WHERE {n} IS NULL)" for n in NOTAS if n in cols) + f" FROM {src}"
    ).fetchone()
    duplicadas = 0
    if "NU_INSCRICAO" in cols:
        duplicadas = con.execute(
            f"SELECT COUNT(*) - COUNT(DISTINCT NU_INSCRICAO) FROM {src}").fetchone()[0]
        resultado.append({"regra": "inscrição duplicada", "violacoes": int(duplicadas),
                          "pct": round(100 * duplicadas / total, 4), "bloqueante": True})
    return {
        "linhas": total,
        "regras": resultado,
        "nulos_por_nota": {n: int(v) for n, v in zip([n for n in NOTAS if n in cols], nulos)},
        "tolerancia_pct": TOLERANCIA_PCT,
        "aprovado": all(r["pct"] <= TOLERANCIA_PCT for r in resultado if r["bloqueante"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--processed", default="processed")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    rel = avaliar(Path(a.processed) / f"enem_{a.ano}.parquet")
    rel["ano"] = a.ano
    destino = Path(a.out) / str(a.ano)
    destino.mkdir(exist_ok=True, parents=True)
    (destino / "qualidade.json").write_text(json.dumps(rel, indent=2, ensure_ascii=False))
    for r in rel["regras"]:
        flag = "❌" if r["violacoes"] and r["bloqueante"] else ("⚠️" if r["violacoes"] else "✅")
        print(f"{flag} {r['regra']}: {r['violacoes']:,} ({r['pct']}%)")
    if not rel["aprovado"]:
        raise SystemExit("qualidade reprovada: regra bloqueante violada")


if __name__ == "__main__":
    main()
