#!/usr/bin/env python
"""Script para verificar SSID do usuário no banco de dados"""
import asyncio
from src.database import init_database_manager
from sqlalchemy import select
from src.database.models import User

async def check_ssid():
    db_manager = await init_database_manager(
        database_url='postgresql+asyncpg://postgres:postgres@localhost/trading_db',
        admin_url='postgresql://postgres:postgres@localhost',
        db_name='trading_db'
    )
    
    async with db_manager.get_session() as session:
        result = await session.execute(select(User).where(User.email == 'admin@gmail.com'))
        user = result.scalar_one_or_none()
        if user:
            print(f'User ID: {user.id}')
            print(f'SSID Demo: {user.ssid_demo[:50] if user.ssid_demo else "VAZIO"}...')
            print(f'SSID Real: {user.ssid_real[:50] if user.ssid_real else "VAZIO"}...')
            print(f'Operator: {user.operator}')
            
            # Verificar se está vazio
            if not user.ssid_demo or user.ssid_demo.strip() == '':
                print('\n❌ SSID Demo está vazio!')
            else:
                print('\n✅ SSID Demo está configurado')
                
            if not user.ssid_real or user.ssid_real.strip() == '':
                print('❌ SSID Real está vazio!')
            else:
                print('✅ SSID Real está configurado')
        else:
            print('Usuário não encontrado')
    
    await db_manager.stop()

if __name__ == '__main__':
    asyncio.run(check_ssid())
