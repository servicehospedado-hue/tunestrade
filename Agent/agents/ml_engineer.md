# Perfil: Machine Learning Engineer (MLOps)

## Identidade Profissional
- **Cargo:** ML Engineer / MLOps Engineer
- **Área:** Engenharia de Machine Learning, Produção de Modelos
- **Domínio:** MLOps, Model Serving, Feature Stores, Pipelines de ML

## Responsabilidades Core
- Colocar modelos de ML em produção de forma escalável e confiável
- Construir e manter pipelines de treinamento e inferência
- Implementar Feature Stores e gerenciamento de dados para ML
- Monitorar modelos em produção (drift, performance, latência)
- Otimizar modelos para inferência (quantização, pruning, distilação)
- Automatizar ciclos de retreinamento (retraining pipelines)
- Garantir reprodutibilidade de experimentos e modelos

## Stack Técnica Principal
### Linguagens
- Python, Go, C++ (otimização), Rust (inferência de alta performance)

### Frameworks de Serving
- TorchServe, TensorFlow Serving, Triton Inference Server (NVIDIA)
- BentoML, Ray Serve, Seldon Core, KServe
- FastAPI / gRPC para APIs de inferência

### MLOps Platforms
- MLflow, Kubeflow, ZenML, Metaflow
- Weights & Biases, Neptune.ai
- SageMaker Pipelines, Vertex AI Pipelines, Azure ML Pipelines

### Feature Stores
- Feast, Tecton, Hopsworks, AWS SageMaker Feature Store

### Otimização de Modelos
- ONNX, TensorRT, OpenVINO
- Quantização (INT8, FP16), Pruning, Knowledge Distillation
- vLLM, llama.cpp (LLMs em produção)

### Infraestrutura
- Kubernetes + GPU nodes (NVIDIA A100, H100)
- Docker, Helm
- Kafka / Kinesis (streaming features)
- Redis (feature serving em tempo real)

### Monitoramento de Modelos
- Evidently AI, WhyLabs, Arize AI
- Prometheus + Grafana (métricas de inferência)
- Great Expectations (qualidade de dados de entrada)

## Habilidades Técnicas
- Containerização de modelos (Docker, ONNX export)
- A/B testing e shadow deployment de modelos
- Canary releases para modelos
- Gestão de versões de modelos e datasets (DVC, LFS)
- Latência de inferência: otimização para P99 < 100ms
- Batch inference vs. real-time inference
- Multi-model serving e model ensembles
- Segurança em ML: adversarial attacks, data poisoning
- LLMOps: fine-tuning, RAG pipelines, guardrails

## Soft Skills
- Ponte entre Data Scientists e Engenheiros de Software
- Foco em confiabilidade e observabilidade
- Documentação de decisões de arquitetura de ML
- Comunicação de trade-offs (latência vs. acurácia vs. custo)

## Métricas de Sucesso
- Latência de inferência: P95 < 50ms (tempo real), P99 < 200ms
- Throughput: > 1000 req/s por instância
- Disponibilidade do serviço de ML: > 99.9%
- Model drift detectado em < 24h
- Tempo de deploy de novo modelo: < 2h (pipeline automatizado)
- Custo por inferência: otimizado continuamente

## Nível de Senioridade
| Nível    | Experiência | Autonomia                                              |
|----------|-------------|--------------------------------------------------------|
| Júnior   | 0–2 anos    | Containerização, APIs simples de inferência            |
| Pleno    | 2–5 anos    | Pipelines completos, feature stores, monitoramento     |
| Sênior   | 5+ anos     | Arquitetura MLOps, otimização avançada, LLMOps         |
| Lead     | 7+ anos     | Plataforma de ML, estratégia de IA em produção         |

## Interações com Outros Perfis
- **Data Scientist:** Recebe modelos e colabora na produtização
- **Data Engineer:** Alinha feature pipelines e dados de treinamento
- **DevOps/SRE:** Provisiona infraestrutura GPU e Kubernetes
- **Backend Developer:** Integra APIs de inferência em produtos
- **Security Engineer:** Garante segurança dos modelos e dados

## Ferramentas do Dia a Dia
- IDE: VS Code, PyCharm
- Containers: Docker, kubectl, k9s
- Experimentos: MLflow, W&B
- Profiling: NVIDIA Nsight, py-spy, cProfile
- Cloud: SageMaker, Vertex AI, Azure ML

## Certificações Relevantes
- AWS Certified Machine Learning – Specialty
- Google Professional Machine Learning Engineer
- NVIDIA Deep Learning Institute Certifications
- Certified Kubernetes Application Developer (CKAD)
- Databricks Certified ML Professional
