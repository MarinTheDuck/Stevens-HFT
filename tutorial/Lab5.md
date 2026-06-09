# Lab 5 — Market Maker with Inventory Control

Source: **Lecture 6 — Market Making, Inventory Management & the SHIFT Risk Engine**.
Code: [`Lab5.py`](../Lab5.py).

> Logic and SHIFT API only. UI ignored.

## Original task (from the lecture)

> **Lab Exercise 5: Market Maker with Inventory Control**
>
> **Goal:** Implement a market maker in SHIFT and tune it to maintain near-zero inventory.
>
> 1. Start with the skeleton from slide 12; run it for 3 minutes and observe: how often do you hit `MAX_INV`? Is your realised P&L positive?
> 2. Add `inventory_skew()` to the reservation price computation
> 3. Add `adaptive_spread()` to widen quotes when volatile
> 4. Re-run and compare inventory excursions and P&L
> 5. (Extension) Add a flat-position exit: when inventory > 4 lots, submit a market sell to flatten
>
> *Vibe coding challenge:* "Stop quoting the bid side when inventory exceeds +3 lots, stop the ask side when inventory drops below −3 lots, and resume both when inventory returns within [−2, +2]."

## The idea

Unlike Labs 2/4 (one-sided directional bets), a **market maker posts both a bid
and an ask** every tick and earns the spread on round trips. The enemy is
**inventory**: one-sided fills leave you net long or short and exposed to price
moves. The whole lab is about pushing inventory back toward zero.

Two quoting modes (toggle live to compare, per step 4):

- **basic** — `reservation_price()` + `quote_spread()` (slide 8)
- **inventory** — `inventory_skew()` + `adaptive_spread()` (slide 11)

## Code logic

### Where to center the quotes — reservation price
```python
def reservation_price(mid, inventory, sigma, t_remaining, gamma=0.01):
    return mid - inventory * gamma * sigma**2 * t_remaining   # Avellaneda-Stoikov

def inventory_skew(inv, mid, max_inv=5, skew_factor=0.02):
    return mid + (-(inv / max_inv) * skew_factor * mid)       # stronger skew
```
Both push the center **away** from inventory: long (`inv > 0`) → center below mid
→ your ask is keener → you sell and shed inventory. Short → the reverse.

### How wide to quote — spread
```python
def quote_spread(sigma, t_remaining, gamma=0.01, base=0.04):
    return max(base, base + gamma * sigma**2 * t_remaining)   # wider when volatile

def adaptive_spread(sigma, inv, mid, max_inv=5, base=0.04, inv_penalty=0.01):
    return max(base, base + 100*sigma*mid + (abs(inv)/max_inv)*inv_penalty*mid)
```
`adaptive_spread` also widens with `|inventory|` — when you're loaded up you
demand more edge. (Its `100·σ·mid` term is the lecture's exact scaling and
produces a genuinely wide spread; the 4-cent basic mode is the one that fills
tightly. Comparing the two is the point of step 4.)

The final quotes are `bid = r − spread/2`, `ask = r + spread/2`.

### Inventory control — `_quote()`
```python
cancel_all_pending_orders()                 # never leave stale two-sided quotes
if flat_exit and abs(inv) > 4:  market-flatten; return     # extension (step 5)
_update_quote_sides(inv)                     # hysteresis, below
if quote_bid and inv <  MAX_INV: post LIMIT_BUY  1 @ bid   (+ buying-power check)
if quote_ask and inv > -MAX_INV: post LIMIT_SELL 1 @ ask
```

### One-sided pausing with hysteresis — `_update_quote_sides()`
```python
if inv >= 3:  quote_bid = False      # too long  -> stop buying
if inv <= -3: quote_ask = False      # too short -> stop selling
if -2 <= inv <= 2: quote_bid = quote_ask = True   # back near flat -> resume both
```
The gap between the ±3 trip and the ±2 reset is **hysteresis** — it stops the
quote from flickering on/off around a single threshold.

### Did it work? — risk metrics
On the **equity curve** (`equity0 + realized_pl + unrealized_pl` each tick):
```python
max_drawdown(equity)    # worst peak-to-trough drop (fraction)
sharpe_ratio(returns)   # mean/std of per-tick returns (raw, not annualised)
sortino_ratio(returns)  # same but only downside std in the denominator
```
Annualisation is skipped on purpose — the lecture notes it's fragile at HFT
speeds, so these are within-session comparison numbers.

## SHIFT API used

Setup (`run()`): `sub_order_book(symbol)`,
`request_sample_prices([symbol], 1.0, 30)`, `time.sleep(2)`.

Per heartbeat (1 s):

| Call | Used for |
|------|----------|
| `get_best_price(sym)` | bid/ask → mid for the reservation price |
| `get_sample_prices(sym, True)` | mid-price history → `realized_vol()` (σ) |
| `get_portfolio_item(sym)` | `get_long_shares() - get_short_shares()` = inventory |
| `get_portfolio_summary()` | `get_total_bp()` (buying-power check, equity base), `get_total_realized_pl()` |
| `get_unrealized_pl(sym)` | mark-to-market leg of the equity curve |

Orders each tick:

| Call | Meaning |
|------|---------|
| `cancel_all_pending_orders()` | drop the previous bid+ask before requoting |
| `shift.Order(LIMIT_BUY, sym, 1, bid_q)` | post the bid |
| `shift.Order(LIMIT_SELL, sym, 1, ask_q)` | post the ask |
| `shift.Order(MARKET_SELL/MARKET_BUY, sym, n)` | flatten inventory (extension / session end) |
| `submit_order(order)` | send each quote |

## σ (realized volatility)

```python
def realized_vol(prices):
    if len(prices) >= 21:
        return float(np.std(np.diff(np.log(prices[-20:]))))
    return 0.001    # small floor until the buffer fills
```
Std of 1-second log returns over the last 20 samples — the same volatility input
both the reservation price and the spread react to.

## Session timer

`SESSION_T = 600` feeds the `t_remaining` term in the Avellaneda-Stoikov
formulas (wider/safer quotes earlier, tighter near the close). When the clock
runs out the maker auto-stops and flattens.
