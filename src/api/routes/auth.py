"""
Rotas de Autenticação - Login, registro e gerenciamento de usuário
Refatorado para usar camada de serviço
"""
from fastapi import APIRouter, HTTPException, Depends, Request

from ..auth import APIAuthMiddleware, login_guard
from ..schemas import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserResponse,
    SaveSSIDRequest,
    SaveSSIDResponse,
    SSIDResponse
)
from ..services.auth_service import auth_service, set_user_manager
from ...managers.log_manager import get_manager_logger

logger = get_manager_logger("auth_routes_new")
router = APIRouter(prefix="/auth", tags=["auth"])

auth_middleware = APIAuthMiddleware()


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """
    Cadastra um novo usuário no sistema.
    """
    # Validação de força de senha
    senha = request.senha
    if len(senha) < 8:
        raise HTTPException(status_code=400, detail="Senha deve ter no mínimo 8 caracteres")
    if not any(c.isupper() for c in senha):
        raise HTTPException(status_code=400, detail="Senha deve conter ao menos uma letra maiúscula")
    if not any(c.isdigit() for c in senha):
        raise HTTPException(status_code=400, detail="Senha deve conter ao menos um número")

    success, user_data, error = await auth_service.register_user(
        nome=request.nome,
        email=request.email,
        senha=request.senha
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    # Gerar token JWT
    token = auth_service.create_jwt_token(
        user_id=user_data["id"],
        email=user_data["email"],
        role=user_data["role"]
    )
    
    from ..services.auth_service import _get_db_manager
    is_local = _get_db_manager() is None
    logger.info(f"Novo usuário cadastrado: {request.email} (local={is_local})")
    
    return AuthResponse(
        success=True,
        message=f"Usuário cadastrado com sucesso {'(modo local)' if is_local else ''}",
        token=token,
        user=user_data
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, http_request: Request):
    """
    Realiza login do usuário e retorna token JWT.
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    login_guard.check(client_ip)

    try:
        success, user_data, error = await auth_service.authenticate_user(
            email=request.email,
            senha=request.senha
        )
        
        if not success:
            login_guard.record_failure(client_ip)
            raise HTTPException(status_code=401, detail=error)

        login_guard.record_success(client_ip)
        
        # Gerar token JWT
        token = auth_service.create_jwt_token(
            user_id=user_data["id"],
            email=user_data["email"],
            role=user_data["role"]
        )
        
        # Notificar UserManager sobre login
        from ..services.auth_service import _user_manager, _get_db_manager
        if _user_manager:
            is_local = _get_db_manager() is None
            await _user_manager.on_user_login(
                user_data["id"], 
                user_data["email"], 
                is_local=is_local
            )
        
        logger.info(f"[AUTH] Usuário logado: {request.email}")
        logger.info(f"[AUDIT] LOGIN_SUCCESS user={user_data['id']} email={request.email} ip={client_ip}")
        
        return AuthResponse(
            success=True,
            message="Login realizado com sucesso",
            token=token,
            user=user_data
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Erro no login: {e}", exc_info=True)
        login_guard.record_failure(client_ip)
        raise HTTPException(status_code=500, detail="Erro interno no servidor")


@router.get("/me", response_model=UserResponse)
async def get_current_user(auth: dict = Depends(auth_middleware)):
    """
    Retorna dados do usuário logado.
    """
    user_id = auth.get("user_id")
    
    success, user_data, error = await auth_service.get_user_by_id(user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=error)
    
    return UserResponse(**user_data)


@router.post("/save-ssid", response_model=SaveSSIDResponse)
async def save_ssid(
    request: SaveSSIDRequest,
    auth: dict = Depends(auth_middleware)
):
    """
    Salva o SSID da PocketOption para o usuário logado.
    """
    user_id = auth.get("user_id")
    
    if request.account_type not in ['demo', 'real']:
        raise HTTPException(
            status_code=400,
            detail="Tipo de conta deve ser 'demo' ou 'real'"
        )
    
    success, message = await auth_service.save_ssid(
        user_id=user_id,
        ssid=request.ssid,
        account_type=request.account_type
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=message)
    
    logger.info(f"[AUDIT] SAVE_SSID user={user_id} account_type={request.account_type}")
    return SaveSSIDResponse(success=True, message=message)


@router.get("/ssid", response_model=SSIDResponse)
async def get_ssid(auth: dict = Depends(auth_middleware)):
    """
    Retorna os SSIDs salvos do usuário logado.
    """
    user_id = auth.get("user_id")
    
    success, data, error = await auth_service.get_ssid(user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=error)
    
    return SSIDResponse(**data)


@router.put("/operator")
async def update_operator(
    request: dict,
    auth: dict = Depends(auth_middleware)
):
    """
    Atualiza o tipo de conta (operator) do usuário: 'demo' ou 'real'.
    """
    try:
        user_id = auth.get("user_id")
        operator = request.get("operator")
        
        if operator not in ['demo', 'real']:
            raise HTTPException(status_code=400, detail="Operator deve ser 'demo' ou 'real'")
        
        success, data, error = await auth_service.update_operator(user_id, operator)
        
        if not success:
            logger.error(f"[OPERATOR] Erro ao atualizar: {error}")
            raise HTTPException(status_code=500, detail=error or "Erro ao atualizar operator")
        
        logger.info(f"[OPERATOR] Atualizado com sucesso: {user_id} -> {operator}")
        logger.info(f"[AUDIT] OPERATOR_CHANGE user={user_id} operator={operator}")
        return {
            "success": True,
            "operator": data["operator"],
            "message": f"Conta alterada para {operator.upper()} com sucesso"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OPERATOR] Erro inesperado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
