"""
Middleware de Autenticação para API
Suporta API Key e JWT
"""
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Callable
import os
import jwt
import secrets
from datetime import datetime, timedelta


class APIAuthMiddleware:
    """
    Middleware de autenticação para a API PocketOption Trading
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        jwt_secret: Optional[str] = None,
        jwt_algorithm: str = "HS256",
        token_expiry_hours: int = 24
    ):
        self.api_key = api_key or os.getenv("API_KEY")
        _secret = os.getenv("JWT_SECRET", "")
        if not _secret or _secret == "your-secret-key-change-in-production":
            import logging
            logging.getLogger("auth").warning(
                "[SECURITY] JWT_SECRET não definido ou inseguro — gerando chave temporária. "
                "Defina JWT_SECRET no .env para produção."
            )
            _secret = secrets.token_hex(32)
        self.jwt_secret = jwt_secret or _secret
        self.jwt_algorithm = jwt_algorithm
        self.token_expiry_hours = token_expiry_hours
        self.security = HTTPBearer(auto_error=False)
        
    def create_jwt_token(self, user_id: str, **claims) -> str:
        """Cria um token JWT para um usuário"""
        payload = {
            "sub": user_id,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=self.token_expiry_hours),
            **claims
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def verify_jwt_token(self, token: str) -> dict:
        """Verifica e decodifica um token JWT"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expirado")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token inválido")
    
    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))
    ) -> dict:
        """
        Verifica autenticação da requisição
        
        Prioridade:
        1. API Key no header X-API-Key
        2. Bearer Token (JWT)
        3. API Key no query param (para WebSocket)
        """
        # Verificar API Key no header
        api_key_header = request.headers.get("X-API-Key")
        if api_key_header:
            if not self.api_key or api_key_header != self.api_key:
                raise HTTPException(status_code=401, detail="API Key inválida")
            return {"type": "api_key", "user_id": "api_user"}
        
        # Verificar Bearer Token (JWT)
        if credentials:
            token = credentials.credentials
            payload = self.verify_jwt_token(token)
            return {"type": "jwt", "user_id": payload.get("sub"), "claims": payload}
        
        # Verificar API Key no query param (para WebSocket)
        api_key_query = request.query_params.get("api_key")
        if api_key_query:
            if not self.api_key or api_key_query != self.api_key:
                raise HTTPException(status_code=401, detail="API Key inválida")
            # Aceitar via query param apenas para WebSocket
            if not request.url.path.startswith("/ws"):
                raise HTTPException(
                    status_code=400,
                    detail="API Key via query param só é permitida em conexões WebSocket"
                )
            return {"type": "api_key", "user_id": "api_user"}
        
        # Se chegou aqui, não há autenticação
        raise HTTPException(
            status_code=401,
            detail="Autenticação necessária. Use header X-API-Key ou Bearer Token",
            headers={"WWW-Authenticate": "Bearer"}
        )


class RateLimitMiddleware:
    """
    Middleware de rate limiting simples
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._requests: dict = {}  # user_id -> list of timestamps
        
    def is_allowed(self, user_id: str) -> bool:
        """Verifica se usuário pode fazer requisição"""
        now = datetime.utcnow()
        
        if user_id not in self._requests:
            self._requests[user_id] = []
        
        # Limpar requisições antigas
        one_minute_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)
        
        user_requests = self._requests[user_id]
        user_requests = [t for t in user_requests if t > one_hour_ago]
        self._requests[user_id] = user_requests
        
        # Verificar limites
        requests_last_minute = sum(1 for t in user_requests if t > one_minute_ago)
        requests_last_hour = len(user_requests)
        
        if requests_last_minute >= self.requests_per_minute:
            return False
        
        if requests_last_hour >= self.requests_per_hour:
            return False
        
        # Registrar requisição
        user_requests.append(now)
        return True
    
    async def __call__(self, request: Request, auth: dict = Depends(APIAuthMiddleware())):
        """Verifica rate limit para a requisição"""
        user_id = auth.get("user_id", "anonymous")
        
        if not self.is_allowed(user_id):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit excedido. Limite: {self.requests_per_minute}/minuto, {self.requests_per_hour}/hora"
            )
        
        return auth


# Instância global opcional
auth_middleware = APIAuthMiddleware()
rate_limit_middleware = RateLimitMiddleware()


class LoginBruteForceGuard:
    """
    Proteção contra brute force no endpoint de login.
    Bloqueia IP após N tentativas falhas em janela de tempo.
    """

    def __init__(self, max_attempts: int = 5, window_minutes: int = 15, lockout_minutes: int = 30):
        self.max_attempts = max_attempts
        self.window = timedelta(minutes=window_minutes)
        self.lockout = timedelta(minutes=lockout_minutes)
        self._attempts: dict = {}  # ip -> list[datetime]
        self._locked: dict = {}    # ip -> datetime (unlock_at)

    def check(self, ip: str) -> None:
        """Lança 429 se IP estiver bloqueado ou exceder tentativas."""
        now = datetime.utcnow()

        # Verificar bloqueio ativo
        if ip in self._locked:
            if now < self._locked[ip]:
                remaining = int((self._locked[ip] - now).total_seconds() // 60) + 1
                raise HTTPException(
                    status_code=429,
                    detail=f"Muitas tentativas de login. Tente novamente em {remaining} minuto(s)."
                )
            else:
                del self._locked[ip]
                self._attempts.pop(ip, None)

        # Limpar tentativas fora da janela
        cutoff = now - self.window
        self._attempts[ip] = [t for t in self._attempts.get(ip, []) if t > cutoff]

    def record_failure(self, ip: str) -> None:
        """Registra tentativa falha e bloqueia se necessário."""
        now = datetime.utcnow()
        self._attempts.setdefault(ip, []).append(now)
        if len(self._attempts[ip]) >= self.max_attempts:
            self._locked[ip] = now + self.lockout

    def record_success(self, ip: str) -> None:
        """Limpa tentativas após login bem-sucedido."""
        self._attempts.pop(ip, None)
        self._locked.pop(ip, None)


login_guard = LoginBruteForceGuard()
