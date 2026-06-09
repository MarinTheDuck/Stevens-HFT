# Finance Week (HFT) — Course Recap

A single-file summary of the whole course: the eight lectures, the SHIFT Python
API, and how Labs 1–5 fit in. **Logic and concepts only — no UI.**

Per-lab deep-dives live alongside this file: [Lab1](Lab1.md) · [Lab2](Lab2.md)
· [Lab3](Lab3.md) · [Lab4](Lab4.md) · [Lab5](Lab5.md).

## The arc of the week

| Day | Topic | Lecture(s) | Lab |
|-----|-------|-----------|-----|
| Mon | Fundamentals, LOB, NBBO, SHIFT · Python & API | 1, 2 | **Lab 1** |
| Mon | Vibe coding + first algorithm | 3 | **Lab 2** |
| Tue | Triple Barrier labelling | 4 | **Lab 3** |
| Tue | Strategy families (trend/momentum/mean-rev) | 5 | **Lab 4** |
| Wed | Market making, inventory, risk engine | 6 | **Lab 5** |
| Thu | Flash crashes, spoofing, tournament prep | 7 | — |
| Fri | Final competition | 8 | — |

Labs 1–5 map one-to-one to Lectures 2–6. Lectures 7–8 are case studies and
competition rules — no new lab exercise (Labs 6–8 in the launcher are stubs).

---

## Lecture 1 — Trading Fundamentals, the LOB & SHIFT

**Algorithmic trading (AT)** = automated systems deciding *when/what/how much*.
Two families: **execution** algos (fill a big order with low impact — TWAP/VWAP)
and **strategy** algos (predict direction, generate alpha). **HFT** is the subset
with sub-millisecond submission, very high order-to-trade ratios, and flat
positions at day end. HFT is ~55% of US / ~40% of EU equity volume.

**Order types**
- **Market** — immediate fill at the best available price; guaranteed fill, no
  price control. Use when speed > price.
- **Limit** — fills only at your price or better; price guaranteed *if* filled,
  but may never fill. Use when price > certainty.

**Order anatomy:** symbol · type · **size in lots (1 lot = 100 shares)** · price
(0.0 for market) · auto-assigned UUID · status · timestamp.

**Time-in-Force:** DAY / GTC / IOC / FOK. **SHIFT uses DAY** for all limit orders
in a session.

**The Limit Order Book (LOB)** is the exchange's central data structure: all
resting limit orders sorted by price. Key terms: **best bid** (highest buyer),
**best ask** (lowest seller), **mid** = (bid+ask)/2, **depth** (volume at a
level). Orders match by **price–time priority** — at the same price, the earlier
order fills first, so **queue position** is gold for HFT.

**Market impact:** a large market order *walks the book* across levels →
**slippage** (avg fill worse than the touch). Thin books move easily.

**NBBO** (National Best Bid & Offer): with ~20 US exchanges, Reg NMS (2005)
requires routing to the best price. NBBO bid = max bid, ask = min ask across
exchanges. In SHIFT, `get_best_price()` returns both **global** (NBBO-like) and
**local** (this client's) best prices.

**SHIFT** (Stevens High Frequency Trading): realistic offline market simulator —
real LOB, real matching engine, multi-asset, real-time. Architecture: Datafeed
Engine → Matching Engine → Brokerage Center → Clients (Python/C++). Two modes:
**Replay** (historical data, deterministic) and **Live Agent Simulation** (prices
emerge from competing agents, non-deterministic). The competition uses replay.

---

## The SHIFT Python API (reference manual)

One `shift.Trader` object is the gateway for everything. **1 lot = 100 shares.**

**Connection** — `Trader(username)` · `connect(cfg, password)` ·
`disconnect()` · `is_connected()`. Always disconnect in a `finally` block.

**Market data** — `get_stock_list()` · `get_last_price(sym)` ·
`get_last_size(sym)` (lots) · `get_last_trade_time()` · `get_best_price(sym)` →
`BestPrice` · `get_close_price(sym, buy, size)` (hypothetical fill) ·
`request_company_names()` / `get_company_name(sym)`.

**Order book** — `sub_order_book(sym)` / `sub_all_order_book()` / `unsub_*` ·
`get_order_book(sym, type, max_level)` → list of `OrderBookEntry`
(`.price/.size/.destination/.time`); `type` ∈ `OrderBookType.GLOBAL_BID/
GLOBAL_ASK/LOCAL_BID/LOCAL_ASK`. **You must subscribe before prices populate.**

**Order management** — `submit_order(order)` · `submit_cancellation(order)` ·
`cancel_all_pending_orders(timeout=10)` · `get_waiting_list()` /
`get_waiting_list_size()` (open orders) · `get_submitted_orders()` ·
`get_order(id)` · `get_executed_orders(id)`.

**`shift.Order(type, symbol, size, price=0.0, id="")`** — types: `LIMIT_BUY`,
`LIMIT_SELL`, `MARKET_BUY`, `MARKET_SELL`, `CANCEL_BID`, `CANCEL_ASK`.
Attributes after submit: `executed_size`, `executed_price`, `id` (UUID), `status`.
Statuses: `PENDING_NEW → NEW → PARTIALLY_FILLED → FILLED`, or `PENDING_CANCEL /
CANCELED / REJECTED`. **PENDING states are transient — check for FILLED.**

**`BestPrice`** — combined `get_bid_price/ask_price/bid_size/ask_size()`, plus
`get_global_*` and `get_local_*`. Use the combined ones for most strategies.

**Portfolio** — `get_portfolio_summary()` → `get_total_bp()` (buying power),
`get_total_shares()`, `get_total_realized_pl()`, `get_timestamp()`. Per-symbol:
`get_portfolio_item(sym)` → `get_shares()` (net), `get_long_shares()`,
`get_short_shares()`, `get_price/long_price/short_price()`, `get_realized_pl()`.
`get_unrealized_pl(sym="")` for mark-to-market.

**Sample prices** (rolling price buffer SHIFT maintains for you) —
`request_sample_prices(symbols, sampling_frequency=1.0, sampling_window=31)` ·
`get_sample_prices(sym, mid_prices=False)` → `list[float]` ·
`get_sample_prices_size(sym)` · `get_log_returns(sym)` ·
`cancel_all_sample_prices_requests()`. This is how every lab gets price history
without polling in a loop.

**Common gotchas:** `get_best_price` returns 0.0 until you `sub_order_book`;
`REJECTED` usually means insufficient buying power or a price too far from market;
sizes are lots not shares.

---

## Lecture 2 — Python & the SHIFT API → **Lab 1: Market Monitor**

Environment (conda `shift`), the `Trader` lifecycle, and every market-data /
portfolio / sample-price call above. **Lab 1** is read-only: list symbols, show
bid/ask/spread/last, add a 5-period SMA (ABOVE/BELOW), print the portfolio,
disconnect cleanly. See [Lab1.md](Lab1.md).

## Lecture 3 — Vibe Coding → **Lab 2: First Algorithm**

The five-phase skeleton (**connect → subscribe → decide → execute → monitor**)
looping on a heartbeat, plus the discipline of *verifying* AI-generated code
(right API names, lots vs shares, buy/sell direction, empty-list guards,
cancel-before-resubmit, disconnect in `finally`). **Lab 2** implements three
`get_signal()` ideas — momentum (10-SMA), mean reversion (20-SMA ±0.1%), order
imbalance (size ×1.5) — with a position cap and buying-power check.
See [Lab2.md](Lab2.md).

## Lecture 4 — Triple Barrier → **Lab 3: Triple Barrier Labelling**

How to *label* whether a past entry was good: place a take-profit, a stop-loss,
and a time barrier; the first one hit gives +1/−1/0. Barriers scale with
volatility (`p₀(1 ± c·σ)`). A balanced label set is healthy; mostly-zero means
barriers too wide / `T` too short. **Lab 3** collects 200 mid-prices for two
symbols, compares `c ∈ {0.5,1.5,3.0}`, and correlates price features with the
label. Analysis only — no orders. See [Lab3.md](Lab3.md).

## Lecture 5 — Strategy Families → **Lab 4: Strategy Lab**

Markets alternate between **trending** (use momentum) and **mean-reverting**
(buy dips/sell rallies) regimes. Tools: SMA/EMA crossover, MACD, Bollinger Bands,
z-score, VWAP. **Exit rules matter as much as entries** — momentum holds until an
opposite signal; mean reversion closes on return to the mean. **Lab 4**
implements all five and lets you pick one at launch. See [Lab4.md](Lab4.md).

## Lecture 6 — Market Making & Risk → **Lab 5: Market Maker**

A market maker posts **both sides** and earns the spread; the risk is
**inventory** (one-sided fills) and **adverse selection**. Avellaneda-Stoikov:
skew the reservation price toward zero inventory and widen the spread with
volatility/inventory. Measure results on the **equity curve**: max drawdown,
Sharpe, Sortino. **Lab 5** has basic vs inventory-aware modes, one-sided quoting
with hysteresis, and a flat-position exit. See [Lab5.md](Lab5.md).

---

## Lecture 7 — Flash Crashes, Spoofing & Tournament Prep

**Flash Crash (May 6, 2010):** a $4.1B sell algorithm with no price/time limits
triggered an HFT "hot potato" feedback loop → Dow −1,000 pts (9%) in minutes;
CME stop-logic paused trading and prices recovered. HFT **amplified, did not
cause** it. Reforms: circuit breakers (>5% in 5 min → 5-second pause), Limit
Up-Limit Down (2013), market-maker obligations.

**Knight Capital (Aug 1, 2012):** a deployment error reactivated dead "Power Peg"
code on 1 of 8 servers → 4 million erroneous orders in 45 minutes → **$440M
loss**, near-bankruptcy. Lessons baked into every algorithm:
- **Kill switch** — a way to stop instantly (`cancel_all_pending_orders()` +
  `disconnect()`).
- **Position limits** — a hard max-size check **before every order**.
- **Test before deploy**, **remove dead code**, **monitor in real time**,
  **buying-power check**, **log everything**.

**Spoofing:** placing large orders with **no intent to execute** to fake
supply/demand — illegal (Dodd-Frank, MiFID II; e.g. Sarao, Coscia). Detected via
**order-to-trade ratio**, order persistence, layering, price-impact correlation.
SHIFT logs all orders/cancels; spoofing-like patterns may be flagged.

**Tournament (from Deck 7):** 1-hour replay session, scored on **realised P&L**;
**unrealised positions don't count** — you must **flatten before the close**
(the `T_remaining < 300` flat-exit snippet). Plus the 10-item pre-competition
checklist (connection, signal correctness, size limits, cancel-on-entry,
flat-exit, kill switch, buying-power, logging, no infinite retries,
disconnect-in-finally).

## Lecture 8 — Final Competition

**Format:** 3:00 PM start, 1-hour live session, **flat all positions by 4:00 PM**
(residuals closed at mid), results + 5-minute team presentations, awards.

**Rules:** realised P&L in USD; equal starting capital; all symbols & order types
allowed; one account per team (multiple scripts OK); instructor sees all data;
**spoofing-like systematic cancel-before-fill → disqualification**.

**Presentation (5 min):** strategy name, signal logic + chosen parameters, risk
controls, results (trades, win rate, best/worst), and what you'd improve.
**Scoring:** signal quality 30% · risk management 25% · code clarity 20% ·
results 15% · presentation 10%. *A well-reasoned losing strategy can beat a lucky
winner* — judges want to see you understand **why** it behaved as it did.

**Last-hour tips:** watch the P&L trend; reduce size or pause entries if it
drops; in the last 5 minutes confirm the flat-exit fired, check
`get_portfolio_items()` for residuals, `cancel_all_pending_orders()`, and **avoid
large market orders at the close** (slippage is worst then).

---

## Cross-cutting principles (true for every trading lab)

1. **1 lot = 100 shares.** Order sizes and `get_*_size` are in lots.
2. **Subscribe first** (`sub_order_book` / `sub_all_order_book`) and start
   `request_sample_prices` — prices are 0/empty until you do.
3. **Cancel before requoting** so only intended orders rest in the book.
4. **Check buying power** before buys; **cap position size**; expect `REJECTED`
   if you don't.
5. **Realised P&L is what counts** — close positions before the session ends.
6. **Always disconnect** in `try/finally` (handled centrally by
   [`connection.py`](../connection.py)).
7. **Log/monitor** so you (or an LLM) can diagnose what the algorithm did.
