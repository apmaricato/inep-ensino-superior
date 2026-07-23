# Posts para LinkedIn — Harmonização de dados no Painel INEP

Série separada dos 10 posts de achados (`docs/LINKEDIN_10_POSTAGENS.md`):
aqui o assunto é o processo de engenharia de dados por trás do painel, não
um resultado analítico. Público-alvo inclui gente de dados/engenharia além
do público de educação — tom técnico, mas sem jargão desnecessário. Mesmo
padrão de formatação: parágrafos curtos, poucas hashtags, fecho com
convite ao debate.

---

## 1. "Quantas instituições distintas existem na base?" — pergunta mais
difícil do que parece

Enquanto revisava os filtros do painel do Censo da Educação Superior
(INEP), reparei em algo estranho: buscar por uma instituição às vezes
trazia duas entradas quase idênticas — mesmo nome, uma com acento e
outra sem.

Fui auditar a série completa (2009–2024, 3,85 milhões de linhas) e
descobri três fontes de fragmentação diferentes, empilhadas: convenção
de capitalização que mudou entre anos, acentuação inconsistente do
próprio INEP entre ciclos, e — a mais chata — o código de algumas
instituições simplesmente mudou ao longo do tempo.

Nenhuma delas se resolve com um único `.upper()`. Cada uma pediu uma
estratégia diferente. Detalhei o processo completo em
`docs/HARMONIZACAO_DADOS.md` no repositório do projeto.

**#DataEngineering #QualidadeDeDados #INEP #DadosAbertos**

---

## 2. Por que eu não confiei em "mesmo nome = mesma instituição"

A parte mais delicada: 61 instituições apareciam sob mais de um código
ao longo dos 16 anos da série, com o nome idêntico. Parecia óbvio
mesclar todas — exceto que não era.

Descobri que "FACULDADE METROPOLITANA" existe em Porto Velho (RO) *e*
em Lauro de Freitas (BA). Nomes de fantasia se repetem entre
instituições que não têm nenhuma relação entre si. Mesclar automático
por nome teria juntado dados de duas escolas completamente diferentes
num único registro — um erro pior do que o que eu estava tentando
corrigir.

A solução: classificar cada um dos 61 casos por confiança, cruzando
cidade de atuação e sobreposição de anos entre os códigos. Só mesclei
os 23 casos onde um código claramente "assumiu" de onde o outro parou,
na mesma cidade. Os outros 38 ficaram como estão — a incerteza documentada
é mais honesta do que uma mesclagem errada e invisível.

Isso mudou minha régua para qualquer deduplicação de entidade daqui pra
frente: identificador estável sempre que existir, texto só quando não
tiver alternativa, e nunca automatizar o caso ambíguo sem critério
explícito.

**#DataQuality #EntityResolution #Python #Pandas**

---

## 3. O resultado, em números

Depois da auditoria e correção:

- Nomes de curso: 9.540 → 7.476 grafias distintas (-21,6%)
- Nomes/siglas de instituição: 9.789 → 6.365 (-35%)
- Códigos de instituição: 3.759 → 3.736, após mesclar só os 23 casos de
  alta confiança de recadastro
- Zero instituições com mais de uma grafia sob o mesmo código, validado
  ponta a ponta no painel em produção

Nenhum número de matrícula, ingressante ou concluinte mudou — essa
correção afeta só como as entidades são *identificadas e agrupadas* nos
filtros, não a métrica em si. Mas sem ela, qualquer "top N instituições"
ou "quantas IES distintas" do painel estaria sutilmente errado.

Painel e pipeline completos, com o código de auditoria disponível no
repositório. Link nos comentários.

**#EducaçãoSuperior #OpenData #DataAnalytics**
