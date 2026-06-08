"""Lab 2: Build Your First Algorithm  (Lecture 3 — Vibe Coding).

Extends the 5-phase skeleton (connect → subscribe → decide → execute → monitor)
into a live trading strategy. Three switchable signals from the lab brief:

  * momentum       — buy when mid crosses above its 10-period SMA, sell below.
  * mean_reversion — buy when mid is >0.1% below its 20-period SMA, sell above.
  * imbalance      — buy when ask size > bid size x1.5, sell when reversed.

get_signal() returns +1 (buy) / -1 (sell) / 0 (hold); execute() cancels resting
orders then submits a 1-lot limit at the touch. Buying power and a position cap
guard every order.

SAFETY: this places real orders on the SHIFT simulation. The app starts ARMED
but PAUSED — press SPACE to begin trading. Entry point used by main.py: run(trader).
"""
from __future__ import annotations

import time
from datetime import datetime

import shift
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog, Static

from UI import PortfolioPanel, PricePanel

NAME = "First Algorithm"
IMPLEMENTED = True

SYMBOL = "AAPL"
HEARTBEAT = 2.0  # seconds between decisions
SAMPLE_WINDOW = 30  # rolling sample-price buffer length
MAX_POSITION = 5  # lots, long or short
BP_BUFFER = 0.9  # use at most 90% of buying power on a buy


# --- signal functions: (prices, mid, best_price) -> +1 / -1 / 0 -------------
def momentum_signal(prices: list[float], mid: float, bp) -> int:
    if len(prices) < 10:
        return 0
    sma10 = sum(prices[-10:]) / 10
    return 1 if mid > sma10 else -1 if mid < sma10 else 0


def mean_reversion_signal(prices: list[float], mid: float, bp) -> int:
    if len(prices) < 20:
        return 0
    sma20 = sum(prices[-20:]) / 20
    if mid < sma20 * (1 - 0.001):
        return 1
    if mid > sma20 * (1 + 0.001):
        return -1
    return 0


def imbalance_signal(prices: list[float], mid: float, bp) -> int:
    bid_sz, ask_sz = bp.get_bid_size(), bp.get_ask_size()
    if ask_sz > bid_sz * 1.5:
        return 1
    if bid_sz > ask_sz * 1.5:
        return -1
    return 0


STRATEGIES = {
    "momentum": (momentum_signal, 10),
    "mean_reversion": (mean_reversion_signal, 20),
    "imbalance": (imbalance_signal, None),
}
STRATEGY_KEYS = ["momentum", "mean_reversion", "imbalance"]


def rolling_mean(values: list[float], period: int) -> list[float]:
    """SMA at every point with enough history (for the chart overlay)."""
    return [
        sum(values[i + 1 - period : i + 1]) / period
        for i in range(period - 1, len(values))
    ]


class StatusPanel(Static):
    """Strategy, signal, trading state, and live position."""

    DEFAULT_CSS = """
    StatusPanel { height: 8; border: round $secondary; padding: 0 1; }
    """

    def show(
        self,
        symbol: str,
        strategy: str,
        signal: int,
        trading: bool,
        net: int,
        unreal: float,
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

        t = Text()
        t.append("  Strategy  ", style="dim")
        t.append(f"{strategy.upper():<16}", style="bold magenta")
        t.append("Symbol ", style="dim")
        t.append(f"{symbol}\n", style="bold")
        t.append("  Signal    ", style="dim")
        t.append(f"{sig_txt:<16}", style=sig_style)
        t.append("State  ", style="dim")
        t.append(state)
        t.append("\n  Position  ", style="dim")
        t.append(f"{net:+d} lots".ljust(16), style=f"bold {pos_style}")
        t.append("Unreal ", style="dim")
        t.append(f"${unreal:,.2f}", style=f"bold {pl_style}")
        self.update(t)


class TradingApp(App):
    """Live algorithmic trader for a single symbol."""

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
        ("1", "set_strategy('momentum')", "Momentum"),
        ("2", "set_strategy('mean_reversion')", "Mean-rev"),
        ("3", "set_strategy('imbalance')", "Imbalance"),
    ]

    def __init__(self, trader: shift.Trader, symbol: str) -> None:
        super().__init__()
        self.trader = trader
        self.symbol = symbol
        self.strategy = "momentum"
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
        self.title = "Lab 2 · First Algorithm"
        self.sub_title = f"{self.symbol} · heartbeat {HEARTBEAT:g}s"
        log = self.query_one(RichLog)
        log.write("[dim]Armed. Press [b]SPACE[/b] to start trading, "
                  "[b]1/2/3[/b] to switch strategy, [b]f[/b] to flatten.[/dim]")
        self.set_interval(HEARTBEAT, self.tick)
        self.tick()

    # -- heartbeat -----------------------------------------------------------
    def tick(self) -> None:
        self.heartbeat()

    @work(exclusive=True, thread=True)
    def heartbeat(self) -> None:
        """Worker thread: read market, decide, (maybe) trade, refresh UI."""
        t = self.trader
        bp = t.get_best_price(self.symbol)
        bid, ask = bp.get_bid_price(), bp.get_ask_price()
        prices = list(t.get_sample_prices(self.symbol, True))  # mid prices
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else (prices[-1] if prices else 0.0)

        signal_fn = STRATEGIES[self.strategy][0]
        signal = signal_fn(prices, mid, bp)

        item = t.get_portfolio_item(self.symbol)
        net = item.get_shares()
        ps = t.get_portfolio_summary()
        bp_avail = ps.get_total_bp()

        action = None
        if self.trading:
            action = self._execute(signal, bid, ask, net, bp_avail)
            net = t.get_portfolio_item(self.symbol).get_shares()  # refresh post-trade

        snap = {
            "prices": prices,
            "signal": signal,
            "net": net,
            "unreal": t.get_unrealized_pl(self.symbol),
            "bp": bp_avail,
            "shares": ps.get_total_shares(),
            "realized": ps.get_total_realized_pl(),
            "ts": ps.get_timestamp(),
        }
        self.call_from_thread(self._apply, snap, action)

    def _execute(self, signal: int, bid: float, ask: float, net: int, bp_avail: float):
        """Cancel resting orders, then place a 1-lot limit at the touch."""
        self.trader.cancel_all_pending_orders()
        if signal == 1:
            if net >= MAX_POSITION:
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
            if net <= -MAX_POSITION:
                return ("CAP", "short cap reached")
            if bid <= 0:
                return None
            self.trader.submit_order(
                shift.Order(shift.Order.LIMIT_SELL, self.symbol, 1, round(bid, 2))
            )
            return ("SELL", round(bid, 2))
        return None

    def _apply(self, snap: dict, action) -> None:
        self.query_one(StatusPanel).show(
            self.symbol, self.strategy, snap["signal"],
            self.trading, snap["net"], snap["unreal"],
        )
        self.query_one(PortfolioPanel).update_summary(
            snap["bp"], snap["shares"], snap["realized"], snap["ts"]
        )

        period = STRATEGIES[self.strategy][1]
        overlay = None
        if period is not None and len(snap["prices"]) >= period:
            overlay = (rolling_mean(snap["prices"], period), f"SMA{period}")
        self.query_one(PricePanel).draw(
            f"{self.symbol} — mid price (1s samples)", snap["prices"], overlay
        )

        if action is not None:
            self._log(action)

    def _log(self, action) -> None:
        kind, detail = action
        now = datetime.now().strftime("%H:%M:%S")
        if kind == "BUY":
            color, msg = "green", f"BUY  1 @ {detail}"
        elif kind == "SELL":
            color, msg = "red", f"SELL 1 @ {detail}"
        elif kind == "SKIP":
            color, msg = "yellow", f"SKIP — {detail}"
        elif kind == "CAP":
            color, msg = "yellow", f"HELD — {detail}"
        elif kind == "FLATTEN":
            color, msg = "cyan", f"FLATTEN {detail:+d} lots → market"
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

    def action_set_strategy(self, name: str) -> None:
        if name in STRATEGIES:
            self.strategy = name
            self.query_one(RichLog).write(f"[magenta]strategy → {name.upper()}[/]")

    def action_flatten(self) -> None:
        self.flatten()

    @work(thread=True)
    def flatten(self) -> None:
        net = self.trader.get_portfolio_item(self.symbol).get_shares()
        if net > 0:
            self.trader.submit_order(
                shift.Order(shift.Order.MARKET_SELL, self.symbol, net)
            )
        elif net < 0:
            self.trader.submit_order(
                shift.Order(shift.Order.MARKET_BUY, self.symbol, abs(net))
            )
        if net != 0:
            self.call_from_thread(self._log, ("FLATTEN", net))


# --- lab entry point --------------------------------------------------------
def run(trader: shift.Trader) -> None:
    """Subscribe to the symbol, start sampling, then launch the trading UI."""
    symbols = trader.get_stock_list()
    symbol = SYMBOL if SYMBOL in symbols else (sorted(symbols)[0] if symbols else None)
    if symbol is None:
        raise RuntimeError("No tradable symbols returned by the server.")

    trader.sub_order_book(symbol)
    trader.request_sample_prices(
        [symbol], sampling_frequency=1.0, sampling_window=SAMPLE_WINDOW
    )
    time.sleep(2)  # let the buffer begin filling

    try:
        TradingApp(trader, symbol).run()
    finally:
        # Leave a clean book behind when returning to the menu.
        trader.cancel_all_pending_orders()
