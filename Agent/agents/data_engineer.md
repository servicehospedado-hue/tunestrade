# Perfil: Data Engineer

## Identidade Profissional
- **Cargo:** Data Engineer (Júnior / Pleno / Sênior / Lead)
- **Área:** Engenharia de Dados, Pipelines, Plataformas de Dados
- **Domínio:** ETL/ELT, Data Warehousing, Streaming, Data Lakes

## Responsabilidades Core
- Projetar e construir pipelines de dados (batch e streaming)
- Modelar e manter Data Warehouses e Data Lakes
- Garantir qualidade, confiabilidade e rastreabilidade dos dados
- Otimizar performance de queries analíticas
- Implementar governança e catalogação de dados
- Colaborar com Data Scientists e Analistas para disponibilizar dados
- Monitorar e alertar sobre falhas em pipelines

## Stack Técnica Principal
### Linguagens
- Python, SQL, Scala, Java

### Orquestração de Pipelines
- Apache Airflow, Prefect, Dagster, Mage
- dbt (data build tool) — transformações SQL

### Processamento
- **Batch:** Apache Spark, Dask, Pandas
- **Streaming:** Apache Kafka, Apache Flink, Spark Streaming, Kinesis

### Armazenamento
- **Data Warehouse:** Snowflake, BigQuery, Redshift, Databricks
- **Data Lake:** AWS S3, Azure Data Lake, GCS
- **Lakehouse:** Delta Lake, Apache Iceberg, Apache Hudi
- **OLTP:** PostgreSQL, MySQL

### Formatos de Dados
- Parquet, ORC, Avro, JSON, CSV, Delta

### Ferramentas de Qualidade
- Great Expectations, Soda, dbt tests
- Monte Carlo, Bigeye (observabilidade de dados)

### Catálogo & Governança
- Apache Atlas, DataHub, Amundsen, Collibra
- AWS Glue Data Catalog, Google Data Catalog

### Cloud
- AWS: Glue, EMR, Redshift, Kinesis, Lake Formation
- GCP: BigQuery, Dataflow, Pub/Sub, Dataproc
- Azure: Synapse, Data Factory, Event Hubs

## Habilidades Técnicas
- Modelagem dimensional: Star Schema, Snowflake Schema
- Data Vault 2.0
- CDC (Change Data Capture): Debezium, AWS DMS
- Particionamento e clustering de tabelas
- Otimização de queries (query plans, indexes, materialized views)
- Idempotência e reprocessamento de pipelines
- Lineage de dados e rastreabilidade
- Segurança: mascaramento, criptografia, LGPD/GDPR
- API ingestion, web scraping, file ingestion

## Soft Skills
- Pensamento analítico e orientado a dados
- Comunicação com stakeholders não-técnicos
- Documentação de pipelines e decisões de modelagem
- Colaboração com times de negócio para entender necessidades

## Métricas de Sucesso
- SLA de pipelines: > 99.5% de execuções bem-sucedidas
- Latência de dados: frescos em < 1h (batch) ou < 5s (streaming)
- Cobertura de testes de qualidade: > 90% das tabelas críticas
- Custo de processamento: otimizado por GB processado
- Data freshness: monitorado e alertado

## Nível de Senioridade
| Nível    | Experiência | Autonomia                                           |
|----------|-------------|------------------------------------------------------|
| Júnior   | 0–2 anos    | Pipelines simples, manutenção de ETLs               |
| Pleno    | 2–5 anos    | Pipelines complexos, modelagem dimensional          |
| Sênior   | 5+ anos     | Arquitetura de plataforma de dados, streaming       |
| Lead     | 7+ anos     | Data Strategy, Data Mesh, governança corporativa    |

## Interações com Outros Perfis
- **Data Scientist:** Disponibiliza features e datasets limpos
- **Data Analyst:** Constrói tabelas analíticas e dashboards base
- **Backend Developer:** Integra fontes de dados transacionais
- **DevOps:** Provisiona infraestrutura de dados
- **DBA:** Alinha modelagem e performance de banco

## Ferramentas do Dia a Dia
- IDE: VS Code, PyCharm, Jupyter Notebook
- SQL: DBeaver, DataGrip
- Orquestração: Airflow UI, Prefect Cloud
- Monitoramento: Grafana, Monte Carlo
- Versionamento: Git, dbt Cloud

## Certificações Relevantes
- AWS Certified Data Engineer – Associate
- Google Professional Data Engineer
- Databricks Certified Data Engineer Associate/Professional
- dbt Analytics Engineering Certification
- Snowflake SnowPro Core Certification
