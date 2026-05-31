# file: backend/app/ai/backtester.py
import csv
from typing import Callable, List, Dict, Any

class BacktestResult:
    def __init__(self):
        self.trades: List[Dict[str, Any]] = []
        self.final_pnl: float = 0.0
        self.max_drawdown: float = 0.0
        self.win_rate: float = 0.0
        self.total_trades: int = 0

    def print_summary(self):
        print("=== Backtest Summary ===")
        print(f"Total Trades: {self.total_trades}")
        print(f"Win Rate:     {self.win_rate:.2%}")
        print(f"Final PnL:    ${self.final_pnl:.2f}")
        print(f"Max Drawdown: ${self.max_drawdown:.2f}")
        print("========================")


def run_backtest(csv_path: str, strategy_fn: Callable) -> BacktestResult:
    """
    Runs a backtest on historical spread data.
    
    strategy_fn: A function that takes (current_row, state) and returns an action.
                 Action can be: 'ENTER_LONG', 'ENTER_SHORT', 'EXIT', or None.
    """
    result = BacktestResult()
    
    position = 0  # 1 for Long Spread, -1 for Short Spread, 0 for Flat
    entry_price = 0.0
    current_pnl = 0.0
    peak_pnl = 0.0
    max_dd = 0.0
    wins = 0

    state = {} # Strategy can store arbitrary state here (e.g. rolling windows)

    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                for k in row:
                    try:
                        row[k] = float(row[k])
                    except ValueError:
                        pass
                
                # The strategy function returns an action based on the row and state
                action = strategy_fn(row, state)

                current_spread = row.get('exchange_spread_mid', 0)

                # Execute Action
                if action == 'ENTER_LONG' and position == 0:
                    position = 1
                    entry_price = current_spread
                    # In a real scenario, we'd account for bid/ask crossing (slippage)
                elif action == 'ENTER_SHORT' and position == 0:
                    position = -1
                    entry_price = current_spread
                elif action == 'EXIT' and position != 0:
                    # Calculate PnL for this trade (simplified)
                    # For Long Spread: we profit if spread widens (Wait, actually long spread means we buy the lower and sell the higher, so we profit if they converge? It depends on definition).
                    # Let's assume positive PnL if we guess the direction correctly.
                    # This is just a structural placeholder.
                    price_diff = current_spread - entry_price
                    trade_pnl = price_diff if position == 1 else -price_diff
                    
                    # Assume $100 notional for simplicity
                    trade_pnl_usd = trade_pnl * 100 / 10000 # Just a dummy scalar
                    
                    current_pnl += trade_pnl_usd
                    result.total_trades += 1
                    if trade_pnl_usd > 0:
                        wins += 1

                    result.trades.append({
                        'ts': row['ts'],
                        'pnl': trade_pnl_usd,
                        'cumulative_pnl': current_pnl
                    })

                    position = 0

                # Track Drawdown
                if current_pnl > peak_pnl:
                    peak_pnl = current_pnl
                dd = peak_pnl - current_pnl
                if dd > max_dd:
                    max_dd = dd

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
        return result

    result.final_pnl = current_pnl
    result.max_drawdown = max_dd
    if result.total_trades > 0:
        result.win_rate = wins / result.total_trades

    return result
