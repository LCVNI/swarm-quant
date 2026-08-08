# Indicadores de Desempenho e Risco para o Desafio Quant AI 2026

No contexto do **Desafio Quant AI 2026 da Itaú Asset**, a avaliação não se baseia apenas no "lucro absoluto". Em tesourarias institucionais e asset managements, o retorno financeiro só tem valor se o risco tomado for simétrico e controlado. O Edital e o Guia valorizam estratégias que apresentem retornos consistentes, proteção contra quedas bruscas e descorrelação com o mercado tradicional.

Abaixo estão as explicações dos principais indicadores que **devem** constar no relatório final da estratégia.

---

## 1. Indicadores de Risco vs. Retorno Histórico

### 📌 Índice de Sharpe (Sharpe Ratio)
**O que é:** Mede o retorno excedente (acima da taxa livre de risco, geralmente o CDI no Brasil) por cada unidade de risco (volatilidade) tomada.  
**Fórmula Básica:** `(Retorno da Estratégia - Retorno do CDI) / Volatilidade da Estratégia`  
**Por que no Relatório (Itaú):** É o indicador institucional mais famoso do mundo quant. Um Sharpe superior a `1.0` indica que a estratégia gera valor real. Um Sharpe muito alto (ex: `+2.0`) mostra que os ganhos são quase "linhas retas" para cima, sem sustos, o que é altamente premiado em competições Quant, pois fundos preferem consistência a saltos esporádicos.

### 📌 Maximum Drawdown (Rebaixamento Máximo)
**O que é:** A pior queda histórica de capital que a estratégia já sofreu do pico até o fundo.  
**Por que no Relatório (Itaú):** Em gestão de fundos da Itaú Asset, um Max Drawdown elevado (ex. -30%) causa pânico em cotistas e exige paradas na mesa (stop loss institucional). Demonstrar que o *Market Graph* da B3 é capaz de gerar bons lucros com um Drawdown contido (idealmente entre -5% e -15%) provará ao júri que o algoritmo possui excelente gestão de risco em crises. Fator eliminatório muitas vezes.

### 📌 Sortino Ratio (O Primo do Sharpe)
**O que é:** Semelhante ao Sharpe, porém ele **só penaliza a volatilidade negativa** (dias de queda).  
**Por que é Interessante:** Estratégias quantitativas baseadas em *Spillover* podem ter altos saltos para cima. O Sharpe penaliza esses saltos por tratar todos os desvios como volatilidade indesejada. O Sortino mostra ao júri que a variação da nossa curva de capital vem de grandes lucros (positividade), e não de instabilidade sistêmica.

---

## 2. Indicadores de Perfil e Correlação Sistêmica

### 📌 Beta (Exposição ao Mercado)
**O que é:** Mede a sensibilidade da estratégia em relação ao Ibovespa (Benchmark). Um Beta de `1` anda junto com o IBOV. Um Beta `> 1` é muito mais submisso e agressivo às oscilações da Bolsa.  
**Por que no Relatório (Itaú):** A grande busca da Itaú Asset em teses Quants modernas frequentemente foca em fundos "Beta Neutro" (`Beta próximo de 0`). Se o nosso algoritmo tem Beta `0.1` ou `-0.1`, a gente argumenta brilhantemente no relatório que **"A estratégia gera ganhos absolutos que independem de o Ibovespa estar subindo ou caindo"**. Isso vale ouro em fundos Multimercado Quantitativos.

### 📌 Alpha de Jensen (A Mágica da Estratégia)
**O que é:** O rendimento autônomo gerado que supera o rendimento esperado pelo fator Beta do mercado. É o famoso "valor adicionado pelo algoritmo".  
**Por que no Relatório (Itaú):** Ter um **Alpha Positivo consistente** atesta que a nossa tese matemática topológica (Market Graph) captura de fato assimetrias que o mercado eficiente não precifica de imediato. É a prova matemática rigorosa de que "estamos extraindo valor intrínseco, não apenas pegando carona na bolsa".

---

## 3. Outros Indicadores Complementares Essenciais no Relatório

### 📊 Win Rate (Taxa de Acerto ou Hit Ratio)
**O que é:** Percentual de operações encerradas no lucro versus o total operado.  
**Por que incluir:** Modelos de convergência e de reversão (como o *Spillover* dos vértices) costumam ostentar taxas de acerto mais elevadas (frequentemente `60-65%`). Expor essa simetria de vitórias traz confiança técnica ao relatório de que o ruído branco do mercado é mitigado pela bolha de correlação.

### 📊 Profit Factor (Fator de Lucro)
**O que é:** A soma de todo o dinheiro ganho (Gross Profit) dividida pela soma de todo o dinheiro perdido (Gross Loss).  
**Por que incluir:** Um *Profit Factor* > `1.5` ou `2.0` demonstra tremenda estabilidade. Atesta que o nosso caixa engole confortavelmente os custos perversos de corretagem e B3 modelados na arquitetura de custos de vocês.

### 📊 Calmar Ratio
**O que é:** O Retorno Anualizado dividido pelo Maximum Drawdown absoluto.  
**Por que incluir:** É uma prova rápida para comparativos robustos. Quem extrai maiores rendimentos ao longo dos anos, com as menores covas de prejuízos possíveis na linha do tempo? Muito requisitado.

---

## 4. Métricas Institucionais Premium (O "Grau Master" do Dashboard)

Para cravar categoricamente a postura de Fundo Institucional (e encantar o júri da Asset com o jargão do alto clero de gestão), a injeção dessas métricas secundárias destrói dúvidas sobre a solidez de longo prazo do algorítmo:

### 🏆 Information Ratio (Índice de Informação)
**O que é:** Enquanto o Sharpe compara com a Renda Fixa (CDI), o **Information Ratio (IR)** mede exclusivamente se o nosso robô vence o IBOVESPA com "esperteza" ou com apostas cegas.
**Como Calcular:** `(Média do Retorno da Norn - Média do Retorno do Ibovespa) / Tracking Error`. (O Tracking error é o desvio padrão/volatilidade da diferença diária entre Norn e IBOV).
**O Motivo (Por que ter):** Prova que a equipe não superou a Bolsa por pura loteria de variação. Um IR de 0.5 diz: "Temos um controle direcional que gera lucros ativos excedendo o benchmark consistentemente."

### 🏆 Volatilidade Anualizada do Fundo (Vol)
**O que é:** O Risco Bruto Despido (A instabilidade do nosso saldo no dia a dia).
**Como Calcular:** `Desvio Padrão Diário dos Retornos da Norn * √252 (Raiz dos dias úteis num ano)`.
**O Motivo (Por que ter):** Nenhum Comitê do Itaú aprova R$ 1 investido se não souber a volatilidade da tese! Eles preferem um fundo que renda só `15% ao ano` com `10% de Volatilidade`, do que um que renda absurdos `150% ao ano` custando assustadores `90% de Volatilidade` (que destrói os nervos dos clientes no sobe e desce intraday).  Esfregar uma baixa volatilidade no relatório atesta Governança de Risco!

### 🏆 Fator de Recuperação (Recovery Factor) e Dias Embaixo D'água (Underwater Time)
**O que é:** Quantidade de dinheiro absoluto feito dividida por quão feia foi a pior crise que o fundo engoliu.
**Como Calcular:** `Lucro Total Absoluto / Valor Absoluto Máximo de Drawdown`. (Se perdemos R$ 10.000 na pior queda, mas geramos R$ 40.000 no total geral, o fator é `4.0` - O Fundo sabe sair de covas triplamente mais fortes que suas derrotas).
**O Motivo (Por que ter):** Prova a "Elasticidade" do robô Norn. Quando os ruídos furam as defesas do Leiden e nós assumimos perda (Drawdown), nosso Spillover tem velocidade para recuperar e nadar de volta pràs máximas? É o medidor mestre de resiliência.

---

### Síntese para o Relatório Final (Júri do Desafio Quant)
No relatório ou notebook de apresentação final, deve-se construir uma tabela de métricas com a síntese desses KPIs listados. A principal linha estratégica de vendas do nosso modelo deve ser a comprovação de que gerar robôs que acertam mais do que dão prejuízo é fundamental, mas robôs com **Beta Neutro, Drawdown engessado e Alpha proeminente** formam o santo graal das Assets brasileiras, enquadrando rigorosamente o caso de uso nos guias avaliativos propostos pelo Edital do Itaú.
