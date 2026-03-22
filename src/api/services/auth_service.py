"""
Serviço de Autenticação - Lógica de negócio separada das rotas
"""
import os
import json
import bcrypt
import uuid as uuid_module
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Tuple
from sqlalchemy import select

from ...database.models import User, AutotradeConfig
from ...database import database_manager as _db_module
from ...api.auth import APIAuthMiddleware
from ...managers.log_manager import get_manager_logger
from decimal import Decimal

logger = get_manager_logger("auth_service")

# Configurações
_local_users: Dict[str, dict] = {}
_fallback_enabled = os.getenv("AUTH_FALLBACK_LOCAL", "true").lower() == "true"
_user_manager = None


def _get_local_storage_path():
    """Retorna caminho para armazenamento local de usuários"""
    from pathlib import Path
    data_dir = Path(__file__).parent.parent.parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "local_users.json"


def _save_local_users():
    """Salva usuários locais em arquivo JSON"""
    try:
        path = _get_local_storage_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_local_users, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Não foi possível salvar usuários locais: {e}")


def _load_local_users():
    """Carrega usuários locais do arquivo JSON"""
    global _local_users
    try:
        path = _get_local_storage_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                _local_users = json.load(f)
    except Exception as e:
        logger.warning(f"Não foi possível carregar usuários locais: {e}")
        _local_users = {}


def _hash_password(password: str) -> str:
    """Gera hash seguro da senha usando bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def _verify_password(password: str, hashed: str) -> bool:
    """Verifica se a senha corresponde ao hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def _get_db_manager():
    """Retorna o db_manager atual do módulo database_manager"""
    return _db_module.db_manager


def set_user_manager(user_manager):
    """Define o UserManager para notificar sobre logins"""
    global _user_manager
    _user_manager = user_manager
    logger.info("[AUTH] UserManager configurado")


# Carregar usuários locais ao iniciar o módulo
_load_local_users()

# Criar usuário admin padrão se necessário
if _fallback_enabled and "admin@gmail.com" not in _local_users:
    admin_password_hash = _hash_password("leandro1228")
    admin_id = str(uuid_module.uuid4())
    _local_users["admin@gmail.com"] = {
        "id": admin_id,
        "nome": "Administrador",
        "email": "admin@gmail.com",
        "senha": admin_password_hash,
        "role": "admin",
        "operator": "demo",
        "data_criacao": datetime.utcnow().isoformat(),
        "ultima_vez_ativo": datetime.utcnow().isoformat()
    }
    _save_local_users()
    logger.info("[OK] Usuário admin padrão criado (admin@gmail.com / leandro1228)")


class AuthService:
    """Serviço de autenticação e gerenciamento de usuários"""
    
    @staticmethod
    async def register_user(nome: str, email: str, senha: str) -> Tuple[bool, dict, Optional[str]]:
        """
        Registra um novo usuário
        Returns: (success, user_data, error_message)
        """
        db = _get_db_manager()
        
        # Fallback local
        if db is None:
            if email in _local_users:
                return False, {}, "Email já cadastrado"
            
            password_hash = _hash_password(senha)
            user_id = str(uuid_module.uuid4())
            
            _local_users[email] = {
                "id": user_id,
                "nome": nome,
                "email": email,
                "senha": password_hash,
                "role": "user",
                "operator": "demo",
                "data_criacao": datetime.utcnow().isoformat(),
                "ultima_vez_ativo": datetime.utcnow().isoformat()
            }
            _save_local_users()
            
            logger.info(f"Novo usuário cadastrado (local): {email}")
            return True, {
                "id": user_id,
                "nome": nome,
                "email": email,
                "role": "user"
            }, None
        
        # PostgreSQL
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            if result.scalars().first():
                return False, {}, "Email já cadastrado"
            
            password_hash = _hash_password(senha)
            new_user = User(
                nome=nome,
                email=email,
                senha=password_hash,
                role="user",
                operator="demo"
            )
            session.add(new_user)
            await session.flush()
            
            logger.info(f"Novo usuário cadastrado: {email}")
            return True, {
                "id": str(new_user.id),
                "nome": new_user.nome,
                "email": new_user.email,
                "role": new_user.role
            }, None
    
    @staticmethod
    async def authenticate_user(email: str, senha: str) -> Tuple[bool, dict, Optional[str]]:
        """
        Autentica um usuário
        Returns: (success, user_data, error_message)
        """
        db = _get_db_manager()
        
        # Fallback local
        if db is None:
            user = _local_users.get(email)
            if not user or not _verify_password(senha, user["senha"]):
                return False, {}, "Email ou senha incorretos"
            
            # Atualizar última vez ativo
            user["ultima_vez_ativo"] = datetime.utcnow().isoformat()
            _save_local_users()
            
            # Tentar sincronizar para PostgreSQL se disponível
            await AuthService._sync_local_to_postgres(user)
            
            return True, {
                "id": user["id"],
                "nome": user["nome"],
                "email": user["email"],
                "role": user["role"]
            }, None
        
        # PostgreSQL
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalars().first()
            
            if not user or not _verify_password(senha, user.senha):
                return False, {}, "Email ou senha incorretos"
            
            user.ultima_vez_ativo = datetime.utcnow()
            
            return True, {
                "id": str(user.id),
                "nome": user.nome,
                "email": user.email,
                "role": user.role
            }, None
    
    @staticmethod
    async def _sync_local_to_postgres(user: dict) -> None:
        """Sincroniza usuário local para PostgreSQL se disponível"""
        try:
            db_manager = _get_db_manager()
            if db_manager is None:
                return
            
            logger.info(f"[SYNC] Sincronizando usuário {user['email']} para PostgreSQL...")
            
            async with db_manager.get_session() as session:
                result = await session.execute(
                    select(User).where(User.id == UUID(user["id"]))
                )
                existing = result.scalars().first()
                
                if existing:
                    logger.info(f"[SYNC] Usuário já existe no PostgreSQL: {user['email']}")
                    await AuthService._ensure_autotrade_config(session, user["id"])
                    return
                
                # Criar usuário no PostgreSQL
                new_user = User(
                    id=UUID(user["id"]),
                    nome=user["nome"],
                    email=user["email"],
                    senha=user["senha"],
                    role=user.get("role", "user"),
                    operator=user.get("operator", "demo"),
                    data_criacao=datetime.fromisoformat(user["data_criacao"]) 
                        if isinstance(user["data_criacao"], str) else datetime.utcnow()
                )
                session.add(new_user)
                await session.commit()
                
                logger.info(f"[SYNC] Usuário sincronizado: {user['email']}")
                
                # Criar autotrade_config
                await AuthService._ensure_autotrade_config(session, user["id"])
                
        except Exception as e:
            logger.error(f"[SYNC] Falha ao sincronizar: {e}")
    
    @staticmethod
    async def _ensure_autotrade_config(session, user_id: str) -> None:
        """Garante que o usuário tenha uma configuração de autotrade"""
        try:
            result = await session.execute(
                select(AutotradeConfig).where(AutotradeConfig.user_id == UUID(user_id))
            )
            if not result.scalars().first():
                config = AutotradeConfig(
                    user_id=UUID(user_id),
                    autotrade=0,
                    amount=Decimal("1.00"),
                    strategy_name="Scalping5s",
                    cooldown="60"
                )
                session.add(config)
                await session.commit()
                logger.info(f"[SYNC] AutotradeConfig criada para user {user_id}")
        except Exception as e:
            logger.warning(f"[SYNC] Falha ao criar autotrade_config: {e}")
    
    @staticmethod
    def create_jwt_token(user_id: str, email: str, role: str) -> str:
        """Cria token JWT para o usuário"""
        auth_middleware = APIAuthMiddleware()
        return auth_middleware.create_jwt_token(
            user_id=user_id,
            email=email,
            role=role
        )
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Tuple[bool, dict, Optional[str]]:
        """Busca usuário por ID"""
        db = _get_db_manager()
        
        if db is None:
            # Buscar em usuários locais
            for email, user in _local_users.items():
                if user["id"] == user_id:
                    return True, {
                        "id": user["id"],
                        "nome": user["nome"],
                        "email": user["email"],
                        "role": user["role"],
                        "operator": user.get("operator", "demo"),
                        "vip": user.get("vip", "free"),
                        "vip_data_active": user.get("vip_data_active", None),
                        "data_criacao": user["data_criacao"],
                        "ssid_demo": user.get("ssid_demo", ""),
                        "ssid_real": user.get("ssid_real", ""),
                    }, None
            return False, {}, "Usuário não encontrado"
        
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalars().first()
            
            if not user:
                return False, {}, "Usuário não encontrado"
            
            return True, {
                "id": str(user.id),
                "nome": user.nome,
                "email": user.email,
                "role": user.role,
                "operator": user.operator,
                "vip": user.vip if hasattr(user, 'vip') else "free",
                "vip_data_active": user.vip_data_active if hasattr(user, 'vip_data_active') else None,
                "data_criacao": user.data_criacao,
                "ssid_demo": user.ssid_demo or "",
                "ssid_real": user.ssid_real or "",
            }, None
    
    @staticmethod
    async def save_ssid(user_id: str, ssid: str, account_type: str) -> Tuple[bool, str]:
        """Salva SSID do usuário"""
        db = _get_db_manager()
        
        if db is None:
            # Salvar localmente
            for email, user in _local_users.items():
                if user["id"] == user_id:
                    user[f"ssid_{account_type}"] = ssid
                    _save_local_users()
                    return True, f"SSID {account_type} salvo com sucesso (modo local)"
            return False, "Usuário não encontrado"
        
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalars().first()
            
            if not user:
                return False, "Usuário não encontrado"
            
            if account_type == "demo":
                user.ssid_demo = ssid
            else:
                user.ssid_real = ssid
            
            await session.commit()
            return True, f"SSID {account_type} salvo com sucesso"
    
    @staticmethod
    async def get_ssid(user_id: str) -> Tuple[bool, dict, str]:
        """Obtém SSIDs salvos do usuário"""
        db = _get_db_manager()
        
        if db is None:
            for email, user in _local_users.items():
                if user["id"] == user_id:
                    return True, {
                        "ssid_demo": user.get("ssid_demo", ""),
                        "ssid_real": user.get("ssid_real", "")
                    }, ""
            return False, {}, "Usuário não encontrado"
        
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalars().first()
            
            if not user:
                return False, {}, "Usuário não encontrado"
            
            return True, {
                "ssid_demo": user.ssid_demo or "",
                "ssid_real": user.ssid_real or ""
            }, ""
    
    @staticmethod
    async def update_operator(user_id: str, operator: str) -> Tuple[bool, dict, Optional[str]]:
        """
        Atualiza o tipo de conta (operator) do usuário
        Returns: (success, data, error_message)
        """
        try:
            logger.info(f"[UPDATE_OPERATOR] Iniciando para user_id={user_id}, operator={operator}")
            db = _get_db_manager()
            
            # Fallback local
            if db is None:
                logger.info(f"[UPDATE_OPERATOR] Usando modo local")
                for email, user in _local_users.items():
                    if user["id"] == user_id:
                        user["operator"] = operator
                        _save_local_users()
                        logger.info(f"[UPDATE_OPERATOR] Operator atualizado (local): {user_id} -> {operator}")
                        return True, {"operator": operator}, None
                logger.error(f"[UPDATE_OPERATOR] Usuário não encontrado (local): {user_id}")
                return False, {}, "Usuário não encontrado"
            
            # PostgreSQL
            logger.info(f"[UPDATE_OPERATOR] Usando PostgreSQL")
            async with db.get_session() as session:
                # Converter user_id para UUID se for string
                user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
                
                result = await session.execute(
                    select(User).where(User.id == user_uuid)
                )
                user = result.scalars().first()
                
                if not user:
                    logger.error(f"[UPDATE_OPERATOR] Usuário não encontrado no banco: {user_id}")
                    return False, {}, "Usuário não encontrado"
                
                # Atualizar operator
                logger.info(f"[UPDATE_OPERATOR] Atualizando de {user.operator} para {operator}")
                user.operator = operator
                await session.commit()
                
                logger.info(f"[UPDATE_OPERATOR] Operator atualizado com sucesso: {user_id} -> {operator}")
                return True, {"operator": operator}, None
                
        except Exception as e:
            logger.error(f"[UPDATE_OPERATOR] Erro: {e}", exc_info=True)
            return False, {}, str(e)


# Instância singleton
auth_service = AuthService()
