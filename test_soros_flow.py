"""
Simulação do fluxo Soros nível 3 com payout 92%
"""

def simulate_soros():
    # Configuração
    base_amount = 1.00
    soros_levels = 3
    soros_pct = 1.0  # 100%
    payout = 0.92  # 92%
    
    # Estado inicial
    soros_level = 0
    amount_current = base_amount
    consecutive_wins = 0
    
    print("=" * 80)
    print("SIMULAÇÃO SOROS - NÍVEL 3 COM PAYOUT 92%")
    print("=" * 80)
    print(f"Config: base=${base_amount}, levels={soros_levels}, pct={soros_pct*100}%")
    print("=" * 80)
    print()
    
    # Simular 5 wins consecutivos
    for trade_num in range(1, 6):
        print(f"TRADE {trade_num}:")
        print(f"  Estado antes: soros_level={soros_level}, amount_current=${amount_current:.2f}")
        
        # Executar trade
        trade_amount = amount_current if soros_level > 0 else base_amount
        print(f"  Executando: ${trade_amount:.2f}")
        
        # Resultado: WIN
        profit = trade_amount * payout
        print(f"  Resultado: WIN | Profit: ${profit:.2f}")
        
        # Processar resultado
        consecutive_wins += 1
        
        # Aplicar Soros
        soros_level += 1
        print(f"  Soros: nível {soros_level-1} → {soros_level}")
        
        if soros_level <= soros_levels:
            # Dentro do limite
            old_amount = amount_current
            amount_current = round(amount_current + abs(profit) * soros_pct, 2)
            print(f"  Cálculo: ${old_amount:.2f} + (${abs(profit):.2f} * {soros_pct*100}%) = ${amount_current:.2f}")
            print(f"  ✓ Nível {soros_level}/{soros_levels} - Próximo trade: ${amount_current:.2f}")
        else:
            # Ultrapassou limite
            print(f"  ⚠ Ultrapassou nível máximo ({soros_levels})")
            soros_level = 0
            amount_current = base_amount
            print(f"  ✓ Reset ao base: ${base_amount:.2f}")
        
        print(f"  Estado depois: soros_level={soros_level}, amount_current=${amount_current:.2f}, wins={consecutive_wins}")
        print()
    
    print("=" * 80)
    print("RESUMO DA PROGRESSÃO")
    print("=" * 80)
    print("Trade 1: $1.00 → WIN (+$0.92) → Nível 1 → Próximo: $1.92")
    print("Trade 2: $1.92 → WIN (+$1.77) → Nível 2 → Próximo: $3.69")
    print("Trade 3: $3.69 → WIN (+$3.39) → Nível 3 → Próximo: $7.08")
    print("Trade 4: $7.08 → WIN (+$6.51) → Ultrapassou → Reset: $1.00")
    print("Trade 5: $1.00 → WIN (+$0.92) → Nível 1 → Próximo: $1.92")
    print("=" * 80)
    print()
    
    # Calcular lucro total
    total_profit = (
        (1.00 * 0.92) +   # Trade 1
        (1.92 * 0.92) +   # Trade 2
        (3.69 * 0.92) +   # Trade 3
        (7.08 * 0.92) +   # Trade 4
        (1.00 * 0.92)     # Trade 5
    )
    total_invested = 1.00 + 1.92 + 3.69 + 7.08 + 1.00
    
    print("ANÁLISE FINANCEIRA")
    print("=" * 80)
    print(f"Total investido: ${total_invested:.2f}")
    print(f"Total lucro:     ${total_profit:.2f}")
    print(f"ROI:             {(total_profit/total_invested)*100:.1f}%")
    print("=" * 80)

if __name__ == "__main__":
    simulate_soros()
