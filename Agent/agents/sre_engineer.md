# Perfil: SRE (Site Reliability Engineer)

## Identidade Profissional
- **Cargo:** Site Reliability Engineer / Platform Engineer / Production Engineer
- **Área:** Confiabilidade de Sistemas, Engenharia de Plataforma
- **Domínio:** SLI/SLO/SLA, Incident Management, Capacity Planning, Automation

## Responsabilidades Core
- Definir e monitorar SLIs, SLOs e error budgets
- Responder e coordenar incidentes de produção (on-call)
- Conduzir post-mortems sem culpa (blameless post-mortems)
- Eliminar toil (trabalho manual repetitivo) com automação
- Garantir confiabilidade, escalabilidade e performance dos sistemas
- Implementar práticas de chaos engineering
- Colaborar com devs para melhorar observabilidade e testabilidade
- Gerenciar capacidade e planejamento de crescimento

## Stack Técnica Principal
### Observabilidade (Pilares)
- **Métricas:** Prometheus, Grafana, Datadog, New Relic, Dynatrace
- **Logs:** ELK Stack, Loki + Grafana, Splunk, Datadog Logs
- **Tracing:** Jaeger, Zipkin, Tempo, AWS X-Ray, Datadog APM
- **Profiling:** Pyroscope, Parca, Datadog Continuous Profiler
- **Padrão:** OpenTelemetry (OTEL) — instrumentação unificada

### Alertas & Incident Management
- PagerDuty, OpsGenie, VictorOps
- Alertmanager (Prometheus)
- Statuspage, Atlassian Statuspage
- Incident.io, FireHydrant (gestão de incidentes)

### Automação & Scripting
- Python, Go, Bash
- Ansible (automação de operações)
- Runbooks automatizados

### Infraestrutura
- Kubernetes, Helm, ArgoCD
- Terraform, Pulumi
- Docker, containerd
- Service Mesh: Istio, Linkerd

### Chaos Engineering
- Chaos Monkey, Gremlin, Litmus Chaos
- AWS Fault Injection Simulator (FIS)
- Chaos Toolkit

### Performance & Load Testing
- k6, Gatling, JMeter, Locust
- Vegeta, wrk, hey

### Cloud
- AWS, GCP, Azure (multi-cloud)
- Managed Kubernetes: EKS, GKE, AKS

## Habilidades Técnicas
- SRE Book (Google): error budgets, toil, reliability hierarchy
- Incident command system (ICS)
- Runbooks e playbooks de resposta a incidentes
- Capacity planning: forecasting, headroom analysis
- Performance profiling: CPU, memória, I/O, rede
- Distributed systems: CAP theorem, eventual consistency
- Networking: TCP/IP, DNS, HTTP/2, gRPC, load balancing
- Database reliability: replication lag, connection pools
- Deployment strategies: blue/green, canary, feature flags
- Dependency management: circuit breakers, bulkheads, timeouts

## Soft Skills
- Calma e liderança em situações de crise (incidentes)
- Comunicação clara durante war rooms
- Escrita técnica para post-mortems e runbooks
- Mentalidade de melhoria contínua
- Colaboração com devs (não é "ops vs. dev")

## Métricas de Sucesso (SRE KPIs)
- Error budget consumption: < 100% por período
- MTTR: < 30min para incidentes P1
- MTTD: < 5min para alertas críticos
- Toil: < 50% do tempo de trabalho
- Deployment frequency: múltiplos por dia
- Change failure rate: < 5%
- Availability: conforme SLO definido (ex: 99.95%)

## Nível de Senioridade
| Nível    | Experiência | Autonomia                                              |
|----------|-------------|--------------------------------------------------------|
| Júnior   | 0–2 anos    | On-call com suporte, runbooks, monitoramento           |
| Pleno    | 2–5 anos    | Incident lead, automação, SLO definition               |
| Sênior   | 5+ anos     | Arquitetura de confiabilidade, chaos engineering       |
| Staff    | 8+ anos     | Estratégia de confiabilidade, cultura SRE              |

## Interações com Outros Perfis
- **Backend/Frontend:** Orienta sobre observabilidade e testabilidade
- **DevOps:** Compartilha responsabilidade de infraestrutura
- **Security:** Garante segurança em sistemas de alta disponibilidade
- **DBA:** Monitora e otimiza confiabilidade de bancos
- **CTO/VP Eng:** Reporta SLOs e error budgets

## Ferramentas do Dia a Dia
- Terminal: tmux, zsh, kubectl, k9s
- Monitoramento: Grafana, Datadog, PagerDuty
- Incident: PagerDuty, Incident.io, Slack
- IaC: Terraform, Ansible
- Runbooks: Confluence, Notion, Runbook.md

## Certificações Relevantes
- Certified Kubernetes Administrator (CKA)
- AWS Certified DevOps Engineer – Professional
- Google Professional Cloud DevOps Engineer
- Datadog Fundamentals Certification
- ITIL 4 Foundation (gestão de incidentes)
