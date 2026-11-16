"""Roda o pipeline inteiro pra uma ou mais edições do Enem.

    python rodar.py 2023 2024

Precisa rodar de uma máquina com IP no Brasil: o servidor do INEP recusa
conexões de fora do país (inclusive dos runners do GitHub Actions).
No fim, só os dados agregados ficam em data/; os brutos são apagados.
"""
import json
import shutil
import sys
import time
from pathlib import Path

from pipeline import agregacao, qualidade, tratamento
from pipeline.aquisicao import URL, baixar, extrair_csvs, sha256

RAW, PROC, DATA = Path("raw"), Path("processed"), Path("data")


def etapa(nome):
    print(f"\n▶ {nome}", flush=True)
    return time.time()


def rodar(ano: int, manter_brutos: bool = False) -> None:
    print(f"\n════════ Enem {ano} ════════")
    raw = RAW / str(ano)
    zip_path = raw / f"microdados_enem_{ano}.zip"
    t = etapa("1/4 aquisição (download do INEP)")
    if not zip_path.exists():
        baixar(URL.format(ano=ano), zip_path)
    csvs = extrair_csvs(zip_path, raw / "csv")
    aq = {"ano": ano, "fonte": URL.format(ano=ano), "zip_bytes": zip_path.stat().st_size,
          "zip_sha256": sha256(zip_path), "baixado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "csvs": {p.name: p.stat().st_size for p in csvs}}
    print(f"  {len(csvs)} CSVs, {sum(aq['csvs'].values()) / 1e9:.2f} GB ({time.time() - t:.0f}s)")

    t = etapa("2/4 tratamento (CSV → Parquet tipado)")
    tr = tratamento.tratar(ano, RAW, PROC)
    print(f"  {tr['linhas']:,} linhas, Parquet de {tr['parquet_bytes'] / 1e6:.0f} MB ({time.time() - t:.0f}s)")

    t = etapa("3/4 qualidade")
    q = qualidade.avaliar(PROC / f"enem_{ano}.parquet")
    q["ano"] = ano
    for r in q["regras"]:
        if r["violacoes"]:
            print(f"  {'❌' if r['bloqueante'] else '⚠️'} {r['regra']}: {r['violacoes']:,} ({r['pct']}%)")
    print(f"  {'aprovado' if q['aprovado'] else 'REPROVADO'} ({time.time() - t:.0f}s)")

    t = etapa("4/4 agregação")
    res = agregacao.agregar(PROC / f"enem_{ano}.parquet", DATA / str(ano), ano)
    out = DATA / str(ano)
    for nome, conteudo in (("aquisicao", aq), ("tratamento", tr), ("qualidade", q)):
        (out / f"{nome}.json").write_text(json.dumps(conteudo, indent=2, ensure_ascii=False))
    print(f"  {len(res['tabelas'])} tabelas em {out} ({time.time() - t:.0f}s)")
    print(f"  média geral {res['medias']['geral']}, {res['presentes_analisados']:,} alunos analisados")
    if not q["aprovado"]:
        print("  ⚠️ qualidade reprovada: confira data/%d/qualidade.json antes de publicar" % ano)
    if not manter_brutos:
        shutil.rmtree(raw / "csv", ignore_errors=True)
        (PROC / f"enem_{ano}.parquet").unlink(missing_ok=True)


if __name__ == "__main__":
    anos = [int(a) for a in sys.argv[1:] if a.isdigit()] or [2023, 2024]
    for a in anos:
        rodar(a, manter_brutos="--manter" in sys.argv)
