"""Etapa 1: aquisição.

Baixa o zip de microdados do INEP com retomada (o arquivo tem centenas de MB
e o servidor derruba a conexão com frequência), confere a integridade do zip
e extrai só os CSVs da pasta DADOS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

import requests

URL = "https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"
CHUNK = 1 << 20


def baixar(url: str, destino: Path, tentativas: int = 8) -> Path:
    """Download com retomada via header Range."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".part")
    for t in range(1, tentativas + 1):
        ja = parcial.stat().st_size if parcial.exists() else 0
        headers = {"Range": f"bytes={ja}-"} if ja else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 416:  # já está completo
                    break
                r.raise_for_status()
                modo = "ab" if r.status_code == 206 else "wb"
                total = int(r.headers.get("Content-Length", 0)) + (ja if modo == "ab" else 0)
                with open(parcial, modo) as f:
                    for bloco in r.iter_content(CHUNK):
                        f.write(bloco)
                if total and parcial.stat().st_size < total:
                    raise IOError(f"incompleto: {parcial.stat().st_size} de {total} bytes")
            break
        except (requests.RequestException, IOError) as e:
            espera = min(60, 5 * t)
            print(f"[aquisição] tentativa {t} falhou ({e}); nova tentativa em {espera}s")
            time.sleep(espera)
    else:
        raise RuntimeError(f"não consegui baixar {url}")
    parcial.rename(destino)
    return destino


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(CHUNK), b""):
            h.update(bloco)
    return h.hexdigest()


def extrair_csvs(zip_path: Path, pasta: Path) -> list[Path]:
    """Extrai os CSVs de dados (ignora dicionários, leia-me e provas)."""
    pasta.mkdir(parents=True, exist_ok=True)
    saida = []
    with zipfile.ZipFile(zip_path) as z:
        ruim = z.testzip()
        if ruim:
            raise zipfile.BadZipFile(f"arquivo corrompido dentro do zip: {ruim}")
        for info in z.infolist():
            nome = Path(info.filename).name
            if nome.lower().endswith(".csv") and "DADOS" in info.filename.upper():
                alvo = pasta / nome
                with z.open(info) as src, open(alvo, "wb") as dst:
                    while bloco := src.read(CHUNK):
                        dst.write(bloco)
                saida.append(alvo)
    return saida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--raw", default="raw")
    a = ap.parse_args()

    raw = Path(a.raw) / str(a.ano)
    zip_path = raw / f"microdados_enem_{a.ano}.zip"
    if not zip_path.exists():
        baixar(URL.format(ano=a.ano), zip_path)
    csvs = extrair_csvs(zip_path, raw / "csv")
    meta = {
        "ano": a.ano,
        "fonte": URL.format(ano=a.ano),
        "baixado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "zip_bytes": zip_path.stat().st_size,
        "zip_sha256": sha256(zip_path),
        "csvs": {p.name: p.stat().st_size for p in csvs},
    }
    (raw / "aquisicao.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
