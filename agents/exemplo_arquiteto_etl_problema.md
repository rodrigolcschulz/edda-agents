Problema: relatório diário de vendas

Uma empresa possui vendas registradas em um sistema. Todos os dias, ela precisa gerar um relatório com:

Total de vendas por dia
Total vendido por produto
Total vendido por vendedor
Quantidade de vendas
Ticket médio
Vendas por região

Fontes de dados:

vendas.csv → exportado diariamente pelo sistema
produtos.csv → cadastro de produtos
vendedores.csv → cadastro de vendedores

Regras:

Os arquivos podem ter registros duplicados.
Algumas vendas podem estar sem vendedor.
Valores de venda podem estar vazios ou inválidos.
O relatório deve considerar apenas vendas aprovadas.
Os dados precisam ser atualizados diariamente.
Seu desafio

Projete uma arquitetura de ETL que faça:

Extract
→ buscar os três arquivos

Transform
→ validar, limpar, deduplicar e enriquecer as vendas

Load
→ armazenar os dados tratados e disponibilizar uma tabela final para consumo do relatório.