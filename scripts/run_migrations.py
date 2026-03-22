"""
Script para executar todas as migrações pendentes
"""
import asyncio
import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from migrations.add_role_column import migrate_add_role_column
from migrations.add_cooldown_column import migrate_add_cooldown_column
from migrations.add_execute_column import migrate_add_execute_column

async def run_all_migrations():
    """Executa todas as migrações em ordem"""
    print("=" * 60)
    print("🚀 Iniciando migrações do banco de dados")
    print("=" * 60)
    
    migrations = [
        ("role", migrate_add_role_column),
        ("cooldown", migrate_add_cooldown_column),
        ("execute", migrate_add_execute_column),
    ]
    
    for name, migration_func in migrations:
        try:
            print(f"\n📦 Executando migração: {name}")
            await migration_func()
        except Exception as e:
            print(f"❌ Erro na migração {name}: {e}")
            return False
    
    print("\n" + "=" * 60)
    print("✅ Todas as migrações foram executadas com sucesso!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = asyncio.run(run_all_migrations())
    sys.exit(0 if success else 1)
