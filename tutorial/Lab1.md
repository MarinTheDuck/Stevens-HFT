# Lab 1 — Market Monitor

Source: **Lecture 2 — Python & the SHIFT API**. Code: [`Lab1.py`](../Lab1.py).

> This tutorial explains the *logic* and the *SHIFT API usage* only. The Textual/
> Rich/plotext UI is deliberately ignored.

## Original task (from the lecture)

> **Lab Exercise 1: Market Monitor**
>
> **Goal:** Write a Python script that connects to SHIFT and prints a live summary every second.
>
> 1. Connect to SHIFT and print the list of available symbols
> 2. For each symbol, print: best bid, best ask, bid-ask spread, last price
> 3. Add a 5-period SMA using `get_sample_prices` and indicate whether the current price is above or below it
> 4. Print your portfolio summary at the end
> 5. Disconnect cleanly using `try/finally`
>
> *Vibe coding hint:* "Write a Python script using the SHIFT trading API that connects with `shift.Trader`, subscribes to all order books, and prints a market summary table every second showing symbol, bid, ask, spread, and 5-period SMA signal."

## The idea

Pure **read-only** monitoring. No orders are sent. Every second we re-read the
market for every tradable symbol, compute one derived signal (price vs its own
5-period moving average), and read the account summary.

## Code logic

### The signal — `sma()`
```python
def sma(values, period=5):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period
```
A 5-period **simple moving average** of the mid-price samples. Returns `None`
until at least 5 samples exist (the rolling buffer needs a few seconds to fill).

### ABOVE / BELOW — `SymbolRow.signal`
- `mid = (bid + ask) / 2` (falls back to `last` if a side is missing).
- If `mid >= sma5` → **ABOVE** (price stronger than its recent average); else
  **BELOW**. This is the "is the current price above or below the SMA?" of step 3.

`spread = ask - bid` is just the touch spread.

## SHIFT API used

Setup (in `run()`), once at startup:

| Call | Why |
|------|-----|
| `trader.sub_all_order_book()` | subscribe to every symbol's order book so bid/ask are live |
| `trader.request_company_names()` | ask the server to load human-readable names |
| `trader.get_stock_list()` | the list of tradable tickers (step 1) |
| `trader.request_sample_prices(symbols, sampling_frequency=1.0, sampling_window=60)` | start SHIFT's rolling 1-second mid-price buffer (needed for the SMA) |

Then once per second, for each symbol:

| Call | Returns | Used for |
|------|---------|----------|
| `trader.get_best_price(sym)` | `BestPrice` | `.get_bid_price()`, `.get_ask_price()` → bid/ask/spread |
| `trader.get_last_price(sym)` | `float` | last trade price |
| `trader.get_sample_prices(sym, True)` | `list[float]` | mid-price history; `True` = mid prices, feeds `sma()` |
| `trader.get_company_name(sym)` | `str` | display name |

Account summary (step 4):

| Call | Returns |
|------|---------|
| `trader.get_portfolio_summary()` | `PortfolioSummary` |
| `ps.get_total_bp()` | buying power |
| `ps.get_total_shares()` | shares traded this session |
| `ps.get_total_realized_pl()` | realised P&L |
| `ps.get_timestamp()` | last update time |

### Clean disconnect (step 5)

Lab 1 itself doesn't manage the connection — that lives in
[`connection.py`](../connection.py)'s `Connection` context manager, which wraps
the whole session in `try/finally` and always calls `trader.disconnect()` on
exit. That satisfies requirement 5 for every lab at once.

## Why a 2-second sleep after `request_sample_prices`

The sample buffer fills at 1 sample/second. `time.sleep(2)` lets a couple of
samples land before the first read so the table isn't all dashes. The SMA needs
5 samples, so the ABOVE/BELOW signal appears a few seconds in.
