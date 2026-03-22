#!/usr/bin/env python
"""Script para corrigir o operador do usuário para 'demo'"""
import asyncio
from src.database import init_database_manager
from sqlalchemy import select, update
from src.database.models import User

async def fix_operator():
    db_manager = await init_database_manager(
        database_url='postgresql+asyncpg://postgres:postgres@localhost/trading_db',
        admin_url='postgresql://postgres:postgres@localhost',
        db_name='trading_db'
    )
    
    async with db_manager.get_session() as session:
        # Buscar usuário admin
        result = await session.execute(select(User).where(User.email == 'admin@gmail.com'))
        user = result.scalar_one_or_none()
        
        if user:
            print(f'Usuário encontrado: {user.email}')
            print(f'Operador atual: {user.operator}')
            print(f'SSID Demo: {"✅ Configurado" if user.ssid_demo else "❌ Vazio"}')
            print(f'SSID Real: {"✅ Configurado" if user.ssid_real else "❌ Vazio"}')
            
            # Atualizar operador para demo
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(operator='demo')
            )
            await session.commit()
            
            print('\n✅ Operador alterado para "demo"')
            print('Agora o sistema usará o SSID Demo que está configurado!')
        else:
            print('❌ Usuário não encontrado')
    
    await db_manager.stop()

if __name__ == '__main__':
    asyncio.run(fix_operator())
