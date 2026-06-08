"""Lab 5: Market Maker with Inventory Control  (Lecture 6 — Market Making).

A two-sided market maker built on the Avellaneda-Stoikov idea: post a bid and an
ask around a *reservation price* that is skewed toward zero inventory, with a
spread that widens with volatility and inventory.

Two quoting modes you can flip between live (key `m`) to compare, per the lab:
  * basic       — reservation_price() + quote_spread()      (slide 8 skeleton)
  * inventory   — inventory_skew() + adaptive_spread()      (slide 11)

Inventory control on top:
  * one-sided quoting with hysteresis — stop quoting the bid when inventory > +3,
    stop the ask when < -3, resume both within [-2, +2] (the vibe-coding task);
  * optional flat-position exit (key `e`) — market-flatten when |inventory| > 4.

Risk engine readout: equity curve, max drawdown, Sharpe and Sortino (raw, not
annualised — HFT annualisation is fragile), inventory excursions.

SAFETY: places real orders on the SHIFT simulation. Starts ARMED but PAUSED —
press SPACE to begin. Entry point used by main.py: run(trader).
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import shift
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog, Static

from UI import PricePanel

NAME = "Market Maker"
IMPLEMENTED = True

SYMBOL = "AAPL"
GAMMA = 0.01  # risk aversion
MAX_INV = 5  # max inventory (lots)
BASE_SPREAD = 0.04  # 4 cents
SKEW_FACTOR = 0.02  # inventory_skew strength
INV_PENALTY = 0.01  # adaptive_spread inventory penalty
VOL_SCALE = 100.0  # adaptive_spread volatility -> dollars scaling
SESSION_T = 600.0  # nominal session length (seconds) for the AS time term
HEARTBEAT = 1.0
SAMPLE_WINDOW = 30
HISTORY = 300  # points kept for the charts / metrics


# --- quoting maths (faithful to the lecture slides) -------------------------
def reservation_price(mid, inventory, sigma, t_remaining, gamma=GAMMA):
    """Skew the mid away from inventory: long -> quote lower, short -> higher."""
    return mid - inventory * gamma * (sigma ** 2) * t_remaining


def quote_spread(sigma, t_remaining, gamma=GAMMA, base_spread=BASE_SPREAD):
    vol_component = gamma * (sigma ** 2) * t_remaining
    return max(base_spread, base_spread + vol_component)


def inventory_skew(inv, mid, max_inv=MAX_INV, skew_factor=SKEW_FACTOR):
    """Reservation price shifted toward reducing inventory."""
    skew = -(inv / max_inv) * skew_factor * mid
    return mid + skew


def adaptive_spread(
    sigma, inv, mid, max_inv=MAX_INV, base=BASE_SPREAD, inv_penalty=INV_PENALTY
):
    """Wider when volatility is high OR inventory is large."""
    vol_addon = VOL_SCALE * sigma * mid
    inv_addon = (abs(inv) / max_inv) * inv_penalty * mid
    return max(base, base + vol_addon + inv_addon)


def realized_vol(prices) -> float:
    """Std of log returns over the last 20 samples (else a small floor)."""
    if len(prices) >= 21:
        return float(np.std(np.diff(np.log(prices[-20:]))))
    return 0.001


# --- risk metrics (faithful to the lecture slides) --------------------------
def max_drawdown(equity) -> float:
    """Largest peak-to-trough drop of the equity curve, as a fraction."""
    if len(equity) < 2:
        return 0.0
    eq = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak == 0, 1, peak)
    return float(dd.max())


def sharpe_ratio(returns, rf=0.0, periods_per_year=1) -> float:
    if len(returns) < 2:
        return 0.0
    r = np.asarray(returns, dtype=float) - rf
    sd = r.std(ddof=1)
    return float(np.sqrt(periods_per_year) * r.mean() / sd) if sd > 0 else 0.0


def sortino_ratio(returns, rf=0.0, periods_per_year=1) -> float:
    if len(returns) < 2:
        return 0.0
    r = np.asarray(returns, dtype=float) - rf
    downside = r[r < 0]
    dd = np.sqrt(np.mean(downside ** 2)) if downside.size > 0 else 0.0
    return float(np.sqrt(periods_per_year) * r.mean() / dd) if dd > 0 else 0.0


# --- panels -----------------------------------------------------------------
class QuotePanel(Static):
    """Live quotes, inventory, and which sides are active."""

    DEFAULT_CSS = """
    QuotePanel { height: 7; border: round $secondary; padding: 0 1; }
    """

    def show(self, mode, mid, r, spread, bid_q, ask_q, inv, q_bid, q_ask,
             flat_exit, trading) -> None:
        state = (
            Text("TRADING", style="bold green")
            if trading
            else Text("ARMED · paused", style="bold yellow")
        )
        inv_style = "red" if abs(inv) >= MAX_INV else "yellow" if abs(inv) >= 3 else "green"
        bid_txt = Text(f"{bid_q:.2f}", style="green" if q_bid else "dim strike")
        ask_txt = Text(f"{ask_q:.2f}", style="red" if q_ask else "dim strike")

        t = Text()
        t.append("  Mode ", style="dim")
        t.append(f"{mode:<12}", style="bold magenta")
        t.append("State ", style="dim")
        t.append(state)
        t.append("   flat-exit ", style="dim")
        t.append("on" if flat_exit else "off", style="cyan" if flat_exit else "dim")
        t.append("\n  Quote   ", style="dim")
        t.append("BID ", style="dim")
        t.append(bid_txt)
        t.append("  ", style="dim")
        t.append("ASK ", style="dim")
        t.append(ask_txt)
        t.append(f"   spread ${spread:.2f}", style="yellow")
        t.append("\n  Mid ", style="dim")
        t.append(f"{mid:.2f}", style="bold")
        t.append("   resv ", style="dim")
        t.append(f"{r:.2f}", style="bold")
        t.append("   Inventory ", style="dim")
        t.append(f"{inv:+d}/{MAX_INV} lots", style=f"bold {inv_style}")
        self.update(t)


class RiskPanel(Static):
    """SHIFT risk-engine style readout: equity, drawdown, risk-adjusted return."""

    DEFAULT_CSS = """
    RiskPanel { height: 10; border: round $accent; padding: 0 1; }
    """

    def show(self, realized, unreal, mdd, sharpe, sortino, max_abs_inv,
             inv_hits, t_rem) -> None:
        pnl = realized + unreal
        pnl_style = "green" if pnl >= 0 else "red"
        t = Text()
        t.append("  Risk Engine\n\n", style="bold")
        t.append("  Total P&L    ", style="dim")
        t.append(f"${pnl:,.2f}", style=f"bold {pnl_style}")
        t.append(f"   (real ${realized:,.2f} · unreal ${unreal:,.2f})\n", style="dim")
        t.append("  Max drawdown ", style="dim")
        t.append(f"{mdd * 100:.2f}%\n", style="bold red" if mdd > 0.05 else "bold")
        t.append("  Sharpe ", style="dim")
        t.append(f"{sharpe:+.2f}", style="bold")
        t.append("   Sortino ", style="dim")
        t.append(f"{sortino:+.2f}", style="bold")
        t.append("   [dim](raw)[/]\n", style="dim")
        t.append("  Max |inv|    ", style="dim")
        t.append(f"{max_abs_inv} lots", style="bold")
        t.append("   MAX_INV hits ", style="dim")
        t.append(f"{inv_hits}\n", style="bold yellow" if inv_hits else "bold")
        t.append("  Time left    ", style="dim")
        t.append(f"{int(t_rem)}s", style="bold")
        self.update(t)


# --- app --------------------------------------------------------------------
class MarketMakerApp(App):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #left { width: 2fr; }
    #right { width: 3fr; }
    RichLog { height: 1fr; border: round $primary; }
    """

    BINDINGS = [
        ("q", "quit", "Back to menu"),
        ("space", "toggle", "Start/Stop"),
        ("m", "mode", "Mode"),
        ("e", "flat_exit", "Flat-exit"),
        ("f", "flatten", "Flatten now"),
    ]

    def __init__(self, trader: shift.Trader, symbol: str) -> None:
        super().__init__()
        self.trader = trader
        self.symbol = symbol
        self.mode = "basic"  # or "inventory"
        self.trading = False
        self.flat_exit = False
        # one-sided quoting state (hysteresis)
        self.quote_bid = True
        self.quote_ask = True
        # history / metrics
        self.start = 0.0
        self.equity0: float | None = None
        self.equity: list[float] = []
        self.inv_history: list[float] = []
        self.max_abs_inv = 0
        self.inv_hits = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield QuotePanel(id="quote")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield RiskPanel(id="risk")
                    yield RichLog(id="log", markup=True, wrap=True)
                with Vertical(id="right"):
                    yield PricePanel(id="chart")
                    yield PricePanel(id="invchart")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Lab 5 · Market Maker"
        self.sub_title = f"{self.symbol} · γ={GAMMA} · MAX_INV={MAX_INV}"
        self.start = time.time()
        self.query_one(RichLog).write(
            "[dim]Armed. [b]SPACE[/b] start/stop · [b]m[/b] basic⇄inventory · "
            "[b]e[/b] flat-exit · [b]f[/b] flatten · [b]q[/b] back.[/dim]"
        )
        self.set_interval(HEARTBEAT, self.tick)
        self.tick()

    def tick(self) -> None:
        self.heartbeat()

    # -- one-sided quoting with hysteresis ----------------------------------
    def _update_quote_sides(self, inv: int) -> None:
        if inv >= 3:
            self.quote_bid = False
        if inv <= -3:
            self.quote_ask = False
        if -2 <= inv <= 2:
            self.quote_bid = self.quote_ask = True

    @work(exclusive=True, thread=True)
    def heartbeat(self) -> None:
        t = self.trader
        elapsed = time.time() - self.start
        t_rem = max(SESSION_T - elapsed, 0.0)

        bp = t.get_best_price(self.symbol)
        bid, ask = bp.get_bid_price(), bp.get_ask_price()
        prices = list(t.get_sample_prices(self.symbol, True))
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else (prices[-1] if prices else 0.0)
        sigma = realized_vol(prices)

        item = t.get_portfolio_item(self.symbol)
        inv = item.get_long_shares() - item.get_short_shares()

        # reservation price + spread for the active mode
        if self.mode == "inventory":
            r = inventory_skew(inv, mid)
            spread = adaptive_spread(sigma, inv, mid)
        else:
            r = reservation_price(mid, inv, sigma, t_rem)
            spread = quote_spread(sigma, t_rem)
        bid_q = round(r - spread / 2, 2)
        ask_q = round(r + spread / 2, 2)

        ps = t.get_portfolio_summary()
        bp_avail = ps.get_total_bp()

        action = None
        if self.trading and mid > 0 and len(prices) >= 10:
            action = self._quote(inv, bid_q, ask_q, bp_avail, t_rem)
            item = t.get_portfolio_item(self.symbol)
            inv = item.get_long_shares() - item.get_short_shares()

        snap = {
            "mid": mid, "r": r, "spread": spread, "bid_q": bid_q, "ask_q": ask_q,
            "inv": inv, "prices": prices, "t_rem": t_rem,
            "realized": ps.get_total_realized_pl(),
            "unreal": t.get_unrealized_pl(self.symbol),
            "bp": bp_avail,
        }
        self.call_from_thread(self._apply, snap, action)

    def _quote(self, inv, bid_q, ask_q, bp_avail, t_rem):
        """Cancel, then (re)post both sides subject to inventory control."""
        self.trader.cancel_all_pending_orders()

        if t_rem <= 0:  # session over -> stop quoting, flatten
            self.call_from_thread(self._auto_stop)
            return self._flatten_now(inv)

        if self.flat_exit and abs(inv) > 4:
            return self._flatten_now(inv)

        self._update_quote_sides(inv)
        posted = []
        if self.quote_bid and inv < MAX_INV and bid_q > 0:
            if bid_q * 100 <= bp_avail * 0.9:
                self.trader.submit_order(
                    shift.Order(shift.Order.LIMIT_BUY, self.symbol, 1, bid_q)
                )
                posted.append(f"bid {bid_q:.2f}")
        if self.quote_ask and inv > -MAX_INV and ask_q > 0:
            self.trader.submit_order(
                shift.Order(shift.Order.LIMIT_SELL, self.symbol, 1, ask_q)
            )
            posted.append(f"ask {ask_q:.2f}")
        return ("QUOTE", " · ".join(posted) if posted else "one-sided pause")

    def _flatten_now(self, inv):
        if inv > 0:
            self.trader.submit_order(shift.Order(shift.Order.MARKET_SELL, self.symbol, inv))
        elif inv < 0:
            self.trader.submit_order(shift.Order(shift.Order.MARKET_BUY, self.symbol, abs(inv)))
        return ("FLATTEN", -inv) if inv != 0 else None

    def _auto_stop(self) -> None:
        if self.trading:
            self.trading = False
            self.query_one(RichLog).write("[bold yellow]⏹ Session over — stopped.[/]")

    # -- UI update -----------------------------------------------------------
    def _apply(self, snap, action) -> None:
        inv = snap["inv"]
        self.inv_history.append(inv)
        self.inv_history = self.inv_history[-HISTORY:]
        self.max_abs_inv = max(self.max_abs_inv, abs(inv))
        if abs(inv) >= MAX_INV:
            self.inv_hits += 1

        if self.equity0 is None:
            self.equity0 = snap["bp"]
        self.equity.append(self.equity0 + snap["realized"] + snap["unreal"])
        self.equity = self.equity[-HISTORY:]
        returns = list(np.diff(self.equity) / np.asarray(self.equity[:-1])) if len(self.equity) > 1 else []

        self.query_one(QuotePanel).show(
            self.mode, snap["mid"], snap["r"], snap["spread"], snap["bid_q"],
            snap["ask_q"], inv, self.quote_bid, self.quote_ask,
            self.flat_exit, self.trading,
        )
        self.query_one(RiskPanel).show(
            snap["realized"], snap["unreal"], max_drawdown(self.equity),
            sharpe_ratio(returns), sortino_ratio(returns),
            self.max_abs_inv, self.inv_hits, snap["t_rem"],
        )

        self.query_one("#chart", PricePanel).draw(
            f"{self.symbol} — mid + quotes", snap["prices"],
            hlines=[(snap["bid_q"], "green"), (snap["ask_q"], "red"), (snap["r"], "yellow")],
        )
        self.query_one("#invchart", PricePanel).draw(
            "inventory (lots)", self.inv_history,
            hlines=[(MAX_INV, "red"), (-MAX_INV, "green"), (0, "yellow")],
        )

        if action is not None:
            self._log(action)

    def _log(self, action) -> None:
        kind, detail = action
        now = datetime.now().strftime("%H:%M:%S")
        if kind == "QUOTE":
            color, msg = "blue", f"quote  {detail}"
        elif kind == "FLATTEN":
            color, msg = "cyan", f"FLATTEN {detail:+d} lots → market"
        else:
            color, msg = "white", f"{kind} {detail}"
        self.query_one(RichLog).write(f"[dim]{now}[/dim]  [{color}]{msg}[/{color}]")

    # -- key actions ---------------------------------------------------------
    def action_toggle(self) -> None:
        self.trading = not self.trading
        if self.trading:
            self.notify("Quoting STARTED", severity="warning")
            self.query_one(RichLog).write("[bold green]▶ Quoting started[/]")
        else:
            self.notify("Quoting paused")
            self.query_one(RichLog).write("[bold yellow]⏸ Quoting paused[/]")

    def action_mode(self) -> None:
        self.mode = "inventory" if self.mode == "basic" else "basic"
        self.query_one(RichLog).write(f"[magenta]mode → {self.mode}[/]")

    def action_flat_exit(self) -> None:
        self.flat_exit = not self.flat_exit
        self.query_one(RichLog).write(
            f"[cyan]flat-exit {'on' if self.flat_exit else 'off'}[/]"
        )

    def action_flatten(self) -> None:
        self.flatten()

    @work(thread=True)
    def flatten(self) -> None:
        item = self.trader.get_portfolio_item(self.symbol)
        inv = item.get_long_shares() - item.get_short_shares()
        self.trader.cancel_all_pending_orders()
        action = self._flatten_now(inv)
        if action:
            self.call_from_thread(self._log, action)


# --- lab entry point --------------------------------------------------------
def run(trader: shift.Trader) -> None:
    symbols = trader.get_stock_list()
    symbol = SYMBOL if SYMBOL in symbols else (sorted(symbols)[0] if symbols else None)
    if symbol is None:
        raise RuntimeError("No tradable symbols returned by the server.")

    trader.sub_order_book(symbol)
    trader.request_sample_prices(
        [symbol], sampling_frequency=1.0, sampling_window=SAMPLE_WINDOW
    )
    time.sleep(2)

    try:
        MarketMakerApp(trader, symbol).run()
    finally:
        trader.cancel_all_pending_orders()
