# 10 postagens para LinkedIn — Painel do Censo da Educação Superior

Mesma base de dados e mesmos achados das postagens de Instagram
(`docs/INSTAGRAM_10_POSTAGENS.md`), reescritas no registro do LinkedIn:
tom mais analítico, primeira pessoa, parágrafos curtos (quebra de linha
favorece leitura no feed), poucas hashtags no final, fechamento com
pergunta ou convite ao debate profissional. Sequência sugerida igual à
do Instagram, mas cada uma funciona isolada.

---

## 1. Lançamento do painel

Passei as últimas semanas construindo um painel público com os
microdados oficiais do Censo da Educação Superior (INEP), cobrindo 2009
a 2024 — 3,8 milhões de linhas, atualizadas direto da fonte oficial.

A motivação: relatórios estáticos em Excel/Power BI ficam desatualizados
rápido e não permitem que quem recebe explore por conta própria. Então
montei um pipeline (INEP → tratamento → BigQuery → Streamlit) e um
painel interativo, com filtros hierárquicos por região, estado,
município, tipo de instituição, área e curso.

Está no ar e é gratuito. Link nos comentários.

**#EducaçãoSuperior #DadosAbertos #INEP #DataAnalytics**

---

## 2. A virada histórica do EAD em 2024

Em 2024, pela primeira vez na história, mais brasileiros se matricularam
em cursos superiores a distância do que presenciais.

Os números, direto do Censo da Educação Superior (INEP):
- EAD em 2024: 5.189.391 matrículas
- Presencial em 2024: 5.037.875 matrículas

Para efeito de comparação, em 2009 o EAD representava apenas 14% do
total de matrículas. Hoje é 51%.

Mais chamativo ainda: o ensino presencial não perdeu só participação
relativa — perdeu alunos em número absoluto. O pico foi em 2015 (6,64
milhões); em 2024 são 5,04 milhões, uma queda de quase 1,6 milhão de
matrículas presenciais em 9 anos.

Isso levanta uma pergunta que interessa a quem trabalha com educação,
RH e desenvolvimento de talentos: o mercado de trabalho já está
absorvendo esse novo perfil de formação em massa e a distância? Que
efeitos isso tem sobre empregabilidade e qualificação técnica?

**#EAD #EnsinoADistancia #MercadoDeTrabalho #EducaçãoBrasil**

---

## 3. Setor privado cresceu mais que o dobro do público

Entre 2009 e 2024, o setor privado de ensino superior cresceu 83% em
matrículas (4,46 milhões → 8,16 milhões). O setor público cresceu 35%
no mesmo período (1,53 milhão → 2,07 milhões).

Isso significa que o setor privado respondeu pela grande maioria da
expansão de acesso ao ensino superior no Brasil nos últimos 15 anos —
puxado, em boa parte, pelo crescimento do próprio EAD, que é
majoritariamente ofertado por grupos privados.

Do ponto de vista de política pública, isso traz uma discussão
relevante: o financiamento estudantil (FIES, Prouni) e a regulação
desse setor privado em rápida expansão acompanharam esse ritmo?

**#EnsinoSuperior #PolíticaEducacional #SetorPrivado #INEP**

---

## 4. A região que mais cresceu não foi a que eu esperava

Ao olhar crescimento proporcional de matrículas por região entre 2009 e
2024, esperava que Sudeste ou Sul liderassem. Não foi o caso.

A Região Norte teve o maior crescimento relativo do país: 2,17x mais
matrículas em 2024 do que em 2009 (397.912 → 863.969). Sudeste segue
concentrando o maior volume absoluto (4,5 milhões em 2024), mas cresceu
"apenas" 59% no período.

Minha hipótese (a validar com mais profundidade): a expansão do EAD
chegou a regiões onde a oferta presencial historicamente era escassa,
por questões geográficas e de densidade populacional. Se for esse o
caso, é um efeito positivo de democratização de acesso que vale medir
com mais rigor — inclusive cruzando com dados de infraestrutura de
internet por município.

**#RegiãoNorte #InclusãoDigital #EducaçãoBrasil #DadosAbertos**

---

## 5. Saúde quase triplicou em 15 anos

A área de Saúde e Bem-estar (que inclui enfermagem, biomedicina,
psicologia, entre outros) passou de 860.980 para 2.345.749 matrículas
entre 2009 e 2024 — crescimento de 172%.

É a segunda maior expansão em volume absoluto entre todas as áreas de
conhecimento, atrás apenas de Negócios/Administração/Direito (que já
partia de uma base muito maior).

Não tenho ainda o recorte por curso específico dentro dessa área — é o
próximo passo da análise. Mas a hipótese óbvia (aquecimento do setor de
saúde privado e pressão de demanda pós-pandemia) merece ser testada com
dados, não só intuição.

**#Saúde #Enfermagem #EnsinoSuperior #EducaçãoBrasil**

---

## 6. Escala: uma rede de ensino x uma região inteira

Um dado que me impressionou ao construir o painel: a Universidade
Pitágoras Unopar Anhanguera (grupo Cogna) tem, sozinha, 836.889
matrículas em cursos a distância em 2024.

Para dimensionar: isso é mais do que TODA a Região Centro-Oeste tinha em
matrículas de ensino superior (todas as modalidades, todas as
instituições) em 2009 — 543.819. É mais também do que toda a Região
Norte tinha no mesmo ano.

A escala de operação do ensino a distância no Brasil hoje é de uma
ordem de grandeza completamente diferente do que existia há 15 anos.
Vale a reflexão sobre concentração de mercado, padronização de conteúdo
em escala nacional e o que isso significa para a diversidade da
formação superior brasileira.

**#EAD #ConcentraçãoDeMercado #EnsinoSuperior #EducaçãoBrasil**

---

## 7. Como um erro de leitura de dado quase virou uma conclusão errada

Ao calcular taxa de ocupação de vagas (matrículas ÷ vagas oferecidas),
43,7% dos cursos da base apareciam com mais de 100% de ocupação — em
alguns casos, acima de 200%.

Antes de publicar qualquer conclusão, fui direto ao dicionário de dados
oficial do INEP entender o porquê. A resposta: "matrículas" (QT_MAT)
soma TODOS os alunos ativos no curso — do calouro ao formando, todas as
turmas simultaneamente. "Vagas" (QT_VG_TOTAL) é só a vaga de calouro
daquele ano específico.

Num curso de 4 anos com matrícula estável, comparar as duas coisas é
comparar um estoque acumulado com um fluxo de um único ano — o
resultado passar de 100% é matemática básica, não vaga sobrando.

Troquei o cálculo para comparar fluxo com fluxo (ingressantes daquele
ano ÷ vagas daquele ano), e o resultado passou a fazer sentido: a
maioria dos cursos fica entre 20% e 60% de ocupação real.

Fica o lembrete profissional: número estranho geralmente não é "dado
ruim" — é definição mal entendida. Vale sempre voltar ao dicionário de
dados antes de tirar conclusão.

**#DataLiteracy #CiênciaDeDados #Metodologia #DadosAbertos**

---

## 8. Nem toda "vaga" reportada significa a mesma coisa

Um achado metodológico que vale compartilhar: cursos presenciais
preenchem, em média, 32% das vagas que declaram ao INEP. Cursos EAD
preenchem só 17%.

Isso não significa que o EAD tem metade da demanda do presencial — na
prática, é o oposto (o EAD hoje tem mais matrículas totais que o
presencial, ver post anterior). O que acontece é que instituições de
EAD costumam declarar um número de vagas nominalmente muito alto, sem
relação direta com capacidade real, já que não existe limitação física
de sala de aula.

Isso é um lembrete importante para qualquer análise comparativa entre
modalidades de ensino: dois indicadores com o mesmo nome ("taxa de
ocupação") podem estar medindo fenômenos completamente diferentes
dependendo de como a métrica de base foi construída pela instituição
que reporta o dado.

**#EAD #Metodologia #DadosAbertos #EnsinoSuperior**

---

## 9. Ingressantes dobraram. Concluintes, não.

Entre 2009 e 2024, o número de ingressantes no ensino superior brasileiro
mais que dobrou: de 2,08 milhões para 5,01 milhões (+141%). O número de
concluintes cresceu bem menos: de 967 mil para 1,33 milhão (+38%).

Importante ser preciso aqui: essa NÃO é uma taxa de evasão real, porque
comparar quem entra e quem sai no mesmo ano civil mistura coortes
diferentes (quem se forma em 2024 entrou anos antes, não em 2024).

Mas é um indicador que levanta uma pergunta legítima: o funil de entrada
está crescendo muito mais rápido do que a capacidade (ou o interesse) de
concluir. Merece um estudo de coorte de verdade — acompanhar quem entrou
em um ano específico e ver quantos concluem dentro do prazo esperado.

**#EnsinoSuperior #Evasão #EducaçãoBrasil #AnáliseDeDados**

---

## 10. Convite: o painel é público, os dados são seus

Todos os números que compartilhei nesta série vieram de um painel
público que qualquer pessoa pode filtrar do seu próprio jeito — por
região, estado, município, tipo de instituição, área de conhecimento,
curso específico.

Não é um relatório fechado. É uma ferramenta para profissionais de
educação, gestores públicos, jornalistas de dados e qualquer pessoa
curiosa encontrarem seu próprio ângulo de análise.

Se você trabalha com dados educacionais, mercado de trabalho ou gestão
de instituições de ensino e quiser trocar uma ideia sobre o que os
números mostram (ou sobre como cruzar essa base com outras fontes),
comento e sigo a conversa por aqui.

Link do painel nos comentários.

**#DadosAbertos #EnsinoSuperior #EducaçãoBrasil #DataDriven**

---

## Observação sobre tom

As legendas acima evitam claims causais fortes ("o EAD causou X") e
marcam explicitamente quando um número é uma hipótese a validar, não uma
conclusão — isso é intencional e recomendado manter, especialmente no
LinkedIn, onde o público inclui gestores e pesquisadores que vão
questionar afirmações não sustentadas pelos dados.
