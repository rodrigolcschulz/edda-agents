A empresa precisa criar um pipeline de dados para consolidar informações de vendas provenientes de arquivos CSV.

Atualmente, os dados são exportados diariamente de diferentes sistemas e precisam ser preparados para geração de relatórios gerenciais.

O pipeline deverá:

* Receber diariamente os arquivos de vendas, produtos e vendedores.
* Armazenar os dados originais para permitir auditoria e reprocessamento.
* Validar e limpar os dados.
* Identificar registros duplicados.
* Relacionar vendas com produtos e vendedores.
* Considerar somente vendas aprovadas.
* Tratar vendas com vendedor ausente.
* Disponibilizar os dados tratados para consumo de relatórios.
* Permitir que o processo seja executado novamente caso alguma etapa falhe.

O resultado esperado é uma solução automatizada de ETL que processe os dados diariamente e disponibilize uma camada confiável para análise das vendas.
