# file: backend/app/ai/data_exporter.py
import sqlite3
import csv
import os
import argparse
from datetime import datetime

# Adjust the path to where the SQLite DB is located.
# Depending on where the script is run, it might need absolute pathing.
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/alphast.db")

def export_spread_data(symbol: str, output_file: str, db_path: str = DEFAULT_DB_PATH, days: int = 7):
    """
    Exports historical spread data for a given symbol to a CSV file.
    This data will be used for AI/ML training and backtesting.
    """
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff_ts = (datetime.now().timestamp() - days * 86400) * 1000

    query = """
        SELECT 
            ts, symbol, bybit_mid, lighter_mid, bybit_bid, bybit_ask,
            lighter_bid, lighter_ask, exchange_spread_mid, long_spread,
            short_spread, bid_ask_spread_bybit, bid_ask_spread_lighter,
            basis_bybit, basis_bybit_bps, funding_diff
        FROM spread_metrics
        WHERE symbol = ? AND ts >= ?
        ORDER BY ts ASC
    """

    print(f"Exporting data for {symbol} from the last {days} days...")
    cursor.execute(query, (symbol, cutoff_ts))
    
    rows = cursor.fetchall()
    if not rows:
        print(f"No data found for {symbol} in the given timeframe.")
        conn.close()
        return

    # Column headers
    headers = [description[0] for description in cursor.description]

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"Successfully exported {len(rows)} rows to {output_file}")
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export spread metrics for AI Backtesting")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol to export (e.g. XAUTUSDT)")
    parser.add_argument("--days", type=int, default=7, help="Number of days of history to export")
    parser.add_argument("--output", type=str, default="data_export.csv", help="Output CSV filename")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Path to SQLite database")
    
    args = parser.parse_args()
    export_spread_data(args.symbol, args.output, args.db, args.days)
