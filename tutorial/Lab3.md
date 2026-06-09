# Lab 3 — Triple Barrier Labelling

Source: **Lecture 4 — Core Strategy Elements & the Triple Barrier Method**.
Code: [`Lab3.py`](../Lab3.py).

> Logic and SHIFT API only. UI ignored.

## Original task (from the lecture)

> **Lab Exercise 3: Triple Barrier Labelling**
>
> **Goal:** Apply the Triple Barrier Method to real SHIFT data and analyse the label distribution.
>
> 1. Connect to SHIFT and collect 200 mid-price observations for **two symbols** of your choice (use `get_sample_prices`)
> 2. Apply `apply_triple_barrier()` with `c = 1.5` and `T = 30`
> 3. Print and interpret the label distribution. Is it balanced?
> 4. Try `c = 0.5` and `c = 3.0`. How does the distribution change?
> 5. (Extension) Compute `compute_features()` at each labelled entry point. Which feature looks most correlated with the label?
>
> *Vibe coding extension:* "Modify `apply_triple_barrier` to use asymmetric barriers: upper barrier = 1.5σ, lower barrier = 1.0σ. What effect does this have on the label distribution?"

## The idea

This lab is **analysis, not trading** — no orders are placed. It labels every
historical entry point: was it a good place to buy? Each entry gets three
barriers and the **first one hit** decides the label:

- **Upper barrier** (take-profit) hit first → `+1`
- **Lower barrier** (stop-loss) hit first → `-1`
- **Vertical barrier** (time `T` expires) first → `0`

Barrier widths scale with volatility, so the same `c` means the same "number of
sigmas" on a $5 stock and a $500 stock.

## Code logic

### Volatility — `compute_volatility()`
```python
log_rets = np.log(p[1:] / p[:-1])     # last (window+1) prices -> window returns
return float(np.std(log_rets))        # population std (matches np.std default)
```
Returns `None` until `window+1` (= 21) prices exist.

### One label — `label_entry()`
```python
for t in range(t0+1, min(t0+T+1, len(prices))):
    if prices[t] >= h_up:   return  1   # take-profit hit first
    if prices[t] <= h_down: return -1   # stop-loss hit first
return 0                                 # neither within T -> time expiry
```
Walks forward from the entry, checking which horizontal barrier the path touches
first within `T` steps.

### Label the whole series — `apply_triple_barrier()`
```python
for t0 in range(vol_window, len(prices) - T):
    sigma = compute_volatility(prices[:t0+1])
    if not sigma: continue
    h_up   = p0 * (1 + c * sigma)        # take-profit barrier
    h_down = p0 * (1 - c * sigma)        # stop-loss barrier
    results.append((t0, p0, label_entry(...)))
```
Only entries with at least `vol_window` history before and `T` bars after are
labelled. **`c` is the knob:** bigger `c` = wider barriers = harder to hit =
more `0` (time-expiry) labels. That's exactly what step 4 asks you to observe;
the app runs `c ∈ {0.5, 1.5, 3.0}` side by side.

### Interpreting balance — `verdict()`
A quick read of the distribution: `>80%` zeros → barriers too wide / `T` too
short; `>80%` of one sign → too narrow (noise); otherwise "balanced".

### Extension — features & correlation
`price_features(prices, t0)` builds price-only features known at entry time
(`sma_ratio`, `trend`, `volatility`, `momentum`). `feature_correlations()` then
runs `np.corrcoef(feature, label)` across all entries to see which feature lines
up best with the eventual label.

## SHIFT API used

This lab touches the API only to **collect price data**:

| Call | Why |
|------|-----|
| `trader.get_stock_list()` | pick two symbols (defaults to AAPL + MSFT, else the first two) |
| `trader.request_sample_prices(symbols, 1.0, 250)` | start a rolling 1-second mid-price buffer big enough for ~200 samples |
| `trader.get_sample_prices(sym, True)` | the mid-price series fed to `apply_triple_barrier()` |

Everything else (`compute_volatility`, `label_entry`, `apply_triple_barrier`,
features, correlation) is plain numpy on those price lists — no trading calls.

## Why labels appear gradually

The buffer grows 1 sample/second. `apply_triple_barrier` needs
`len(prices) > vol_window + T` (= 20 + 30 = 50) before the first label exists,
so meaningful distributions show up ~1 minute in and stabilise as the buffer
fills toward 200.
