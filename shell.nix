{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  # Definimos todas as dependências do requirements_grafo.txt aqui
  buildInputs = [
    (pkgs.python3.withPackages (ps: with ps; [
      pandas
      numpy
      scikit-learn
      streamlit
      pyarrow
      networkx
      requests
      yfinance
      matplotlib
    ]))
  ];

  shellHook = ''
    echo "=========================================================="
    echo "🚀 Ambiente NixOS Carregado para a Estratégia B3"
    echo "=========================================================="
    echo ""
    echo "Dependências prontas! Para rodar, digite apenas:"
    echo "  streamlit run app_grafo.py"
    echo ""
  '';
}
