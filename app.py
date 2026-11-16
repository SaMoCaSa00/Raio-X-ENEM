"""Raio-X do Enem: o que os microdados do INEP dizem sobre desigualdade na nota.

Rode com: streamlit run app.py
Os dados em data/ são gerados pelo pipeline (pipeline/), que roda no GitHub Actions.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
DATA = ROOT / "data"
RED, BLUE, GRAY = "#FF2A1F", "#38BDF8", "#A1A1AA"
AREAS = {"media_cn": "Natureza", "media_ch": "Humanas", "media_lc": "Linguagens",
         "media_mt": "Matemática", "media_redacao": "Redação", "media_geral": "Média geral"}

st.set_page_config(page_title="Raio-X do Enem", page_icon="📊", layout="wide")


def fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


@st.cache_data
def anos() -> list[int]:
    return sorted((int(p.name) for p in DATA.iterdir() if p.is_dir() and (p / "resumo.json").exists()), reverse=True)


@st.cache_data
def tabela(ano: int, nome: str) -> pd.DataFrame | None:
    p = DATA / str(ano) / f"{nome}.parquet"
    return duckdb.execute(f"SELECT * FROM read_parquet('{p}')").df() if p.exists() else None


@st.cache_data
def meta(ano: int, nome: str) -> dict:
    p = DATA / str(ano) / f"{nome}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def layout(fig, h=380, **kw):
    fig.update_layout(template="plotly_dark", height=h, margin=dict(l=10, r=10, t=40, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", **kw)
    return fig


def sem_prefixo(s: pd.Series) -> pd.Series:
    """Os grupos vêm como '3. 2 a 3 SM' pra ordenar; na tela fica só o rótulo."""
    return s.str.replace(r"^\d+\.\s*", "", regex=True)


ANOS = anos()
if not ANOS:
    st.error("Nenhum dado em data/. Rode o pipeline primeiro.")
    st.stop()

# ───────────── Sidebar ─────────────
with st.sidebar:
    st.markdown("## 📊 Raio-X do Enem")
    ano = st.selectbox("Edição", ANOS)
    area = st.selectbox("Nota analisada", list(AREAS), index=5, format_func=AREAS.get)
    st.caption("Fonte: microdados do Enem (INEP). Médias de quem fez os dois dias de prova, sem treineiros. "
               "Grupos com menos de 30 pessoas ficam de fora.")

R = meta(ano, "resumo")
st.markdown(f"<h1 style='margin-bottom:0'>Raio-X do <span style='color:{RED}'>Enem {ano}</span></h1>",
            unsafe_allow_html=True)
st.caption("Milhões de linhas de microdados do INEP, baixadas, tratadas e validadas por um pipeline automático. "
           "A pergunta: **o quanto a nota depende de onde o aluno vem?**")

k = st.columns(5)
k[0].metric("Inscritos", fmt(R["inscritos"]))
k[1].metric("Fizeram os 2 dias", fmt(R["presentes_analisados"]))
k[2].metric("Média geral", f"{R['medias']['geral']:.0f}")
k[3].metric("Média em Matemática", f"{R['medias']['mt']:.0f}")
k[4].metric("Redações nota 1000", fmt(R["redacoes_nota_mil"]))

t_des, t_mapa, t_notas, t_dados = st.tabs(["⚖️ Desigualdade", "🗺️ Estados e cidades", "📈 Notas", "🧪 Pipeline e qualidade"])

# ───────────── Desigualdade ─────────────
with t_des:
    renda = tabela(ano, "por_renda")
    if renda is not None and len(renda):
        renda = renda.sort_values("renda_grupo")
        baixo, alto = renda.iloc[0], renda.iloc[-1]
        gap = alto[area] - baixo[area]
        st.markdown(f"### Quem tem renda familiar acima de 20 salários mínimos tira, em média, "
                    f"<span style='color:{RED}'>{gap:.0f} pontos a mais</span> em {AREAS[area].lower()} "
                    f"do que quem não tem renda.", unsafe_allow_html=True)
        c1, c2 = st.columns([3, 2])
        with c1:
            fig = go.Figure(go.Bar(x=sem_prefixo(renda["renda_grupo"]), y=renda[area], marker_color=RED,
                                   text=renda[area].round(0), textposition="outside",
                                   customdata=renda["n"], hovertemplate="%{x}<br>média %{y:.1f}<br>%{customdata:,} alunos<extra></extra>"))
            layout(fig, title=f"{AREAS[area]} por renda familiar mensal", yaxis_range=[0, renda[area].max() * 1.15])
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig = px.pie(renda, names=sem_prefixo(renda["renda_grupo"]), values="n", hole=0.55,
                         color_discrete_sequence=px.colors.sequential.Reds_r)
            layout(fig, title="Quantos alunos em cada faixa", showlegend=True)
            fig.update_traces(textinfo="percent", sort=False)
            st.plotly_chart(fig, width="stretch")

    rxe = tabela(ano, "renda_x_escola")
    if rxe is not None and len(rxe):
        st.markdown("#### A escola privada explica tudo? Não.")
        st.caption("Comparando alunos da **mesma faixa de renda**, a diferença entre escola pública e privada diminui. "
                   "Boa parte do \"efeito escola\" é, na verdade, efeito renda.")
        rxe = rxe.sort_values("renda_grupo")
        fig = go.Figure()
        for esc, cor in (("Pública", BLUE), ("Privada", RED)):
            d = rxe[rxe["escola"] == esc]
            fig.add_trace(go.Scatter(x=sem_prefixo(d["renda_grupo"]), y=d[area], name=esc, mode="lines+markers",
                                     line=dict(color=cor, width=3), marker=dict(size=9)))
        layout(fig, h=360, title=f"{AREAS[area]}: pública × privada em cada faixa de renda",
               legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, width="stretch")

    c = st.columns(3)
    for col, (nome, campo, titulo) in zip(c, [("por_escolaridade_mae", "escolaridade_mae", "Escolaridade da mãe"),
                                              ("por_internet", "internet", "Tem internet em casa?"),
                                              ("por_cor_raca", "cor_raca", "Cor/raça declarada")]):
        df = tabela(ano, nome)
        if df is None or not len(df):
            continue
        df = df.sort_values(campo if nome != "por_cor_raca" else area)
        lab = sem_prefixo(df[campo].astype(str)).str.replace(r" \(.*\)", "", regex=True)
        fig = go.Figure(go.Bar(y=lab, x=df[area], orientation="h", marker_color=GRAY,
                               text=df[area].round(0), textposition="outside"))
        layout(fig, h=340, title=titulo, xaxis_range=[0, df[area].max() * 1.2])
        col.plotly_chart(fig, width="stretch")

# ───────────── Mapa ─────────────
with t_mapa:
    uf = tabela(ano, "por_uf")
    if uf is not None and len(uf):
        geo = json.loads((ROOT / "assets" / "br_uf.geojson").read_text())
        c1, c2 = st.columns([3, 2])
        with c1:
            fig = px.choropleth(uf, geojson=geo, locations="SG_UF_PROVA", featureidkey="properties.sigla",
                                color=area, color_continuous_scale="Reds", hover_data={"n": ":,"})
            fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
            layout(fig, h=520, title=f"{AREAS[area]} por estado (local de prova)",
                   coloraxis_colorbar=dict(title=""))
            st.plotly_chart(fig, width="stretch")
        with c2:
            u = uf.sort_values(area, ascending=False)[["SG_UF_PROVA", area, "n"]]
            u.columns = ["UF", AREAS[area], "alunos"]
            st.dataframe(u, hide_index=True, width="stretch", height=520,
                         column_config={AREAS[area]: st.column_config.ProgressColumn(
                             format="%.1f", min_value=0, max_value=float(u[AREAS[area]].max()))})

    mun = tabela(ano, "por_municipio")
    if mun is not None and len(mun):
        st.markdown("#### Cidades")
        c1, c2 = st.columns([1, 3])
        with c1:
            busca = st.text_input("Buscar cidade", "Uberlândia")
            min_n = st.slider("Mínimo de alunos", 30, 5000, 500, step=10)
        m = mun[mun["n"] >= min_n].copy()
        m["posição"] = m[area].rank(ascending=False, method="min").astype(int)
        m = m.sort_values("posição")
        alvo = m[m["NO_MUNICIPIO_PROVA"].str.contains(busca, case=False, na=False)] if busca else m.head(0)
        with c1:
            for _, r in alvo.head(3).iterrows():
                st.metric(f"{r['NO_MUNICIPIO_PROVA']} ({r['SG_UF_PROVA']})", f"{r[area]:.0f}",
                          f"{r['posição']}º de {len(m)} cidades", delta_color="off")
        with c2:
            show = m[["posição", "NO_MUNICIPIO_PROVA", "SG_UF_PROVA", area, "n"]]
            show.columns = ["#", "Cidade", "UF", AREAS[area], "alunos"]
            st.dataframe(show, hide_index=True, width="stretch", height=380)

# ───────────── Notas ─────────────
with t_notas:
    dist = tabela(ano, "distribuicao")
    if dist is not None and len(dist):
        fig = px.line(dist, x="faixa", y="n", color="area", line_shape="spline",
                      color_discrete_sequence=[RED, BLUE, "#F59E0B", "#22C55E", "#A78BFA"])
        layout(fig, h=400, title="Distribuição das notas por área", xaxis_title="nota", yaxis_title="alunos",
               legend=dict(orientation="h", y=1.12, title=""))
        st.plotly_chart(fig, width="stretch")
    red = tabela(ano, "redacao")
    if red is not None and len(red):
        fig = go.Figure(go.Bar(x=red["nota"], y=red["n"], marker_color=[RED if v == 1000 else GRAY for v in red["nota"]]))
        layout(fig, h=320, title="Redação: quantos alunos tiraram cada nota", xaxis_title="nota", yaxis_title="alunos")
        st.plotly_chart(fig, width="stretch")
        zeros = int(red.loc[red["nota"] == 0, "n"].sum())
        st.caption(f"{fmt(zeros)} redações com nota zero e {fmt(R['redacoes_nota_mil'])} com nota mil.")
    if len(ANOS) > 1:
        st.markdown("#### Comparando edições")
        linhas = [{"ano": a, **{AREAS["media_" + k] if "media_" + k in AREAS else k: v
                                for k, v in meta(a, "resumo")["medias"].items()}} for a in sorted(ANOS)]
        comp = pd.DataFrame(linhas).rename(columns={"geral": "Média geral"}).set_index("ano")
        st.dataframe(comp.round(1), width="stretch")

# ───────────── Pipeline ─────────────
with t_dados:
    st.markdown("""
    ```
    INEP (zip, centenas de MB)
       │  1. aquisição   download com retomada · sha256 · teste de integridade do zip
       ▼
    CSV latin-1, ';', tudo texto (GBs)
       │  2. tratamento  DuckDB lê em streaming · tipagem · decimal com vírgula · códigos → rótulos
       ▼
    Parquet tipado (≈10× menor)
       │  3. qualidade   regras de validação; regra bloqueante quebrada = pipeline para
       ▼
       │  4. agregação   tabelas de KB, grupos com < 30 pessoas removidos
       ▼
    data/  →  este app        (tudo roda sozinho no GitHub Actions)
    ```
    """)
    aq, tr, q = meta(ano, "aquisicao"), meta(ano, "tratamento"), meta(ano, "qualidade")
    c = st.columns(4)
    if aq:
        c[0].metric("Zip baixado", f"{aq['zip_bytes'] / 1e6:,.0f} MB")
    if tr:
        c[1].metric("CSV bruto", f"{tr['csv_bytes'] / 1e9:,.2f} GB")
        c[2].metric("Parquet tratado", f"{tr['parquet_bytes'] / 1e6:,.0f} MB",
                    f"{tr['csv_bytes'] / max(tr['parquet_bytes'], 1):.0f}× menor", delta_color="off")
    if q:
        c[3].metric("Linhas validadas", fmt(q["linhas"]))
        st.markdown("#### Regras de qualidade")
        regras = pd.DataFrame(q["regras"])
        regras["status"] = regras.apply(lambda r: "✅" if r.violacoes == 0 else ("❌" if r.bloqueante else "⚠️ esperado"), axis=1)
        regras["tipo"] = regras["bloqueante"].map({True: "bloqueante", False: "informativa"})
        st.dataframe(regras[["status", "regra", "violacoes", "pct", "tipo"]].rename(
            columns={"violacoes": "linhas", "pct": "% do total"}), hide_index=True, width="stretch")
    if aq:
        st.caption(f"Baixado de {aq['fonte']} em {aq['baixado_em']} · sha256 `{aq['zip_sha256'][:16]}…`")
