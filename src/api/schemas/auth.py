"""
Schemas Pydantic para autenticação
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class RegisterRequest(BaseModel):
    """Request para registro de usuário"""
    nome: str
    email: EmailStr
    senha: str


class LoginRequest(BaseModel):
    """Request para login"""
    email: EmailStr
    senha: str


class AuthResponse(BaseModel):
    """Response de autenticação"""
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[dict] = None


class UserResponse(BaseModel):
    """Dados do usuário"""
    id: str
    nome: str
    email: str
    role: str
    operator: str
    vip: str = "free"
    vip_data_active: Optional[datetime] = None
    data_criacao: datetime
    ssid_demo: Optional[str] = ""
    ssid_real: Optional[str] = ""


class SaveSSIDRequest(BaseModel):
    """Request para salvar SSID"""
    ssid: str
    account_type: str  # 'demo' ou 'real'


class SaveSSIDResponse(BaseModel):
    """Response de salvamento de SSID"""
    success: bool
    message: str


class SSIDResponse(BaseModel):
    """Response com SSIDs salvos"""
    ssid_demo: Optional[str] = ""
    ssid_real: Optional[str] = ""
    success: bool = True
