"""
Mapas de código -> rótulo extraídos do Dicionário de Dados oficial do INEP
(Censo da Educação Superior). Fonte: dicionário cumulativo 2009-2023, incluso
no zip anual em Anexos/ANEXO I - Dicionário de Dados/.

Esses códigos são estáveis entre os ciclos 2020-2024 do censo.
"""

TP_REDE = {
    1: "Pública",
    2: "Privada",
}

TP_CATEGORIA_ADMINISTRATIVA = {
    1: "Pública Federal",
    2: "Pública Estadual",
    3: "Pública Municipal",
    4: "Privada com fins lucrativos",
    5: "Privada sem fins lucrativos",
    6: "Privada - Particular em sentido estrito",
    7: "Especial",
    8: "Privada comunitária",
    9: "Privada confessional",
}

TP_ORGANIZACAO_ACADEMICA = {
    1: "Universidade",
    2: "Centro Universitário",
    3: "Faculdade",
    4: "Instituto Federal de Educação, Ciência e Tecnologia",
    5: "Centro Federal de Educação Tecnológica",
}

TP_MODALIDADE_ENSINO = {
    1: "Presencial",
    2: "Curso a distância",
}

TP_GRAU_ACADEMICO = {
    1: "Bacharelado",
    2: "Licenciatura",
    3: "Tecnológico",
    4: "Bacharelado e Licenciatura",
}

TP_NIVEL_ACADEMICO = {
    1: "Graduação",
    2: "Sequencial de Formação Específica",
}

IN_CAPITAL = {
    0: "Não",
    1: "Sim",
}

IN_GRATUITO = {
    0: "Não",
    1: "Sim",
}
