# Registro para currículo Lattes (CNPq)

*Texto pronto para colar nas seções correspondentes da Plataforma Lattes
— não é gerado nem enviado automaticamente pela IA, a Plataforma Lattes
não tem API de escrita pública; o cadastro precisa ser feito manualmente
por Antonio Pedro de Melo Maricato em lattes.cnpq.br, na área "Produção
técnica" (ou "Outras produções", conforme a versão do currículo).*

## Que tipo de item cadastrar

A produção descrita aqui se encaixa mais naturalmente em uma destas
categorias do Lattes, a depender de como o restante do currículo já está
organizado — escolher **uma**:

- **Produção técnica → Programa de computador** (se o pipeline/repositório
  for cadastrado como um software)
- **Produção técnica → Banco de dados** (se o foco for a base tratada e
  publicada, não o código)
- **Demais tipos de produção técnica → Outra produção técnica** (opção
  genérica, cabe bem para "painel + pipeline de dados públicos")

## Texto sugerido para o campo "Título"

```
Painel do Censo da Educação Superior (INEP): pipeline de tratamento e
harmonização de dados públicos, 2009-2024
```

## Texto sugerido para o campo "Descrição" / "Natureza"

```
Desenvolvimento de pipeline de extração, tratamento, harmonização e
disponibilização pública dos microdados oficiais do Censo da Educação
Superior (INEP), consolidando 16 ciclos anuais (2009-2024, 3.851.933
registros) em base analítica hospedada em Google BigQuery, com painel
interativo em Streamlit. Inclui rotina própria de auditoria e correção
de identidade de entidades (instituições, municípios e cursos) para
resolver inconsistências de grafia, acentuação e recadastro de código
institucional na série histórica publicada pelo órgão, com metodologia
de classificação de confiança para decidir de forma auditável quais
registros mesclar sem risco de conflação de entidades distintas.
```

## Texto sugerido para o campo "Palavras-chave"

```
Dados abertos; Censo da Educação Superior; INEP; Engenharia de dados;
Qualidade de dados; Resolução de entidades; BigQuery; Business
Intelligence; Educação superior
```

## Campos objetivos a preencher você mesmo

- **Ano:** 2026
- **País:** Brasil
- **Meio de divulgação:** painel público (Streamlit) + repositório no
  GitHub (`apmaricato/inep-ensino-superior`)
- **URL:** (a mesma pendência já registrada em `AGENTS.md` — confirmar a
  URL pública final do painel antes de preencher este campo)

## Observação

Este documento é um rascunho de apoio, não uma submissão. Revise o texto
antes de colar no Lattes — em especial os números (3.851.933 registros,
2009-2024), que devem ser conferidos contra o estado mais recente da
base antes da publicação, caso novos anos sejam adicionados depois desta
data.
