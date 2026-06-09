# Lab 2 — First Algorithm

Source: **Lecture 3 — Vibe Coding**. Code: [`Lab2.py`](../Lab2.py).

> Logic and SHIFT API only. UI ignored.

## Original task (from the lecture)

> **Lab Exercise 2: Build Your First Algorithm**
>
> **Mission:** Extend the skeleton algorithm into a real trading strategy using vibe coding.
>
> 1. Start with the skeleton code from slide 12
> 2. Choose one of these starter ideas:
>    - **Order imbalance:** buy when ask size > bid size ×1.5, sell otherwise
>    - **Momentum:** buy when mid price crosses above its 10-period SMA
>    - **Mean reversion:** buy when price drops > 0.1% below 20-period SMA
> 3. Use an AI assistant to help fill in the `get_signal()` function
> 4. Verify the output against the vibe coding checklist
> 5. Run against SHIFT for 5 minutes; check your P&L
>
> *Deliverable:* show the instructor your running algorithm and explain in one sentence what signal it uses.

This implementation includes **all three** starter ideas, switchable live.

## The idea

The five-phase skeleton: **connect → subscribe → decide → execute → monitor**,
looping on a heartbeat (here every 2 s). Each tick computes a signal
(`+1` buy / `-1` sell / `0` hold), then places at most a 1-lot limit order.

## Code logic

### The three signals (`get_signal()` candidates)
```python
def momentum_signal(prices, mid, bp):
    if len(prices) < 10: return 0
    sma10 = sum(prices[-10:]) / 10
    return 1 if mid > sma10 else -1 if mid < sma10 else 0

def mean_reversion_signal(prices, mid, bp):
    if len(prices) < 20: return 0
    sma20 = sum(prices[-20:]) / 20
    if mid < sma20 * (1 - 0.001): return 1   # >0.1% below mean -> buy the dip
    if mid > sma20 * (1 + 0.001): return -1  # >0.1% above mean -> sell
    return 0

def imbalance_signal(prices, mid, bp):
    if bp.get_ask_size() > bp.get_bid_size() * 1.5: return 1
    if bp.get_bid_size() > bp.get_ask_size() * 1.5: return -1
    return 0
```
Each returns the lecture's ternary signal. Note the guards (`len < 10/20`) — the
rolling buffer must be deep enough or the signal is `0`.

### Execution — `_execute()`
The core trading rule:
```python
self.trader.cancel_all_pending_orders()          # cancel stale quote first
if signal == 1 and net < MAX_POSITION:           # buy, if not at long cap
    if ask*100 <= bp_avail * 0.9:                # buying-power check (90% buffer)
        submit LIMIT_BUY  1 lot @ round(ask, 2)
elif signal == -1 and net > -MAX_POSITION:       # sell, if not at short cap
    submit LIMIT_SELL 1 lot @ round(bid, 2)
```
Risk controls from the lecture: `MAX_POSITION = 5` lots cap, a buying-power
check before every buy, and **cancel-before-resubmit** so only one quote rests
at a time. Buy at the **ask** / sell at the **bid** is aggressive pricing to get
filled quickly.

## SHIFT API used

Setup (`run()`): `sub_order_book(symbol)`, then
`request_sample_prices([symbol], 1.0, 30)`, `time.sleep(2)`.

Per heartbeat:

| Call | Returns | Used for |
|------|---------|----------|
| `get_best_price(sym)` | `BestPrice` | `.get_bid_price/ask_price` (mid) and `.get_bid_size/ask_size` (imbalance) |
| `get_sample_prices(sym, True)` | `list[float]` | mid-price history for the SMAs |
| `get_portfolio_item(sym).get_shares()` | `int` | **net** position in lots (long − short) |
| `get_unrealized_pl(sym)` | `float` | mark-to-market P&L for the symbol |
| `get_portfolio_summary()` | `PortfolioSummary` | `get_total_bp()` for the buying-power check |

Orders:

| Call | Meaning |
|------|---------|
| `shift.Order(shift.Order.LIMIT_BUY, sym, 1, price)` | 1-lot limit buy (lots, not shares) |
| `shift.Order(shift.Order.LIMIT_SELL, sym, 1, price)` | 1-lot limit sell |
| `shift.Order(shift.Order.MARKET_SELL / MARKET_BUY, sym, n)` | used by **flatten** to close `n` lots now |
| `trader.submit_order(order)` | send it |
| `trader.cancel_all_pending_orders()` | clear resting orders before requoting |

## Key detail: 1 lot = 100 shares

`shift.Order` sizes are in **lots**. The buying-power check uses `ask * 100`
(100 shares per lot) to estimate the cash a 1-lot buy needs.

## Safety

`self.trading` starts `False` — the heartbeat reads the market and computes the
signal but **submits nothing** until trading is armed. This prevents a fresh
launch from immediately firing live orders.
