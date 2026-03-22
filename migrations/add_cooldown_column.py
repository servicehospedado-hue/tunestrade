"""
Script de migração para adicionar coluna 'cooldown' à tabela autotrade_config
Executar se houver erro: column autotrade_config.cooldown does not exist

Formato do cooldown:
- Fixo: '60' (60 segundos entre trades)
- Intervalo: '60-120' (tempo aleatório entre 60 e 120 segundos)
"""
import asyncio
import os
from sqlalchemy import text, create_engine

async def migrate_add_cooldown_column():
    """Adiciona coluna cooldown à tabela autotrade_config se não existir"""
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/trading_db")
    
    # Converter para URL síncrona para operações DDL
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("🔧 Verificando coluna 'cooldown' na tabela autotrade_config...")
    
    try:
        engine = create_engine(sync_url)
        
        with engine.connect() as conn:
            # Verificar se coluna existe
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'autotrade_config' AND column_name = 'cooldown'
            """))
            
            if result.fetchone():
                print("✅ Coluna 'cooldown' já existe")
                return
            
            # Adicionar coluna
            print("➕ Adicionando coluna 'cooldown'...")
            conn.execute(text("""
                ALTER TABLE autotrade_config 
                ADD COLUMN cooldown VARCHAR(50) NOT NULL DEFAULT '60'
            """))
            conn.commit()
            
            print("✅ Coluna 'cooldown' adicionada com sucesso!")
            print("   Valores aceitos: '60' (fixo) ou '60-120' (intervalo aleatório)")
            
    except Exception as e:
        print(f"❌ Erro na migração: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(migrate_add_cooldown_column())
