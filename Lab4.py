"""Lab 4: Build a Signal-Based Strategy  (Lecture 5 — Strategy Families).

Implements all five strategies from the lecture and lets you pick one at launch:

  momentum:        MA Crossover, MACD
  mean reversion:  Bollinger Bands, Z-Score, VWAP fade

The chosen signal feeds the skeleton trading loop. Momentum strategies hold a
position until an opposite signal flips it; mean-reversion strategies close the
position when the signal returns to 0 (price back at the mean) — the exit rule
emphasised on slide 15.

SAFETY: this places real orders on the SHIFT simulation. The trader starts
ARMED but PAUSED — press SPACE to begin. Entry point used by main.py: run(trader).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Callable

import numpy as np
import shift
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, RichLog, Static

from UI import PortfolioPanel, PricePanel

NAME = "Strategy Lab"
IMPLEMENTED = True

SYMBOL = "AAPL"
HEARTBEAT = 1.0
SAMPLE_WINDOW = 60  # MACD needs slow+signal+2 = 37 samples, so keep a roomy buffer
MAX_LOTS = 3
BP_BUFFER = 0.9


# --- moving averages --------------------------------------------------------
def rolling_sma(prices: list[float], n: int) -> list[float]:
    return [float(np.mean(prices[i + 1 - n : i + 1])) for i in range(n - 1, len(prices))]


def ema_series(prices: list[float], span: int) -> list[float]:
    alpha = 2.0 / (span + 1)
    out = [prices[0]]
    for p in prices[1:]:
        out.append(alpha * p + (1 - alpha) * out[-1])
    return out


# --- signal functions (faithful to the lecture slides) ----------------------
def crossover_signal(prices: list[float], fast: int = 5, slow: int = 20) -> int:
    if len(prices) < slow + 1:
        return 0
    f, s = np.mean(prices[-fast:]), np.mean(prices[-slow:])
    fp, sp = np.mean(prices[-fast - 1 : -1]), np.mean(prices[-slow - 1 : -1])
    if fp < sp and f > s:
        return 1  # golden cross
    if fp > sp and f < s:
        return -1  # death cross
    return 0


def macd_lines(
    prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[float, float] | None:
    if len(prices) < slow + signal + 2:
        return None
    ema_fast, ema_slow = ema_series(prices, fast), ema_series(prices, slow)
    macd_line = [a - b for a, b in zip(ema_fast, ema_slow)]
    sig_line = ema_series(macd_line, signal)
    return macd_line, sig_line


def macd_signal(prices: list[float]) -> int:
    lines = macd_lines(prices)
    if lines is None:
        return 0
    macd_line, sig_line = lines
    if macd_line[-2] < sig_line[-2] and macd_line[-1] > sig_line[-1]:
        return 1
    if macd_line[-2] > sig_line[-2] and macd_line[-1] < sig_line[-1]:
        return -1
    return 0


def bollinger_signal(
    prices: list[float], n: int = 20, k: float = 2.0
) -> tuple[int, tuple[float, float, float] | None]:
    if len(prices) < n:
        return 0, None
    window = np.asarray(prices[-n:], dtype=float)
    mu, sigma = float(np.mean(window)), float(np.std(window))
    lower, upper = mu - k * sigma, mu + k * sigma
    cur = prices[-1]
    if cur <= lower:
        return 1, (lower, mu, upper)
    if cur >= upper:
        return -1, (lower, mu, upper)
    return 0, (lower, mu, upper)


def zscore_signal(
    prices: list[float], n: int = 20, entry: float = 1.5
) -> tuple[int, tuple[float, float, float] | None, float]:
    if len(prices) < n:
        return 0, None, 0.0
    window = np.asarray(prices[-n:], dtype=float)
    mu, sig = float(np.mean(window)), float(np.std(window))
    if sig == 0:
        return 0, (mu, mu, mu), 0.0
    z = (prices[-1] - mu) / sig
    bands = (mu - entry * sig, mu, mu + entry * sig)
    if z < -entry:
        return 1, bands, z
    if z > entry:
        return -1, bands, z
    return 0, bands, z


class VWAP:
    """Intraday cumulative VWAP with volume-weighted dispersion bands."""

    def __init__(self) -> None:
        self.cum_pv = 0.0
        self.cum_v = 0.0
        self.cum_pv2 = 0.0

    def update(self, price: float, volume: float) -> None:
        self.cum_pv += price * volume
        self.cum_v += volume
        self.cum_pv2 += price * price * volume

    def value(self) -> float | None:
        return self.cum_pv / self.cum_v if self.cum_v > 0 else None

    def bands(self, k: float = 2.0) -> tuple[float, float, float] | None:
        v = self.value()
        if v is None:
            return None
        var = max(self.cum_pv2 / self.cum_v - v * v, 0.0)
        sigma = sqrt(var)
        return v - k * sigma, v, v + k * sigma


# --- uniform strategy interface ---------------------------------------------
@dataclass
class StratResult:
    signal: int
    note: str = ""
    bands: tuple[float, float, float] | None = None  # (lower, mid, upper) -> hlines
    overlay: tuple[list[float], str] | None = None  # series -> chart line


def _c_crossover(prices, bp, vwap) -> StratResult:
    s = crossover_signal(prices)
    note, overlay = "warming up…", None
    if len(prices) >= 20:
        f, sl = float(np.mean(prices[-5:])), float(np.mean(prices[-20:]))
        note = f"fast {f:.2f}   slow {sl:.2f}"
        overlay = (rolling_sma(prices, 20), "SMA20")
    return StratResult(s, note, None, overlay)


def _c_macd(prices, bp, vwap) -> StratResult:
    s = macd_signal(prices)
    lines = macd_lines(prices)
    note = (
        f"macd {lines[0][-1]:+.3f}   signal {lines[1][-1]:+.3f}"
        if lines
        else "warming up…"
    )
    return StratResult(s, note)


def _c_bollinger(prices, bp, vwap) -> StratResult:
    s, bands = bollinger_signal(prices)
    note = f"px {prices[-1]:.2f}   [{bands[0]:.2f} … {bands[2]:.2f}]" if bands else "warming up…"
    return StratResult(s, note, bands)


def _c_zscore(prices, bp, vwap) -> StratResult:
    s, bands, z = zscore_signal(prices)
    return StratResult(s, f"z = {z:+.2f}" if bands else "warming up…", bands)


def _c_vwap(prices, bp, vwap) -> StratResult:
    bands = vwap.bands(2.0)
    if bands is None:
        return StratResult(0, "warming up…")
    bid, ask = bp.get_bid_price(), bp.get_ask_price()
    price = (bid + ask) / 2 if bid > 0 and ask > 0 else (prices[-1] if prices else 0.0)
    lower, mid, upper = bands
    s = 1 if price <= lower else -1 if price >= upper else 0
    return StratResult(s, f"px {price:.2f}   vwap {mid:.2f}", bands)


@dataclass
class Strategy:
    name: str
    kind: str  # "momentum" | "mean_reversion"
    desc: str
    compute: Callable[[list, object, VWAP], StratResult]


STRATEGY_ORDER = ["crossover", "macd", "bollinger", "zscore", "vwap"]
STRATEGIES: dict[str, Strategy] = {
    "crossover": Strategy("MA Crossover", "momentum", "Fast/slow SMA cross (5/20)", _c_crossover),
    "macd": Strategy("MACD", "momentum", "EMA12−EMA26 vs signal EMA9", _c_macd),
    "bollinger": Strategy("Bollinger Bands", "mean_reversion", "Buy lower band / sell upper (20, k=2)", _c_bollinger),
    "zscore": Strategy("Z-Score", "mean_reversion", "Fade |z| > 1.5 deviations (n=20)", _c_zscore),
    "vwap": Strategy("VWAP Fade", "mean_reversion", "Fade VWAP ± 2σ bands", _c_vwap),
}


# --- strategy picker (shown once, at launch) --------------------------------
class StrategySelectApp(App):
    """Returns the chosen strategy key, or None to go back to the menu."""

    TITLE = "Lab 4 · Choose a Strategy"

    CSS = """
    Screen { align: center middle; }
    #menu { width: 70; height: auto; border: round $primary; padding: 1 2; }
    #hint { text-align: center; color: $text-muted; padding-top: 1; }
    ListView { height: auto; background: $surface; }
    ListItem { padding: 0 1; }
    """

    BINDINGS = [("q", "quit", "Back"), ("escape", "quit", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="menu"):
            items = []
            for key in STRATEGY_ORDER:
                s = STRATEGIES[key]
                tag = "[cyan]momentum[/]" if s.kind == "momentum" else "[magenta]mean-rev[/]"
                items.append(
                    ListItem(
                        Label(f" [b]{s.name}[/b]  {tag}\n   [dim]{s.desc}[/dim]"),
                        id=f"strat-{key}",
                    )
                )
            yield ListView(*items, id="strats")
            yield Label("↑/↓ to move · Enter to run · q to go back", id="hint")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.exit(event.item.id.removeprefix("strat-"))


# --- status panel -----------------------------------------------------------
class StatusPanel(Static):
    DEFAULT_CSS = """
    StatusPanel { height: 9; border: round $secondary; padding: 0 1; }
    """

    def show(
        self, symbol, strat: Strategy, signal, trading, net, unreal, note
    ) -> None:
        sig_txt, sig_style = {
            1: ("▲ +1 BUY", "bold green"),
            -1: ("▼ -1 SELL", "bold red"),
            0: ("— 0 HOLD", "dim"),
        }[signal]
        state = (
            Text("TRADING", style="bold green")
            if trading
            else Text("ARMED · paused", style="bold yellow")
        )
        pos_style = "green" if net > 0 else "red" if net < 0 else "dim"
        pl_style = "green" if unreal >= 0 else "red"
        kind_tag = "momentum" if strat.kind == "momentum" else "mean-reversion"

        t = Text()
        t.append("  Strategy  ", style="dim")
        t.append(f"{strat.name}  ", style="bold magenta")
        t.append(f"({kind_tag})   ", style="dim")
        t.append("Symbol ", style="dim")
        t.append(f"{symbol}\n", style="bold")
        t.append("  Signal    ", style="dim")
        t.append(f"{sig_txt:<16}", style=sig_style)
        t.append("State  ", style="dim")
        t.append(state)
        t.append("\n  Position  ", style="dim")
        t.append(f"{net:+d} lots".ljust(16), style=f"bold {pos_style}")
        t.append("Unreal ", style="dim")
        t.append(f"${unreal:,.2f}\n", style=f"bold {pl_style}")
        t.append("  ", style="dim")
        t.append(note, style="cyan")
        self.update(t)


# --- live trader ------------------------------------------------------------
class StrategyTraderApp(App):
    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #left { width: 3fr; }
    #right { width: 2fr; }
    RichLog { height: 1fr; border: round $primary; }
    """

    BINDINGS = [
        ("q", "quit", "Back to menu"),
        ("space", "toggle", "Start/Stop"),
        ("f", "flatten", "Flatten"),
    ]

    def __init__(self, trader: shift.Trader, symbol: str, key: str) -> None:
        super().__init__()
        self.trader = trader
        self.symbol = symbol
        self.key = key
        self.strategy = STRATEGIES[key]
        self.vwap = VWAP()
        self.trading = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield StatusPanel(id="status")
                yield RichLog(id="log", markup=True, wrap=True)
            with Vertical(id="right"):
                yield PortfolioPanel(id="portfolio")
                yield PricePanel(id="chart")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"Lab 4 · {self.strategy.name}"
        self.sub_title = f"{self.symbol} · heartbeat {HEARTBEAT:g}s"
        self.query_one(RichLog).write(
            "[dim]Armed. Press [b]SPACE[/b] to start trading, [b]f[/b] to flatten, "
            "[b]q[/b] to pick another strategy.[/dim]"
        )
        self.set_interval(HEARTBEAT, self.tick)
        self.tick()

    def tick(self) -> None:
        self.heartbeat()

    @work(exclusive=True, thread=True)
    def heartbeat(self) -> None:
        t = self.trader
        bp = t.get_best_price(self.symbol)
        bid, ask = bp.get_bid_price(), bp.get_ask_price()
        prices = list(t.get_sample_prices(self.symbol, True))

        if self.key == "vwap":  # accumulate the latest trade print into VWAP
            last, vol = t.get_last_price(self.symbol), t.get_last_size(self.symbol)
            if last > 0 and vol > 0:
                self.vwap.update(last, vol)

        result = self.strategy.compute(prices, bp, self.vwap)

        item = t.get_portfolio_item(self.symbol)
        net = item.get_long_shares() - item.get_short_shares()
        ps = t.get_portfolio_summary()
        bp_avail = ps.get_total_bp()

        action = None
        if self.trading:
            action = self._execute(result.signal, self.strategy.kind, bid, ask, net, bp_avail)
            item = t.get_portfolio_item(self.symbol)
            net = item.get_long_shares() - item.get_short_shares()

        snap = {
            "prices": prices,
            "net": net,
            "unreal": t.get_unrealized_pl(self.symbol),
            "bp": bp_avail,
            "shares": ps.get_total_shares(),
            "realized": ps.get_total_realized_pl(),
            "ts": ps.get_timestamp(),
        }
        self.call_from_thread(self._apply, snap, result, action)

    def _execute(self, signal, kind, bid, ask, net, bp_avail):
        self.trader.cancel_all_pending_orders()
        if signal == 1:
            if net >= MAX_LOTS:
                return ("CAP", "long cap reached")
            if ask <= 0:
                return None
            if ask * 100 > bp_avail * BP_BUFFER:
                return ("SKIP", "insufficient buying power")
            self.trader.submit_order(
                shift.Order(shift.Order.LIMIT_BUY, self.symbol, 1, round(ask, 2))
            )
            return ("BUY", round(ask, 2))
        if signal == -1:
            if net <= -MAX_LOTS:
                return ("CAP", "short cap reached")
            if bid <= 0:
                return None
            self.trader.submit_order(
                shift.Order(shift.Order.LIMIT_SELL, self.symbol, 1, round(bid, 2))
            )
            return ("SELL", round(bid, 2))
        # mean-reversion exit: signal back to 0 -> close to the mean
        if kind == "mean_reversion" and net != 0:
            if net > 0:
                self.trader.submit_order(
                    shift.Order(shift.Order.MARKET_SELL, self.symbol, net)
                )
            else:
                self.trader.submit_order(
                    shift.Order(shift.Order.MARKET_BUY, self.symbol, abs(net))
                )
            return ("CLOSE", -net)
        return None

    def _apply(self, snap, result: StratResult, action) -> None:
        self.query_one(StatusPanel).show(
            self.symbol, self.strategy, result.signal,
            self.trading, snap["net"], snap["unreal"], result.note,
        )
        self.query_one(PortfolioPanel).update_summary(
            snap["bp"], snap["shares"], snap["realized"], snap["ts"]
        )

        title = f"{self.symbol} — mid price (1s samples)"
        chart = self.query_one(PricePanel)
        if result.bands is not None:
            lower, mid, upper = result.bands
            chart.draw(title, snap["prices"],
                       hlines=[(lower, "green"), (mid, "yellow"), (upper, "red")])
        else:
            chart.draw(title, snap["prices"], overlay=result.overlay)

        if action is not None:
            self._log(action)

    def _log(self, action) -> None:
        kind, detail = action
        now = datetime.now().strftime("%H:%M:%S")
        if kind == "BUY":
            color, msg = "green", f"BUY   1 @ {detail}"
        elif kind == "SELL":
            color, msg = "red", f"SELL  1 @ {detail}"
        elif kind == "CLOSE":
            color, msg = "cyan", f"CLOSE {detail:+d} lots → market (back to mean)"
        elif kind in ("SKIP", "CAP"):
            color, msg = "yellow", f"{kind} — {detail}"
        else:
            color, msg = "white", f"{kind} {detail}"
        self.query_one(RichLog).write(f"[dim]{now}[/dim]  [{color}]{msg}[/{color}]")

    # -- key actions ---------------------------------------------------------
    def action_toggle(self) -> None:
        self.trading = not self.trading
        if self.trading:
            self.notify("Trading STARTED", severity="warning")
            self.query_one(RichLog).write("[bold green]▶ Trading started[/]")
        else:
            self.notify("Trading paused")
            self.query_one(RichLog).write("[bold yellow]⏸ Trading paused[/]")

    def action_flatten(self) -> None:
        self.flatten()

    @work(thread=True)
    def flatten(self) -> None:
        item = self.trader.get_portfolio_item(self.symbol)
        net = item.get_long_shares() - item.get_short_shares()
        if net > 0:
            self.trader.submit_order(shift.Order(shift.Order.MARKET_SELL, self.symbol, net))
        elif net < 0:
            self.trader.submit_order(shift.Order(shift.Order.MARKET_BUY, self.symbol, abs(net)))
        if net != 0:
            self.call_from_thread(self._log, ("CLOSE", -net))


# --- lab entry point --------------------------------------------------------
def run(trader: shift.Trader) -> None:
    symbols = trader.get_stock_list()
    symbol = SYMBOL if SYMBOL in symbols else (sorted(symbols)[0] if symbols else None)
    if symbol is None:
        raise RuntimeError("No tradable symbols returned by the server.")

    key = StrategySelectApp().run()  # choose once, at launch
    if key is None:
        return  # user backed out -> return to the main menu

    trader.sub_order_book(symbol)
    trader.request_sample_prices(
        [symbol], sampling_frequency=1.0, sampling_window=SAMPLE_WINDOW
    )
    time.sleep(2)  # let the buffer begin filling

    try:
        StrategyTraderApp(trader, symbol, key).run()
    finally:
        trader.cancel_all_pending_orders()
