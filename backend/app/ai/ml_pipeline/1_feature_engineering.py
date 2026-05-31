import sqlite3
import pandas as pd
import numpy as np
import os

# We will read from a local CSV or DB
def create_features(df: pd.DataFrame, window_sizes=[10, 50, 300]) -> pd.DataFrame:
    """
    Creates technical indicators and features from the raw spread data.
    """
    print("Generating features...")
    # Basic spread
    df['spread'] = df['exchange_spread_mid']
    
    for w in window_sizes:
        # Rolling Mean
        df[f'mean_{w}'] = df['spread'].rolling(window=w).mean()
        # Rolling Std (Volatility)
        df[f'std_{w}'] = df['spread'].rolling(window=w).std()
        # Z-Score
        df[f'zscore_{w}'] = (df['spread'] - df[f'mean_{w}']) / df[f'std_{w}']
        # Rolling Min/Max
        df[f'min_{w}'] = df['spread'].rolling(window=w).min()
        df[f'max_{w}'] = df['spread'].rolling(window=w).max()
        # Distance from min/max
        df[f'dist_min_{w}'] = df['spread'] - df[f'min_{w}']
        df[f'dist_max_{w}'] = df[f'max_{w}'] - df['spread']
        
    # Rate of change
    df['roc_10'] = df['spread'].diff(10)
    df['roc_50'] = df['spread'].diff(50)
    
    # Drop rows with NaN due to rolling windows
    df = df.dropna()
    return df

def create_labels(df: pd.DataFrame, forward_window=7200) -> pd.DataFrame:
    """
    Creates the target labels for Regression.
    target_short: Max favorable spread movement for a short position (spread drops) in the next forward_window ticks.
    target_long: Max favorable spread movement for a long position (spread rises) in the next forward_window ticks.
    """
    print("Generating labels for Regression...")
    
    # Future minimum and maximum in the next N ticks
    df['future_min'] = df['spread'].shift(-forward_window).rolling(window=forward_window).min()
    df['future_max'] = df['spread'].shift(-forward_window).rolling(window=forward_window).max()
    
    # Target values (Continuous / Regression)
    df['target_short'] = df['spread'] - df['future_min'] # Positive means spread dropped (profit for short)
    df['target_long'] = df['future_max'] - df['spread']  # Positive means spread rose (profit for long)
    
    # Clean up
    df = df.dropna()
    return df

def run_pipeline(db_path: str, symbol: str, output_csv: str):
    print(f"Connecting to DB: {db_path} for {symbol}")
    conn = sqlite3.connect(db_path)
    
    # Load data (Limit to 500k rows)
    query = f"SELECT ts, exchange_spread_mid FROM spread_metrics WHERE symbol = '{symbol}' ORDER BY ts ASC LIMIT 500000"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"Loaded {len(df)} rows.")
    
    df = create_features(df)
    df = create_labels(df, forward_window=7200) # 2 hours forward window

    
    # Save features and labels
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"Saved {len(df)} rows of training data to {output_csv}")
    
    # Basic stats on targets
    print(f"\nTarget Short (Max Return in bps) Summary:")
    print((df['target_short'] * 10000).describe())
    print(f"Target Long (Max Return in bps) Summary:")
    print((df['target_long'] * 10000).describe())

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, required=True)
    parser.add_argument("--symbol", type=str, default="XAUTUSDT")
    parser.add_argument("--output", type=str, default="train_data.csv")
    args = parser.parse_args()
    
    run_pipeline(args.db, args.symbol, args.output)
