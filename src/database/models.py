"""
Modelos ORM SQLAlchemy para o banco de dados
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text, SmallInteger, Numeric, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Tabela de usuários do sistema"""
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="ID único do usuário"
    )
    nome = Column(
        String(255),
        nullable=False,
        comment="Nome do usuário"
    )
    email = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Email do usuário"
    )
    senha = Column(
        String(255),
        nullable=False,
        comment="Senha do usuário (hash)"
    )
    ssid_demo = Column(
        Text,
        nullable=True,
        default="",
        comment="SSID da conta demo PocketOption"
    )
    ssid_real = Column(
        Text,
        nullable=True,
        default="",
        comment="SSID da conta real PocketOption"
    )
    operator = Column(
        String(10),
        nullable=False,
        default="demo",
        comment="Tipo de operação: 'demo' ou 'real'"
    )
    role = Column(
        String(20),
        nullable=False,
        default="user",
        comment="Cargo do usuário: 'user' ou 'admin'"
    )
    vip = Column(
        String(10),
        nullable=False,
        default="free",
        comment="Plano VIP do usuário: 'free', 'semanal' ou 'mensal'"
    )
    vip_data_active = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Data de ativação do plano VIP"
    )
    ultima_vez_ativo = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Última vez que o usuário esteve ativo"
    )
    data_criacao = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        comment="Data de criação do registro"
    )
    
    # Relacionamento com autotrade_config
    autotrade_config = relationship("AutotradeConfig", back_populates="user", uselist=False)
    # Relacionamento com estratégias pessoais
    strategies = relationship("UserStrategy", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, nome='{self.nome}', email='{self.email}', role='{self.role}', operator='{self.operator}')>"


class AutotradeConfig(Base):
    """
    Configuração de auto-trade para usuários.
    Controla se o sistema deve executar trades automaticamente para o usuário.
    """
    __tablename__ = "autotrade_config"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="ID único da configuração"
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="ID do usuário (chave estrangeira)"
    )
    autotrade = Column(SmallInteger, nullable=False, default=0, comment="1 = ligado, 0 = desligado")
    amount = Column(Numeric(10, 2), nullable=False, default=1.00, comment="Valor base da operação em USD")
    strategy_name = Column(String(100), nullable=False, default="Scalping5s", comment="Nome da estratégia selecionada")
    cooldown = Column(String(50), nullable=False, default="60", comment="Cooldown entre trades: '60' ou '60-120'")
    execute = Column(String(20), nullable=False, default="signal", comment="Modo: 'signal' ou 'oncandle'")

    # ── Stop Loss / Stop Gain ──────────────────────────────────────────────
    stop_loss_enabled = Column(Boolean, nullable=False, default=False)
    stop_loss_value = Column(Numeric(10, 2), nullable=True, default=None)
    stop_gain_enabled = Column(Boolean, nullable=False, default=False)
    stop_gain_value = Column(Numeric(10, 2), nullable=True, default=None)
    stop_soft_mode = Column(Boolean, nullable=False, default=False, comment="Modo alerta: notifica mas não para")

    # ── Stop por Sequência ────────────────────────────────────────────────
    stop_win_seq_enabled = Column(Boolean, nullable=False, default=False)
    stop_win_seq = Column(Integer, nullable=True, default=None)
    stop_loss_seq_enabled = Column(Boolean, nullable=False, default=False)
    stop_loss_seq = Column(Integer, nullable=True, default=None)
    stop_seq_soft_mode = Column(Boolean, nullable=False, default=False)

    # ── Stop Médio (drawdown do pico) ─────────────────────────────────────
    stop_medium_enabled = Column(Boolean, nullable=False, default=False)
    stop_medium_pct = Column(Numeric(5, 2), nullable=True, default=50.00)
    stop_medium_soft_mode = Column(Boolean, nullable=False, default=False)

    # ── Redução Inteligente ───────────────────────────────────────────────
    reduce_enabled = Column(Boolean, nullable=False, default=False)
    reduce_loss_trigger = Column(Integer, nullable=True, default=3)
    reduce_win_exit = Column(Integer, nullable=True, default=2)
    reduce_pct = Column(Numeric(5, 2), nullable=True, default=50.00)

    # ── Martingale ────────────────────────────────────────────────────────
    martingale_enabled = Column(Boolean, nullable=False, default=False)
    martingale_levels = Column(Integer, nullable=True, default=3)
    martingale_multiplier = Column(Numeric(5, 2), nullable=True, default=2.00)

    # ── Soros ─────────────────────────────────────────────────────────────
    soros_enabled = Column(Boolean, nullable=False, default=False)
    soros_levels = Column(Integer, nullable=True, default=3)
    soros_pct = Column(Numeric(5, 2), nullable=True, default=100.00)

    # ── Estado de Sessão (consolidado) ────────────────────────────────────
    amount_current = Column(Numeric(10, 2), nullable=False, default=1.00, comment="Valor atual da operação (pode diferir do base por martingale/soros/reduce)")
    consecutive_wins = Column(Integer, nullable=False, default=0, comment="Wins consecutivos atuais")
    consecutive_losses = Column(Integer, nullable=False, default=0, comment="Losses consecutivos atuais")
    martingale_level = Column(Integer, nullable=False, default=0, comment="Nível atual do martingale (0 = base)")
    soros_level = Column(Integer, nullable=False, default=0, comment="Nível atual do soros (0 = base)")
    reduce_active = Column(Boolean, nullable=False, default=False, comment="Redução inteligente ativa no momento")
    reduce_level = Column(Integer, nullable=False, default=0, comment="Quantas vezes reduziu nesta sessão")
    session_peak_balance = Column(Numeric(12, 2), nullable=True, default=None, comment="Maior saldo atingido na sessão (para stop médio)")
    session_profit = Column(Numeric(12, 2), nullable=False, default=0.00, comment="Lucro/perda acumulado na sessão")
    session_trades = Column(Integer, nullable=False, default=0, comment="Total de trades na sessão")
    stop_triggered = Column(Boolean, nullable=False, default=False, comment="Algum stop foi atingido nesta sessão")
    stop_type = Column(String(50), nullable=True, default=None, comment="Tipo do stop atingido: loss/gain/seq_win/seq_loss/medium")

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relacionamento com User
    user = relationship("User", back_populates="autotrade_config")

    def __repr__(self):
        return f"<AutotradeConfig(user_id={self.user_id}, autotrade={self.autotrade}, amount={self.amount}, strategy='{self.strategy_name}')>"




class AccountMonitoring(Base):
    """
    Contas do sistema para monitoramento da corretora.
    Cada registro é uma conta client usada para extrair dados (payout, ativos, etc.)
    """
    __tablename__ = "accounts_monitoring"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="ID único da conta de monitoramento"
    )
    name = Column(
        String(50),
        nullable=False,
        unique=True,
        comment="Nome da conta: 'payout' ou 'actives'"
    )
    ssid_system_demo = Column(
        Text,
        nullable=False,
        comment="SSID da conta demo do sistema"
    )
    active = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="1 = ativo, 0 = inativo"
    )

    def __repr__(self):
        return f"<AccountMonitoring(id={self.id}, name='{self.name}', active={self.active})>"


class UserStrategy(Base):
    """
    Estratégias personalizadas criadas pelos usuários.
    Cada estratégia pertence a um usuário e contém indicadores com parâmetros.
    """
    __tablename__ = "user_strategies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="ID único da estratégia"
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID do usuário dono da estratégia"
    )
    name = Column(
        String(100),
        nullable=False,
        comment="Nome da estratégia"
    )
    description = Column(
        Text,
        nullable=True,
        default="",
        comment="Descrição da estratégia"
    )
    # Lista de indicadores com parâmetros: [{"id": "rsi", "name": "RSI", "parameters": {...}, "sliderParams": [...]}]
    indicators = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Indicadores e parâmetros da estratégia"
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Se esta estratégia está ativa no autotrade"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relacionamento com User
    user = relationship("User", back_populates="strategies")

    def __repr__(self):
        return f"<UserStrategy(id={self.id}, user_id={self.user_id}, name='{self.name}', active={self.is_active})>"


# ==================== DADOS PADRÃO ====================

DEFAULT_ACCOUNTS_MONITORING = [
    {
        "name": "payout",
        "ssid_system_demo": '42["auth",{"session":"okh3oc5r8gp2ghn5ddsg82ofkr","isDemo":1,"uid":127006150,"platform":2,"isFastHistory":true,"isOptimized":true}]',
        "active": 1,
    },
    {
        "name": "actives",
        "ssid_system_demo": '42["auth",{"session":"b05sj8d0n8callv1i7e4l9mf79","isDemo":1,"uid":127107215,"platform":2,"isFastHistory":true,"isOptimized":true}]',
        "active": 1,
    },
]

