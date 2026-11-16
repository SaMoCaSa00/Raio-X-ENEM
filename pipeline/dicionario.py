"""Tradução dos códigos do INEP pra rótulos legíveis.

Os microdados trazem quase tudo como código (TP_ESCOLA=2, Q006='D').
Aqui ficam os dicionários, conferidos com o dicionário oficial que vem
no zip de cada edição.
"""

AREAS = {
    "NU_NOTA_CN": "Ciências da Natureza",
    "NU_NOTA_CH": "Ciências Humanas",
    "NU_NOTA_LC": "Linguagens",
    "NU_NOTA_MT": "Matemática",
    "NU_NOTA_REDACAO": "Redação",
}

TP_ESCOLA = {1: "Não respondeu", 2: "Pública", 3: "Privada"}

TP_DEPENDENCIA_ADM_ESC = {1: "Federal", 2: "Estadual", 3: "Municipal", 4: "Privada"}

TP_SEXO = {"M": "Masculino", "F": "Feminino"}

TP_COR_RACA = {
    0: "Não declarado", 1: "Branca", 2: "Preta", 3: "Parda",
    4: "Amarela", 5: "Indígena", 6: "Não dispõe",
}

# Q006: renda mensal da família, em faixas de salário mínimo (SM).
# A ordem das letras é a ordem da renda, então dá pra ordenar pelo código.
RENDA = {
    "A": "Nenhuma renda", "B": "Até 1 SM", "C": "1 a 1,5 SM", "D": "1,5 a 2 SM",
    "E": "2 a 2,5 SM", "F": "2,5 a 3 SM", "G": "3 a 4 SM", "H": "4 a 5 SM",
    "I": "5 a 6 SM", "J": "6 a 7 SM", "K": "7 a 8 SM", "L": "8 a 9 SM",
    "M": "9 a 10 SM", "N": "10 a 12 SM", "O": "12 a 15 SM", "P": "15 a 20 SM",
    "Q": "Mais de 20 SM",
}

# Faixas mais largas, pra gráficos legíveis.
RENDA_GRUPO = {
    "A": "0. Sem renda", "B": "1. Até 1 SM", "C": "2. 1 a 2 SM", "D": "2. 1 a 2 SM",
    "E": "3. 2 a 3 SM", "F": "3. 2 a 3 SM", "G": "4. 3 a 5 SM", "H": "4. 3 a 5 SM",
    "I": "5. 5 a 10 SM", "J": "5. 5 a 10 SM", "K": "5. 5 a 10 SM", "L": "5. 5 a 10 SM",
    "M": "5. 5 a 10 SM", "N": "6. 10 a 20 SM", "O": "6. 10 a 20 SM", "P": "6. 10 a 20 SM",
    "Q": "7. Mais de 20 SM",
}

# Q002: até que série a mãe estudou.
ESCOLARIDADE = {
    "A": "1. Nunca estudou", "B": "2. Fundamental incompleto (até 4ª série)",
    "C": "3. Fundamental incompleto (5ª a 8ª)", "D": "4. Fundamental completo",
    "E": "5. Médio completo", "F": "6. Superior completo", "G": "7. Pós-graduação",
    "H": "8. Não sabe",
}

SIM_NAO = {"A": "Não", "B": "Sim"}


def case_sql(col: str, mapping: dict, alias: str) -> str:
    """Gera um CASE WHEN do DuckDB a partir de um dicionário."""
    def lit(v):
        return f"'{v}'" if isinstance(v, str) else str(v)
    whens = " ".join(f"WHEN {col} = {lit(k)} THEN '{v}'" for k, v in mapping.items())
    return f"CASE {whens} ELSE NULL END AS {alias}"
