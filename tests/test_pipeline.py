import json

import duckdb
import pytest

from pipeline import agregacao, qualidade, tratamento
from pipeline.dicionario import case_sql
from tests.fake_inep import gerar


@pytest.fixture()
def processado(tmp_path):
    gerar(tmp_path / "raw" / "2023" / "csv" / "MICRODADOS_ENEM_2023.csv")
    info = tratamento.tratar(2023, tmp_path / "raw", tmp_path / "processed")
    return tmp_path, info


def test_tratamento_tipa_e_traduz(processado):
    tmp, info = processado
    assert info["linhas"] == 400
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM '{tmp}/processed/enem_2023.parquet'").df()
    assert str(df["NU_NOTA_CH"].dtype) == "float64"          # "512,3" virou número
    assert set(df["NO_MUNICIPIO_PROVA"]) >= {"Uberlândia", "São Paulo"}  # latin-1 decodificado
    assert df["renda"].notna().all() and df["escola"].notna().all()
    ausentes = df[~df["presente_ambos"]]
    assert ausentes["NU_NOTA_MT"].isna().all() and ausentes["media_geral"].isna().all()


def test_qualidade_aprova_dado_limpo(processado):
    tmp, _ = processado
    rel = qualidade.avaliar(tmp / "processed" / "enem_2023.parquet")
    assert rel["aprovado"], rel


def test_qualidade_pega_nota_fora_da_escala(processado):
    tmp, _ = processado
    p = tmp / "processed" / "enem_2023.parquet"
    duckdb.execute(f"COPY (SELECT * REPLACE (CASE WHEN NU_INSCRICAO = '100000000001' THEN 1200 "
                   f"ELSE NU_NOTA_MT END AS NU_NOTA_MT) FROM '{p}') TO '{tmp}/ruim.parquet'")
    rel = qualidade.avaliar(tmp / "ruim.parquet")
    regra = next(r for r in rel["regras"] if r["regra"].startswith("NU_NOTA_MT fora"))
    assert regra["violacoes"] == 1 and not rel["aprovado"]


def test_agregacao_gera_tabelas_pequenas(processado):
    tmp, _ = processado
    res = agregacao.agregar(tmp / "processed" / "enem_2023.parquet", tmp / "data" / "2023", 2023)
    assert res["presentes_analisados"] > 0
    for t in ("por_uf", "por_renda", "por_escola", "distribuicao", "redacao"):
        assert res["tabelas"].get(t, 0) > 0, t
    resumo = json.loads((tmp / "data" / "2023" / "resumo.json").read_text())
    assert 0 < resumo["medias"]["geral"] < 1000


def test_renda_maior_nota_maior(processado):
    """O dado falso tem efeito de renda embutido; a agregação tem que mostrar isso."""
    tmp, _ = processado
    agregacao.agregar(tmp / "processed" / "enem_2023.parquet", tmp / "data" / "2023", 2023)
    df = duckdb.execute(f"SELECT * FROM '{tmp}/data/2023/por_renda.parquet' ORDER BY renda_grupo").df()
    assert df["media_mt"].iloc[-1] > df["media_mt"].iloc[0]


def test_case_sql():
    assert case_sql("X", {1: "a", "B": "b"}, "y") == "CASE WHEN X = 1 THEN 'a' WHEN X = 'B' THEN 'b' ELSE NULL END AS y"
