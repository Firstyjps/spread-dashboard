"""
CLI tool for LIMIT-only sliced execution on Bybit V5 LINEAR perpetuals.

Usage:
    cd backend
    python -m tools.linear_slice --symbol BTCUSDT --side Buy --qty 0.01 --slices 5 --testnet
    python -m tools.linear_slice --symbol ETHUSDT --side Sell --qty 0.1 --dry-run

Flags:
    --symbol     Trading pair (default: BTCUSDT)
    --side       Buy or Sell
    --qty        Total quantity to execute
    --slices     Number of child LIMIT orders (default: from settings)
    --testnet    Use Bybit testnet API
    --dry-run    Fetch instrument/orderbook, compute slices, print plan — no orders
    --timeout    Max runtime in seconds (default: from settings)
    --offset-bps Extra price aggressiveness in basis points (default: 0)
    --reduce-only  Close-only mode
"""
import argparse
import asyncio
import sys
import os

# Ensure backend/ is on sys.path so 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from app.config import settings
from app.execution.bybit_linear_client import BybitLinearClient
from app.execution.linear_limit_slicer import (
    SlicerConfig,
    execute_linear_limit_sliced,
    compute_slices,
    compute_aggressive_price,
)
from app.execution.maker_engine import (
    round_qty_to_step,
    compute_book_metrics,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="LIMIT-only sliced execution on Bybit LINEAR perpetuals"
    )
    parser.add_argument("--symbol", default="XAUTUSDT", help="Trading pair")
    parser.add_argument("--side", required=True, choices=["Buy", "Sell"], help="Order side")
    parser.add_argument("--qty", required=True, type=float, help="Total quantity")
    parser.add_argument("--slices", type=int, default=None, help="Number of slices")
    parser.add_argument("--testnet", action="store_true", help="Use Bybit testnet")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only, no orders")
    parser.add_argument("--timeout", type=float, default=None, help="Max runtime (seconds)")
    parser.add_argument("--offset-bps", type=int, default=0, help="Extra price aggressiveness")
    parser.add_argument("--reduce-only", action="store_true", help="Reduce-only mode")
    return parser.parse_args()


async def dry_run(client: BybitLinearClient, symbol: str, side: str, qty: Decimal, config: SlicerConfig):
    """Fetch market data, compute slices, print plan without placing orders."""
    print(f"\n{'='*60}")
    print(f"  DRY RUN — No orders will be placed")
    print(f"{'='*60}\n")

    # Fetch instrument info
    print("Fetching instrument info...")
    inst = await client.get_instrument_info(symbol)
    tick_size = inst["tick_size"]
    qty_step = inst["qty_step"]
    min_qty = inst["min_qty"]
    max_qty = inst["max_qty"]

    print(f"  tick_size:  {tick_size}")
    print(f"  qty_step:   {qty_step}")
    print(f"  min_qty:    {min_qty}")
    print(f"  max_qty:    {max_qty}")

    # Round target qty
    qty = round_qty_to_step(qty, qty_step)
    print(f"\n  target_qty (rounded): {qty}")

    # Compute slices
    slices = compute_slices(qty, config.num_slices, qty_step, min_qty)
    print(f"  num_slices: {len(slices)}")
    for i, s in enumerate(slices):
        marker = " ← remainder" if i == len(slices) - 1 else ""
        print(f"    slice[{i}]: {s}{marker}")
    total_sliced = sum(slices)
    print(f"  total:      {total_sliced} (target: {qty})")

    # Fetch orderbook
    print("\nFetching orderbook...")
    ob = await client.get_orderbook(symbol)
    book = compute_book_metrics(ob)
    print(f"  best_bid:  {book.best_bid}")
    print(f"  best_ask:  {book.best_ask}")
    print(f"  spread:    {book.spread}")
    print(f"  mid:       {book.mid}")

    # Compute aggressive price
    price = compute_aggressive_price(side, book, tick_size, config.price_offset_bps)
    print(f"\n  aggressive price ({side}): {price}")
    print(f"  offset_bps: {config.price_offset_bps}")

    # Summary
    notional = qty * price
    print(f"\n{'─'*60}")
    print(f"  SUMMARY")
    print(f"  Symbol:    {symbol}")
    print(f"  Side:      {side}")
    print(f"  Qty:       {qty}")
    print(f"  Price:     {price}")
    print(f"  Notional:  ~{notional:.2f} USD")
    print(f"  Slices:    {len(slices)}")
    print(f"  Timeout:   {config.max_runtime_s}s")
    print(f"{'─'*60}\n")

    # Fetch current position
    print("Current position:")
    pos = await client.get_position(symbol)
    if pos["amount"] > 0:
        print(f"  {pos['side']} {pos['amount']} @ {pos['entry_price']} (PnL: {pos['pnl']})")
    else:
        print("  No open position")

    print(f"\n{'='*60}")
    print(f"  DRY RUN COMPLETE — rerun without --dry-run to execute")
    print(f"{'='*60}\n")


async def live_run(client: BybitLinearClient, symbol: str, side: str, qty: Decimal, config: SlicerConfig):
    """Execute the sliced order for real."""
    print(f"\n{'='*60}")
    print(f"  LIVE EXECUTION")
    print(f"  Symbol: {symbol}  Side: {side}  Qty: {qty}  Slices: {config.num_slices}")
    print(f"{'='*60}\n")

    result = await execute_linear_limit_sliced(
        client=client,
        symbol=symbol,
        side=side,
        target_qty=qty,
        config=config,
    )

    # Print result
    print(f"\n{'─'*60}")
    print(f"  RESULT: {result.status.upper()}")
    print(f"{'─'*60}")
    print(f"  Target:       {result.target_qty}")
    print(f"  Filled:       {result.filled_qty}")
    print(f"  Remaining:    {result.remaining_qty}")
    print(f"  Avg Price:    {result.avg_price}")
    print(f"  Slices:       {result.num_slices_placed} placed / {result.num_slices_filled} filled")
    print(f"  Cancelled:    {result.num_cancelled}")
    print(f"  Time:         {result.elapsed_ms:.0f} ms")
    if result.detail:
        print(f"  Detail:       {result.detail}")
    print(f"{'─'*60}\n")

    if result.fills:
        print("  Fills:")
        for i, f in enumerate(result.fills):
            print(f"    [{i}] {f.qty} @ {f.price}")

    # Final position
    pos = await client.get_position(symbol)
    print(f"\n  Final position:")
    if pos["amount"] > 0:
        print(f"    {pos['side']} {pos['amount']} @ {pos['entry_price']} (PnL: {pos['pnl']})")
    else:
        print(f"    No open position")
    print()


async def main():
    args = parse_args()

    # Determine testnet
    use_testnet = args.testnet or settings.bybit_testnet
    env_label = "TESTNET" if use_testnet else "MAINNET"
    print(f"\n  Environment: {env_label}")

    # Build config
    config = SlicerConfig(
        num_slices=args.slices or settings.exec_slice_default,
        poll_interval_s=settings.exec_slice_poll_s,
        max_runtime_s=args.timeout or settings.exec_slice_timeout_s,
        price_offset_bps=args.offset_bps or settings.exec_slice_price_offset_bps,
        reduce_only=args.reduce_only,
    )

    # Create client
    client = BybitLinearClient(settings, testnet=use_testnet)

    target_qty = Decimal(str(args.qty))

    if args.dry_run:
        await dry_run(client, args.symbol, args.side, target_qty, config)
    else:
        await live_run(client, args.symbol, args.side, target_qty, config)


if __name__ == "__main__":
    asyncio.run(main())
