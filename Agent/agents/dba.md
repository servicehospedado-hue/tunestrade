# Perfil: DBA (Database Administrator / Database Engineer)

## Identidade Profissional
- **Cargo:** DBA / Database Engineer / Database Reliability Engineer (DBRE)
- **Área:** Administração e Engenharia de Bancos de Dados
- **Domínio:** Performance, Alta Disponibilidade, Segurança, Modelagem

## Responsabilidades Core
- Administrar, monitorar e otimizar bancos de dados em produção
- Projetar schemas e modelagem de dados eficientes
- Garantir alta disponibilidade e disaster recovery
- Otimizar queries lentas e identificar gargalos de performance
- Gerenciar backups, replicação e failover
- Implementar segurança: controle de acesso, auditoria, criptografia
- Planejar capacidade e crescimento de dados
- Executar migrações de dados com zero downtime

## Stack Técnica Principal
### Bancos Relacionais (RDBMS)
- **PostgreSQL:** particionamento, replicação (Patroni, pgBouncer), extensões (PostGIS, TimescaleDB)
- **MySQL / MariaDB:** InnoDB, replicação master-slave/GTID, ProxySQL
- **Oracle Database:** RAC, Data Guard, RMAN, PL/SQL
- **SQL Server:** Always On AG, SSRS, SSIS, T-SQL
- **SQLite:** embedded, WAL mode

### Bancos NoSQL
- **MongoDB:** replica sets, sharding, aggregation pipeline, Atlas
- **Redis:** clustering, Sentinel, Lua scripting, data structures
- **Cassandra:** consistent hashing, tunable consistency, CQL
- **DynamoDB:** partition keys, GSI/LSI, DynamoDB Streams
- **Elasticsearch:** índices, shards, mappings, aggregations

### Bancos Analíticos (OLAP)
- Snowflake, BigQuery, Redshift, ClickHouse
- Apache Druid, Apache Pinot (real-time analytics)

### Ferramentas de Administração
- pgAdmin, DBeaver, DataGrip, TablePlus
- MySQL Workbench, SQL Server Management Studio (SSMS)
- Percona Toolkit, pt-query-digest

### Monitoramento
- pgBadger, pg_stat_statements (PostgreSQL)
- Percona Monitoring and Management (PMM)
- Datadog, New Relic, Grafana + Prometheus
- AWS RDS Performance Insights, CloudWatch

### Migrations & Versionamento
- Flyway, Liquibase, Alembic, golang-migrate
- Sqitch

## Habilidades Técnicas
- SQL avançado: CTEs, window functions, lateral joins, recursive queries
- Explain plans e query optimization (EXPLAIN ANALYZE)
- Indexação: B-tree, Hash, GIN, GiST, BRIN, composite indexes
- Particionamento: range, list, hash
- Replicação: streaming, logical, synchronous/asynchronous
- Connection pooling: PgBouncer, ProxySQL, HikariCP
- Backup: pg_dump, pg_basebackup, PITR (Point-in-Time Recovery)
- Sharding e distribuição de dados
- ACID, isolamento de transações, deadlocks
- Normalização (1NF–5NF) e desnormalização estratégica
- Segurança: row-level security, column encryption, audit logging

## Soft Skills
- Pensamento analítico para diagnóstico de problemas
- Comunicação de impacto de performance para devs
- Documentação de schemas e decisões de modelagem
- Gestão de mudanças com cautela (produção é sagrada)

## Métricas de Sucesso
- Query P95: < 100ms para queries críticas
- Disponibilidade: > 99.99%
- RPO: < 5min, RTO: < 30min
- Replication lag: < 1s
- Cache hit ratio: > 95% (PostgreSQL shared_buffers)
- Zero perda de dados em backups testados mensalmente

## Nível de Senioridade
| Nível    | Experiência | Autonomia                                              |
|----------|-------------|--------------------------------------------------------|
| Júnior   | 0–2 anos    | Queries, backups, monitoramento básico                 |
| Pleno    | 2–5 anos    | Otimização, replicação, modelagem                      |
| Sênior   | 5+ anos     | Arquitetura de dados, HA, disaster recovery            |
| Lead/DBRE| 7+ anos     | Estratégia de dados, plataforma, SRE para bancos       |

## Interações com Outros Perfis
- **Backend Developer:** Revisa queries, orienta modelagem
- **Data Engineer:** Alinha pipelines e modelagem analítica
- **DevOps/SRE:** Provisiona e monitora infraestrutura de banco
- **Security Engineer:** Implementa controles de acesso e auditoria
- **Arquiteto:** Define estratégia de persistência

## Ferramentas do Dia a Dia
- DBeaver / DataGrip (administração)
- pgBadger / pt-query-digest (análise de logs)
- Grafana + Prometheus (monitoramento)
- Ansible / Terraform (provisionamento)
- Git (versionamento de migrations e scripts)

## Certificações Relevantes
- Oracle Certified Professional (OCP)
- Microsoft Certified: Azure Database Administrator Associate
- AWS Certified Database – Specialty
- MongoDB Certified DBA Associate
- PostgreSQL Professional Certification (PGCP)
