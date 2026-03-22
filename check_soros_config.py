import asyncio
import asyncpg

async def check_config():
    conn = await asyncpg.connect('postgresql://postgres:root@localhost/trading_db')
    
    row = await conn.fetchrow('''
        SELECT 
            soros_enabled, 
            soros_levels, 
            soros_pct, 
            amount, 
            soros_level, 
            amount_current, 
            consecutive_wins,
            consecutive_losses,
            martingale_enabled,
            reduce_enabled
        FROM autotrade_config 
        WHERE user_id = $1
    ''', '94736c7d-e00e-4df7-826b-cfeb4699f225')
    
    if row:
        print("=" * 60)
        print("CONFIGURAÇÃO DO SOROS")
        print("=" * 60)
        print(f"soros_enabled:      {row['soros_enabled']}")
        print(f"soros_levels:       {row['soros_levels']}")
        print(f"soros_pct:          {row['soros_pct']}%")
        print(f"amount (base):      ${row['amount']}")
        print()
        print("ESTADO ATUAL")
        print("=" * 60)
        print(f"soros_level:        {row['soros_level']}")
        print(f"amount_current:     ${row['amount_current']}")
        print(f"consecutive_wins:   {row['consecutive_wins']}")
        print(f"consecutive_losses: {row['consecutive_losses']}")
        print()
        print("OUTRAS GESTÕES")
        print("=" * 60)
        print(f"martingale_enabled: {row['martingale_enabled']}")
        print(f"reduce_enabled:     {row['reduce_enabled']}")
        print("=" * 60)
    else:
        print("Config não encontrada!")
    
    await conn.close()

asyncio.run(check_config())
