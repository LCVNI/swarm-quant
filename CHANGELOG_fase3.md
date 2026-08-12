# Changelog: Implementação da Fase 3 (Universo Investível)

Este documento registra as modificações realizadas nos arquivos de código-fonte para implementar a Fase 3 do `plano_implementacao.md`, que foca na inserção dos filtros de universo (liquidez e anomalias).

## 1. Modificações em `app_grafo.py`
A interface foi expandida para incluir os novos parâmetros e conectar-se aos módulos importados.
- **Importação:** Adicionada a instrução `import universo as uv`.
- **Interface Gráfica UI (Inputs):** Foi criado um *expander* exclusivo chamado "Filtros de Universo Investível (Fase 3)" abaixo do *file_uploader* principal do COTAHIST, contendo instâncias interativas como:
  - Checkbox para ligar/desligar a aplicação das regras do Módulo Universo.
  - Campos numéricos para `Preço Mínimo`, `Volume Mediano`, `Número de Negócios Mínimo` e `Janela Móvel de Liquidez`.
  - Checkbox para excluir ativos problemáticos que não tenham formatação acionária `(sufixos terminados em 3, 4, 11)`.
- **Injeção de Execução Backend:** O bloco que carregava os dados na seção `if arquivo and st.button("Carregar dados"):` foi interceptado e adicionada a verificação: se o filtro estivesse ativado, a rotina primeiro passaria os dados pelas funções puras `uv.ajustar_por_fator_cotacao`, `uv.filtrar_universo` e `uv.marcar_descontinuidades`. O script agora exporta no `st.session_state` o relatório auditor para exibição.
- **Exibição do Rastreio UI (Auditoria):** Na seção dos resultados, sob "Resumo por período", caso a filtragem ocorra, o aplicativo renderiza a tabela de diagnóstico quantificando exatamente quantos papéis sobreviveram a cada etapa.

## 2. Modificações em `grafo_estrategia.py`
A rotina responsável por calcular features do grafo com base na manipulação dos preenchimentos vetoriais foi atualizada para reconhecer se o ativo sofreu gaps espúrios.
- A função `construir_features_grafo` recebeu um tratamento explícito para o input `retorno_valido`.
- Sem este tratamento o `pct_change()` uniria magicamente dias temporalmente isolados originando retornos astronômicos devido ao corte de linhas do BDI ou liquidez do módulo Fase 3.
- Agora a equação neutraliza localizando `invalido = ~df["retorno_valido"]` e marca `["retorno_1d", "retorno_5d", "retorno_futuro"] = np.nan` nestas circunstâncias.

### Checklist (Status)
- [x] Universo modular importado no front-end.
- [x] Toggle interativo para testes on/off de liquidez adicionado ao app.
- [x] Filtros efetivados e auditados em tabelas nativas de session_state.
- [x] Motor estatístico do Market Graph seguro para descontinuidades originárias do filtro.
