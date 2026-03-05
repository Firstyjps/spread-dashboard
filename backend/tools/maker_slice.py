"""
CLI tool for Maker-Only sliced execution on Bybit V5 LINEAR perpetuals.

Usage:
    cd backend
    python -m tools.maker_slice --symbol XAUTUSDT --side BUY --target-usd 1000 --slices 10
    python -m tools.maker_slice --symbol BTCUSDT --side SELL --target-usd 500 --dry-run
    python -m tools.maker_slice --symbol ETHUSDT --side BUY --target-usd 100 --testnet

Flags:
    --symbol       Trading pair (default: BTCUSDT)
    --side         BUY or SELL
    --target-usd   Total notional in USD
    --slices       Number of child orders (default: 10)
    --pace-ms      Min delay between slices in ms (default: 500)
    --stale-ms     Cancel unfilled order after ms (default: 2000)
    --tolerance    Stop tolerance in USD (default: 2.0)
    --timeout      Max execution time in seconds (default: 120)
    --testnet      Use Bybit testnet API
    --dry-run      Fetch instrument/orderbook, compute plan, no orders
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from app.config import settings
from app.exchanges.bybit_linear.client import BybitLinearMakerClient
from app.execution.maker_slicer_linear import (
    execute_linear_maker_sliced,
    _compute_maker_price,
    _round_qty,
)


def parse_args():
    p = argparse.ArgumentParser(description="Maker-Only sliced execution (PostOnly LIMIT)")
    p.add_argument("--symbol", default="BTCUSDT", help="Trading pair")
    p.add_argument("--side", required=True, choices=["BUY", "SELL", "Buy", "Sell"],
                   help="Order side")
    p.add_argument("--target-usd", required=True, type=float, help="Total USD notional")
    p.add_argument("--slices", type=int, default=10, help="Number of slices")
    p.add_argument("--pace-ms", type=int, default=500, help="Pace between slices (ms)")
    p.add_argument("--stale-ms", type=int, default=2000, help="Stale order timeout (ms)")
    p.add_argument("--tolerance", type=float, default=2.0, help="Tolerance USD")
    p.add_argument("--timeout", type=int, default=120, help="Max duration (seconds)")
    p.add_argument("--testnet", action="store_true", help="Use Bybit testnet")
    p.add_argument("--dry-run", action="store_true", help="Print plan only, no orders")
    return p.parse_args()


async def dry_run(client, symbol, side, target_usd, slices):
    """Fetch market data, compute slice plan, print without placing orders."""
    print(f"\n{'='*65}")
    print(f"  DRY RUN — Maker-Only Slicer (PostOnly LIMIT)")
    print(f"{'='*65}\n")

    # Instrument info
    print("  Fetching instrument info...")
    inst = await client.get_instrument_info(symbol)
    print(f"    tick_size:     {inst.tick_size}")
    print(f"    qty_step:      {inst.qty_step}")
    print(f"    min_qty:       {inst.min_qty}")
    print(f"    min_notional:  {inst.min_notional}")

    # Orderbook
    print("\n  Fetching orderbook...")
    ob = await client.get_orderbook(symbol)
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    if bids and asks:
        best_bid = Decimal(bids[0][0])
        best_ask = Decimal(asks[0][0])
        spread = best_ask - best_bid
        print(f"    best_bid:  {best_bid}")
        print(f"    best_ask:  {best_ask}")
        print(f"    spread:    {spread} ({float(spread / best_bid * 10000):.2f} bps)")

        # Maker price
        maker_price = _compute_maker_price(side, best_bid, best_ask, inst.tick_size)
        print(f"\n    maker_price ({side}): {maker_price}")
        print(f"    (BUY=bid, SELL=ask — rests on book, never crosses)")

        # Slice plan
        target = Decimal(str(target_usd))
        slice_usd = target / slices
        if slice_usd < inst.min_notional:
            slices = max(1, int(target / inst.min_notional))
            slice_usd = target / slices
            print(f"\n    Adjusted slices to {slices} (min_notional={inst.min_notional})")

        print(f"\n  Slice Plan:")
        total_qty = Decimal("0")
        for i in range(slices):
            qty = _round_qty(slice_usd / maker_price, inst.qty_step)
            if qty < inst.min_qty:
                qty = inst.min_qty
            notional = qty * maker_price
            total_qty += qty
            print(f"    [{i:2d}] qty={qty}  price={maker_price}  notional=~{notional:.2f} USD")

        print(f"\n  {'─'*60}")
        print(f"  SUMMARY")
        print(f"    Symbol:       {symbol}")
        print(f"    Side:         {side}")
        print(f"    Target USD:   {target_usd}")
        print(f"    Slices:       {slices}")
        print(f"    Slice USD:    ~{slice_usd:.2f}")
        print(f"    Total Qty:    {total_qty}")
        print(f"    Order type:   LIMIT + PostOnly (maker only)")
        print(f"  {'─'*60}")
    else:
        print("    ERROR: Empty orderbook!")

    # Position
    print("\n  Current position:")
    pos = await client.get_position(symbol)
    if pos["amount"] > 0:
        print(f"    {pos['side']} {pos['amount']} @ {pos['entry_price']}")
    else:
        print(f"    No open position")

    print(f"\n{'='*65}")
    print(f"  DRY RUN COMPLETE — rerun without --dry-run to execute")
    print(f"{'='*65}\n")


async def live_run(client, symbol, side, target_usd, args):
    """Execute the maker-only sliced order."""
    print(f"\n{'='*65}")
    print(f"  LIVE EXECUTION — Maker-Only PostOnly LIMIT Slicer")
    print(f"  Symbol: {symbol}  Side: {side}  Target: ${target_usd}")
    print(f"{'='*65}\n")

    result = await execute_linear_maker_sliced(
        client=client,
        symbol=symbol,
        side=side,
        target_usd=target_usd,
        slices=args.slices,
        pace_ms=args.pace_ms,
        stale_ms=args.stale_ms,
        tolerance_usd=args.tolerance,
        max_duration_s=args.timeout,
    )

    # Print result
    print(f"\n  {'─'*60}")
    print(f"  RESULT: {result.status.upper()}")
    print(f"  {'─'*60}")
    print(f"  Target USD:     {result.target_usd}")
    print(f"  Filled USD:     {result.filled_usd}")
    print(f"  Remaining USD:  {result.remaining_usd}")
    print(f"  Filled Qty:     {result.filled_qty}")
    print(f"  Avg Price:      {result.avg_price}")
    print(f"  Slices:         {result.slices_placed} placed / {result.slices_filled} filled")
    print(f"  Cancelled:      {result.slices_cancelled}")
    print(f"  PostOnly Rejects: {result.postonly_rejects}")
    print(f"  Time:           {result.elapsed_ms:.0f} ms")
    print(f"  Est. Fee:       ${result.estimated_fee_usd}")

    # Maker/taker verification
    print(f"\n  Fill Verification:")
    print(f"    Maker fills:  {result.maker_fill_count}")
    print(f"    Taker fills:  {result.taker_fill_count}")
    if result.taker_fill_count > 0:
        print(f"    ⚠️  TAKER FILLS DETECTED — investigate!")
    elif result.maker_fill_count > 0:
        print(f"    ✓  All verified fills are MAKER")

    if result.detail:
        print(f"\n  Detail: {result.detail}")
    print(f"  {'─'*60}")

    # Print fills
    if result.fills:
        print(f"\n  Fills:")
        for i, f in enumerate(result.fills):
            maker_tag = ""
            if f.is_maker is True:
                maker_tag = " [MAKER ✓]"
            elif f.is_maker is False:
                maker_tag = " [TAKER ⚠️]"
            print(f"    [{i}] {f.qty} @ {f.price} = ${f.value_usd:.2f}{maker_tag}")

    # Final position
    pos = await client.get_position(symbol)
    print(f"\n  Final position:")
    if pos["amount"] > 0:
        print(f"    {pos['side']} {pos['amount']} @ {pos['entry_price']}")
    else:
        print(f"    No open position")
    print()


async def main():
    args = parse_args()

    use_testnet = args.testnet or settings.bybit_testnet
    env_label = "TESTNET" if use_testnet else "MAINNET"
    side = "Buy" if args.side.upper() == "BUY" else "Sell"

    print(f"\n  Environment: {env_label}")
    print(f"  PostOnly LIMIT = guaranteed maker fills (0.02% fee)")

    client = BybitLinearMakerClient(settings, testnet=use_testnet)

    if args.dry_run:
        await dry_run(client, args.symbol, side, args.target_usd, args.slices)
    else:
        await live_run(client, args.symbol, side, args.target_usd, args)


if __name__ == "__main__":
    asyncio.run(main())
