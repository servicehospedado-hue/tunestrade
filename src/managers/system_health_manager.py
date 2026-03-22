"""
SystemHealthManager - Gerenciador de saúde e métricas do sistema
Responsabilidade única: coletar e agregar métricas de todos os componentes
"""
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("system_health")


@dataclass
class ComponentHealth:
    """Estado de saúde de um componente"""
    name: str
    status: str = "unknown"  # healthy, degraded, error, unknown
    last_check: datetime = field(default_factory=datetime.now)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status,
            "last_check": self.last_check.isoformat(),
            "metrics": self.metrics,
            "error_count": self.error_count
        }


class SystemHealthManager:
    """
    Gerenciador de saúde e métricas do sistema.
    
    Responsabilidade única: coletar, agregar e expor métricas de saúde.
    NÃO gerencia componentes (isso é da Engine).
    NÃO executa lógica de negócio.
    
    Features:
    - Coletar métricas de todos os componentes
    - Agregar estatísticas em formato unificado
    - Monitorar saúde do sistema periodicamente
    - Expor métricas para APIs/monitoring
    """
    
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self._running = False
        self._components: Dict[str, Any] = {}
        self._health_status: Dict[str, ComponentHealth] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._start_time = datetime.now()
        
    def register_component(self, name: str, component: Any):
        """Registra um componente para coleta de métricas"""
        self._components[name] = component
        self._health_status[name] = ComponentHealth(name=name)
        logger.info(f"[Health] Componente registrado: {name}")
        
    async def start(self):
        """Inicia o monitoramento de saúde"""
        logger.info("[Health] Iniciando SystemHealthManager...")
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("[Health] SystemHealthManager iniciado")
        
    async def stop(self):
        """Para o monitoramento"""
        logger.info("[Health] Parando SystemHealthManager...")
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("[Health] SystemHealthManager parado")
        
    async def _monitor_loop(self):
        """Loop de monitoramento periódico"""
        while self._running:
            try:
                await self._collect_all_metrics()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"[Health] Erro no monitoramento: {e}")
                await asyncio.sleep(5)  # Espera menor em caso de erro
                
    async def _collect_all_metrics(self):
        """Coleta métricas de todos os componentes"""
        for name, component in self._components.items():
            try:
                health = self._health_status[name]
                health.last_check = datetime.now()
                
                # Coletar métricas do componente
                if hasattr(component, 'get_stats'):
                    stats = component.get_stats()
                    health.metrics = stats
                    health.status = "healthy"
                else:
                    health.status = "unknown"
                    
            except Exception as e:
                logger.error(f"[Health] Erro ao coletar métricas de {name}: {e}")
                health = self._health_status[name]
                health.status = "error"
                health.error_count += 1
        
        # Logar resumo periódico
        status_counts = {"healthy": 0, "degraded": 0, "error": 0, "unknown": 0}
        for health in self._health_status.values():
            status_counts[health.status] = status_counts.get(health.status, 0) + 1
        
        uptime = (datetime.now() - self._start_time).total_seconds()
        logger.info(
            f"[Health] Status: healthy={status_counts['healthy']} | "
            f"degraded={status_counts['degraded']} | error={status_counts['error']} | "
            f"unknown={status_counts['unknown']} | uptime={uptime:.0f}s"
        )
        
        # Logar detalhes de componentes com erro
        for name, health in self._health_status.items():
            if health.status == "error":
                logger.warning(f"[Health] Componente {name} com erro (count: {health.error_count})")
            elif health.status == "degraded":
                logger.warning(f"[Health] Componente {name} degradado")
                
    def get_system_status(self) -> Dict[str, Any]:
        """Retorna status completo do sistema"""
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        # Contar componentes por status
        status_counts = {"healthy": 0, "degraded": 0, "error": 0, "unknown": 0}
        for health in self._health_status.values():
            status_counts[health.status] = status_counts.get(health.status, 0) + 1
            
        # Determinar status geral
        overall_status = "healthy"
        if status_counts["error"] > 0:
            overall_status = "error"
        elif status_counts["degraded"] > 0:
            overall_status = "degraded"
        elif status_counts["unknown"] == len(self._health_status):
            overall_status = "unknown"
            
        return {
            "status": overall_status,
            "uptime_seconds": uptime,
            "components_total": len(self._components),
            "components_healthy": status_counts["healthy"],
            "components_degraded": status_counts["degraded"],
            "components_error": status_counts["error"],
            "components": {name: health.to_dict() for name, health in self._health_status.items()}
        }
        
    def get_full_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas completas de todos os componentes"""
        stats = {"system": self.get_system_status()}
        
        # Adicionar métricas individuais
        for name, component in self._components.items():
            try:
                if hasattr(component, 'get_stats'):
                    stats[name] = component.get_stats()
            except Exception as e:
                logger.warning(f"[Health] Erro ao obter stats de {name}: {e}")
                stats[name] = {"error": str(e)}
                
        return stats
        
    def get_component_health(self, name: str) -> Optional[ComponentHealth]:
        """Retorna saúde de um componente específico"""
        return self._health_status.get(name)
