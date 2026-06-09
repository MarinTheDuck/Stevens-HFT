# Lab 4 — Strategy Lab (Signal-Based Strategy)

Source: **Lecture 5 — Trend-Following, Momentum & Mean Reversion**.
Code: [`Lab4.py`](../Lab4.py).

> Logic and SHIFT API only. UI ignored.

## Original task (from the lecture)

> **Lab Exercise 4: Build a Signal-Based Strategy**
>
> **Goal:** Implement and test **one** momentum or mean-reversion strategy in SHIFT.
>
> 1. Choose: MA Crossover, MACD, Bollinger Bands, Z-Score, or VWAP
> 2. Implement the signal function using code from the slides
> 3. Integrate it into the skeleton from Deck 3 (replace `get_signal()`)
> 4. Run for 5 minutes, recording: number of trades placed, final realised P&L, winning vs losing trades
> 5. Tune one parameter (e.g., SMA window or Bollinger k) and re-run
>
> *Vibe coding challenge:* combine two signals — "Enter long only when **both** the Z-score signal is +1 AND the MACD signal is +1. Exit when either signal reverses."

This implementation includes **all five** strategies; you pick one at launch.

## The idea

Same skeleton loop as Lab 2, but the `get_signal()` slot is now any of five
classic strategies, split into two families that need **different exit rules**:

- **Momentum** (MA Crossover, MACD): a `0` means "no new cross" → **hold** the
  position until an opposite signal flips it.
- **Mean reversion** (Bollinger, Z-Score, VWAP): a `0` means "back at the mean"
  → **close** the position (slide 15's exit rule).

## Code logic

### Momentum signals
```python
def crossover_signal(prices, fast=5, slow=20):
    # +1 golden cross: fast SMA crosses ABOVE slow; -1 death cross: below
    # compares last two points of (fast vs slow) to detect the cross event

def macd_signal(prices):       # EMA(12) - EMA(26), signal = EMA(9) of that
    # +1 when MACD line crosses above its signal line; -1 when below
```
Both are **event detectors** — they fire `+1/-1` only on the bar where the cross
happens, and `0` otherwise.

### Mean-reversion signals
```python
def bollinger_signal(prices, n=20, k=2.0):
    # bands = mean ± k·std; +1 at/below lower band, -1 at/above upper band

def zscore_signal(prices, n=20, entry=1.5):
    # z = (price - mean)/std; +1 if z < -1.5 (oversold), -1 if z > +1.5

class VWAP:  # cumulative volume-weighted price + volume-weighted σ bands
    # +1 below lower band, -1 above upper band
```

### Uniform interface — `StratResult` + `Strategy`
Every strategy's `compute(prices, bp, vwap)` returns a `StratResult(signal,
note, bands, overlay)`. The `Strategy` dataclass also carries `kind`
(`"momentum"` / `"mean_reversion"`), which drives the exit rule below.

### Execution — `_execute()`
```python
cancel_all_pending_orders()
if signal == +1 and net < MAX_LOTS:  buy  1 lot @ ask   (+ buying-power check)
if signal == -1 and net > -MAX_LOTS: sell 1 lot @ bid
# the family-specific exit:
if kind == "mean_reversion" and signal == 0 and net != 0:
    market-close the position   # back to the mean -> flatten
```
Momentum strategies skip that last branch, so they hold through `0` signals.
`MAX_LOTS = 3` caps the position.

## SHIFT API used

Setup (`run()`): pick the strategy, then `sub_order_book(symbol)`,
`request_sample_prices([symbol], 1.0, 60)` (window 60 because MACD needs
`slow+signal+2 = 37` samples), `time.sleep(2)`.

Per heartbeat (1 s):

| Call | Used for |
|------|----------|
| `get_best_price(sym)` | bid/ask for quoting; `get_bid_price/ask_price` mid |
| `get_sample_prices(sym, True)` | mid-price history for all SMA/EMA/band maths |
| `get_last_price(sym)` / `get_last_size(sym)` | **VWAP only** — feed each trade print into the accumulator |
| `get_portfolio_item(sym)` | `get_long_shares() - get_short_shares()` = net lots |
| `get_unrealized_pl(sym)` | symbol P&L |
| `get_portfolio_summary().get_total_bp()` | buying-power check |

Orders: `shift.Order(LIMIT_BUY/LIMIT_SELL, sym, 1, price)` for entries,
`shift.Order(MARKET_SELL/MARKET_BUY, sym, n)` for the mean-reversion close /
flatten, via `submit_order()`; `cancel_all_pending_orders()` before each requote.

## VWAP detail

`VWAP` is **cumulative from the session open** (not a rolling window): each tick
adds the latest trade's `price·volume` and `volume` to running sums, so
`value = Σpv / Σv`. Bands use the volume-weighted variance
`Σp²v/Σv − value²`. This is why VWAP only updates when there are fresh trade
prints (`get_last_*`), unlike the sample-price strategies.
