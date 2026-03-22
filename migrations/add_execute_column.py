"""
Script de migração para adicionar coluna 'execute' à tabela autotrade_config
Executar se houver erro: column autotrade_config.execute does not exist

Formato do execute:
- 'signal': Executa imediatamente ao receber o sinal
- 'oncandle': Aguarda o fechamento da vela atual para executar
"""
import asyncio
import os
from sqlalchemy import text, create_engine

async def migrate_add_execute_column():
    """Adiciona coluna execute à tabela autotrade_config se não existir"""
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/trading_db")
    
    # Converter para URL síncrona para operações DDL
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("🔧 Verificando coluna 'execute' na tabela autotrade_config...")
    
    try:
        engine = create_engine(sync_url)
        
        with engine.connect() as conn:
            # Verificar se coluna existe
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'autotrade_config' AND column_name = 'execute'
            """))
            
            if result.fetchone():
                print("✅ Coluna 'execute' já existe")
                return
            
            # Adicionar coluna
            print("➕ Adicionando coluna 'execute'...")
            conn.execute(text("""
                ALTER TABLE autotrade_config 
                ADD COLUMN execute VARCHAR(20) NOT NULL DEFAULT 'signal'
            """))
            conn.commit()
            
            print("✅ Coluna 'execute' adicionada com sucesso!")
            print("   Valores aceitos: 'signal' (imediato) ou 'oncandle' (próxima vela)")
            
    except Exception as e:
        print(f"❌ Erro na migração: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(migrate_add_execute_column())
