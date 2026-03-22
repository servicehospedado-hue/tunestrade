"""
Script de migração para adicionar coluna 'role' à tabela users
Executar se houver erro: column users.role does not exist
"""
import asyncio
import os
from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine

async def migrate_add_role_column():
    """Adiciona coluna role à tabela users se não existir"""
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/trading_db")
    
    # Converter para URL síncrona para operações DDL
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("🔧 Verificando coluna 'role' na tabela users...")
    
    try:
        engine = create_engine(sync_url)
        
        with engine.connect() as conn:
            # Verificar se coluna existe
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'role'
            """))
            
            if result.fetchone():
                print("✅ Coluna 'role' já existe")
                return
            
            # Adicionar coluna
            print("➕ Adicionando coluna 'role'...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'
            """))
            conn.commit()
            
            print("✅ Coluna 'role' adicionada com sucesso!")
            
    except Exception as e:
        print(f"❌ Erro na migração: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(migrate_add_role_column())
