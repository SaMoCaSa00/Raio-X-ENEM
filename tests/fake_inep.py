"""Gera um CSV pequeno no formato do INEP (latin-1, ';') pra testar o pipeline
sem baixar gigabytes. Inclui sujeira de propósito: acento em latin-1, nota com
vírgula, campo vazio e ausentes sem nota."""
from __future__ import annotations

import random
from pathlib import Path

COLS = ("NU_INSCRICAO;NU_ANO;TP_FAIXA_ETARIA;TP_SEXO;TP_COR_RACA;TP_ESCOLA;IN_TREINEIRO;"
        "TP_DEPENDENCIA_ADM_ESC;CO_MUNICIPIO_PROVA;NO_MUNICIPIO_PROVA;SG_UF_PROVA;"
        "TP_PRESENCA_CN;TP_PRESENCA_CH;TP_PRESENCA_LC;TP_PRESENCA_MT;"
        "NU_NOTA_CN;NU_NOTA_CH;NU_NOTA_LC;NU_NOTA_MT;TP_STATUS_REDACAO;"
        "NU_NOTA_COMP1;NU_NOTA_COMP2;NU_NOTA_COMP3;NU_NOTA_COMP4;NU_NOTA_COMP5;NU_NOTA_REDACAO;"
        "Q001;Q002;Q006;Q025").split(";")

CIDADES = [(3170206, "Uberlândia", "MG"), (3550308, "São Paulo", "SP"), (2927408, "Salvador", "BA")]


def gerar(path: Path, n: int = 400, ano: int = 2023, seed: int = 0) -> Path:
    rnd = random.Random(seed)
    linhas = [";".join(COLS)]
    for i in range(n):
        cod, nome, uf = rnd.choice(CIDADES)
        presente = rnd.random() > 0.25
        renda = rnd.choice("ABCDEFGHIJKLMNOPQ")
        escola = rnd.choice([1, 2, 2, 3])
        bonus = "ABCDEFGHIJKLMNOPQ".index(renda) * 8 + (40 if escola == 3 else 0)
        nota = lambda: f"{min(1000, max(300, rnd.gauss(480 + bonus, 70))):.1f}"
        if presente:
            notas = [nota() for _ in range(4)]
            notas[1] = notas[1].replace(".", ",")  # sujeira: decimal com vírgula
            comps = [rnd.choice(range(0, 201, 20)) for _ in range(5)]
            red = [1, *comps, sum(comps)]
            pres = [1, 1, 1, 1]
        else:
            notas, red, pres = ["", "", "", ""], ["", "", "", "", "", "", ""], [0, 0, 0, 0]
        row = [100000000000 + i, ano, rnd.randint(1, 10), rnd.choice("MF"), rnd.randint(0, 5), escola,
               int(rnd.random() < 0.05), rnd.choice(["", 2, 4]), cod, nome, uf, *pres, *notas, *red,
               rnd.choice("ABCDEFGH"), rnd.choice("ABCDEFGH"), renda, rnd.choice("AB")]
        linhas.append(";".join(map(str, row)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(linhas) + "\n").encode("latin-1"))
    return path
