# Harmonização de nomes na base do Censo da Educação Superior (INEP)

*Documento de apoio para artigo e divulgação. Autoria: Antonio Pedro de Melo
Maricato. Registra o trabalho de auditoria e correção de identidade de
entidades (instituições, municípios, cursos) na série histórica 2009–2024
do Painel do Censo da Educação Superior.*

## 1. O problema

Ao consolidar 16 ciclos anuais do Censo da Educação Superior numa única
base, um mesmo curso, instituição ou município pode aparecer sob mais de
uma grafia ao longo dos anos — o INEP não garante estabilidade textual da
série histórica. Isso fragmenta a mesma entidade real em múltiplas linhas
"diferentes" em qualquer filtro, `GROUP BY` ou ranking por nome, distorcendo
contagens (ex.: "quantas instituições distintas existem") e escondendo
tendência real atrás de ruído de grafia.

Três causas distintas foram identificadas, cada uma exigindo uma correção
diferente:

1. **Convenção de capitalização mudou entre anos** — ex.: `NO_CURSO` era
   publicado em MAIÚSCULO até 2020 e em Title Case a partir de 2021
   ("CIÊNCIA DA COMPUTAÇÃO" vs. "Ciência Da Computação").
2. **Acentuação inconsistente entre anos** — o mesmo nome aparece com e
   sem diacríticos em ciclos diferentes (ex.: "UNIVERSIDADE DE BRASILIA"
   em 2009 vs. "UNIVERSIDADE DE BRASÍLIA" nos anos seguintes), afetando
   instituições, municípios e cursos.
3. **O código de instituição (`CO_IES`) não é estável no tempo** —
   algumas instituições foram recadastradas pelo INEP com um código novo
   em algum ano da série, o que fragmenta a mesma IES real em dois
   registros com códigos diferentes, mesmo depois de (1) e (2) corrigidos.

## 2. Metodologia de correção

A regra geral adotada, já estabelecida no projeto para `NO_CURSO`
(ver `docs/METODOLOGIA.md`) e estendida aqui: **a grafia do ano mais
recente disponível é a canônica**, reaplicada retroativamente aos anos
mais antigos. Nunca se inventa uma regra própria de capitalização ou
acentuação — isso erraria preposições ("de"/"da") e exceções de
acentuação — sempre se reaproveita a decisão editorial mais recente do
próprio INEP.

A técnica de agrupamento muda conforme existe ou não um identificador
estável para a entidade:

| Entidade | Chave de agrupamento | Por quê |
|---|---|---|
| `NO_CURSO` | Texto normalizado (maiúsculo, sem acento, espaços colapsados) | Não existe código estável de "tipo de curso" reutilizável entre IES |
| `NO_IES` / `SG_IES` | `CO_IES` (código da instituição) | Código existe e identifica a entidade sem ambiguidade — evita colisão entre instituições de nome parecido |
| `NO_MUNICIPIO` | `CO_MUNICIPIO` (código IBGE) | Idem — e crucial aqui, porque nomes de município se repetem entre estados (ver §3.3) |

Para instituições, uma segunda camada de correção foi necessária: o
próprio `CO_IES` não é estável (§4).

## 3. Resultados por campo

Auditoria feita sobre os 3.851.933 registros da base consolidada
(2009–2024), comparando contagem de valores distintos antes e depois de
cada correção.

### 3.1. Já estavam consistentes (nenhuma ação necessária)

`NO_REGIAO`, `SG_UF`, `NO_UF`, `NO_CINE_AREA_GERAL`, `NO_CINE_AREA_ESPECIFICA`
— mesma contagem de valores distintos com ou sem normalização de caixa/acento.

### 3.2. `NO_CURSO`

- Chave de agrupamento fortalecida de `.upper()` para `.upper()` + remoção
  de acento (NFKD) + colapso de espaço duplo.
- **9.540 → 7.476** nomes distintos (-21,6%).
- Bônus incidental: 3.403 linhas com espaço duplo dentro do próprio nome
  do curso foram limpas no mesmo passo.

### 3.3. `NO_MUNICIPIO`

- Canonicalizado por `CO_MUNICIPIO` em vez de texto.
- **3.690 → 3.689** nomes distintos — impacto pequeno porque o problema
  real aqui era raro (1 município com preposição divergente entre anos:
  "Santo Antônio **de** Leverger" vs. "**do** Leverger", `CO_MUNICIPIO`
  5107800).
- **Achado negativo relevante:** pares de nomes que pareciam ser o mesmo
  erro de acentuação (ex.: "Iporá" / "Iporã", "Marau" / "Maraú") na
  verdade são **municípios brasileiros diferentes**, em estados
  diferentes, que só coincidem quando o acento é ignorado. Colapsá-los
  por texto teria introduzido um erro novo — por isso a canonicalização
  usa o código IBGE, que desambigua sem risco.

### 3.4. `NO_IES` / `SG_IES`

- Canonicalizado por `CO_IES`.
- **9.789 → 6.365** códigos/nomes distintos (-35%) — a correção de maior
  impacto absoluto, incluindo 5.271 linhas com espaço duplo no nome. Esse
  número já reflete a mesclagem dos 23 códigos recadastrados (§4).
- Auditoria pós-correção: **0 instituições com mais de uma grafia sob o
  mesmo `CO_IES`** (validação passou em 100% dos casos restantes).

## 4. `CO_IES` não é estável — o problema que sobrou

Mesmo após 3.3, buscar "Universidade de Brasília" no painel continuava
retornando duas entradas de grafia diferente em alguns casos — porque
**o código, não só o nome, mudou** entre anos para um subconjunto de
instituições. Colapsar por nome de texto sozinho seria arriscado: nomes
de fantasia se repetem entre instituições genuinamente distintas (ex.:
"FACULDADE METROPOLITANA" existe em Porto Velho/RO **e** em Lauro de
Freitas/BA — duas escolas sem nenhuma relação entre si).

**Processo de triagem:** dos 3.759 códigos de IES na base, 61 grupos de
nome idêntico (ignorando caixa/acento) apareciam sob mais de um `CO_IES`.
Cada grupo foi classificado por uma heurística de duas variáveis —
cidade primária de atuação e sobreposição do intervalo de anos entre os
códigos:

| Confiança | Critério | Interpretação | Grupos |
|---|---|---|---|
| **Alta** | Mesma cidade primária, **sem** sobreposição de anos | Um código "assume" exatamente onde o outro parou — recadastro da mesma IES | 23 |
| **Média** | Mesma cidade primária, **com** sobreposição de anos (3+ anos) | Pode ser transição administrativa ou duas unidades coexistindo — ambíguo | 13 |
| **Baixa** | Cidades primárias diferentes | Provavelmente duas instituições distintas com nome parecido | 25 |

Só os 23 grupos de **alta confiança** foram mesclados — mapeamento manual
e explícito `CO_IES` antigo → `CO_IES` canônico (o que continuou em uso
no ano mais recente), documentado linha a linha em
`scripts/transform.py` (constante `CO_IES_MERGES`). Os 38 grupos de
confiança média/baixa foram deliberadamente **mantidos como estão**: o
risco de juntar duas instituições reais e distintas sob um único nome no
painel foi julgado pior do que conviver com a duplicidade aparente.

Exemplo de caso mesclado (alta confiança): `FACULDADE PRISMA`, em Montes
Claros/MG — código `5033` usado até 2010, código `12189` a partir de
2011, sem sobreposição.

Exemplo de caso **não** mesclado (baixa confiança): `FACULDADE BRASILEIRA
DE TECNOLOGIA` — código `1968` em Aracaju/SE (ativo 2009–2024) e código
`17896` em Feira de Santana/BA (ativo 2017–2024), funcionando ao mesmo
tempo em cidades diferentes: duas escolas reais, não um recadastro.

## 5. Resultado final

- **3.759 → 3.736** códigos de IES distintos após a mesclagem dos 23
  grupos de alta confiança.
- Verificação ponta a ponta feita no painel em produção (busca por
  "Universidade de Brasília", "Iporá"/"Iporã", "Administração") — cada
  busca retorna exatamente as entidades reais esperadas, sem duplicata
  por grafia e sem colapsar municípios/instituições que são, de fato,
  diferentes.

## 6. Por que isso importa (para o artigo)

Esse processo é um lembrete prático de um problema comum em qualquer
consolidação de série histórica de dados públicos: a mesma entidade pode
ter *múltiplas* fontes de fragmentação simultâneas (grafia, acentuação,
identificador), e cada uma pede uma estratégia de correção diferente —
usar o identificador estável sempre que ele existir, e reservar
correção por texto/heurística só para quando não existir alternativa,
com critérios explícitos e auditáveis (não uma regra cega) para decidir
o que mesclar.

## 7. Como citar

```
MARICATO, Antonio Pedro de Melo. Harmonização de identidade de entidades
na base do Censo da Educação Superior (INEP), 2009–2024. Painel do Censo
da Educação Superior. [S. l.], 2026. Disponível em: <URL do painel — a
confirmar>. Acesso em: [dd mês. aaaa].
```
