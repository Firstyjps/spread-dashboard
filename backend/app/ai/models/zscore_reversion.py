# file: backend/app/ai/models/zscore_reversion.py
import math
from typing import Dict, Any

class ZScoreModel:
    def __init__(self, window_size: int = 100, entry_z: float = 2.0, exit_z: float = 0.5):
        """
        Z-Score Mean Reversion Model
        window_size: Number of ticks/rows to calculate moving average and std dev
        entry_z: Z-score threshold to enter a position
        exit_z: Z-score threshold to exit a position
        """
        self.window_size = window_size
        self.entry_z = entry_z
        self.exit_z = exit_z

    def calculate_zscore(self, history: list[float]) -> float:
        if len(history) < 2:
            return 0.0
        
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return 0.0
            
        return (history[-1] - mean) / std_dev

    def strategy_fn(self, row: Dict[str, Any], state: Dict[str, Any]) -> str | None:
        """
        The strategy function to be passed to the backtester.
        """
        if 'history' not in state:
            state['history'] = []
            state['position'] = 0 # 0: flat, 1: long, -1: short

        spread = row.get('exchange_spread_mid', 0.0)
        state['history'].append(spread)
        
        # Maintain window size
        if len(state['history']) > self.window_size:
            state['history'].pop(0)
            
        # Wait until window is full
        if len(state['history']) < self.window_size:
            return None

        z_score = self.calculate_zscore(state['history'])
        current_pos = state['position']

        # Logic
        action = None
        if current_pos == 0:
            # Entry rules
            if z_score > self.entry_z:
                # Spread is too wide, expect it to revert (short the spread)
                action = 'ENTER_SHORT'
                state['position'] = -1
            elif z_score < -self.entry_z:
                # Spread is too narrow/negative, expect it to revert (long the spread)
                action = 'ENTER_LONG'
                state['position'] = 1
        elif current_pos == 1:
            # Exit long spread when z-score reverts past exit_z
            if z_score > -self.exit_z:
                action = 'EXIT'
                state['position'] = 0
        elif current_pos == -1:
            # Exit short spread when z-score reverts past exit_z
            if z_score < self.exit_z:
                action = 'EXIT'
                state['position'] = 0

        return action

# Helper for backtester
def get_strategy(window=100, entry=2.0, exit=0.5):
    model = ZScoreModel(window_size=window, entry_z=entry, exit_z=exit)
    return model.strategy_fn
