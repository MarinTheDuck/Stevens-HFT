"""Lab 1: Market Monitor  (Lecture 2 — Python & the SHIFT API).

A live, once-per-second market summary:
  * list of available symbols with best bid / ask / spread / last price,
  * a 5-period SMA with an ABOVE/BELOW signal vs the current mid price,
  * the account portfolio summary,
  * a plotext price chart for the highlighted symbol.

Entry point used by main.py:  ``run(trader)``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import shift
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header

from UI import PortfolioPanel, PricePanel

NAME = "Market Monitor"
IMPLEMENTED = True

SMA_PERIOD = 5
SAMPLE_WINDOW = 60  # seconds of 1-second samples SHIFT keeps in its buffer
REFRESH_SECONDS = 1.0


# --- signal maths -----------------------------------------------------------
def sma(values: list[float], period: int = SMA_PERIOD) -> float | None:
    """Simple moving average of the last `period` values, or None if too short."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rolling_sma(values: list[float], period: int = SMA_PERIOD) -> list[float]:
    """SMA at every point where enough history exists (for the chart overlay)."""
    out: list[float] = []
    for i in range(period - 1, len(values)):
        out.append(sum(values[i + 1 - period : i + 1]) / period)
    return out


@dataclass
class SymbolRow:
    """One snapshot of market data for a single ticker."""

    symbol: str
    company: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    sma5: float | None = None
    samples: list[float] = field(default_factory=list)

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last

    @property
    def signal(self) -> str:
        """ABOVE / BELOW the 5-period SMA, or '—' while the buffer fills."""
        if self.sma5 is None or self.mid <= 0:
            return "—"
        return "ABOVE" if self.mid >= self.sma5 else "BELOW"


@dataclass
class Snapshot:
    """Everything the UI needs for one refresh — gathered off the UI thread."""

    rows: list[SymbolRow]
    bp: float
    total_shares: int
    realized_pl: float
    timestamp: datetime | None


# --- the app ----------------------------------------------------------------
class MarketMonitor(App):
    """Live SHIFT market monitor."""

    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #table { width: 3fr; border: round $primary; }
    #side  { width: 2fr; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        ("q", "quit", "Quit (disconnect)"),
        ("r", "refresh", "Refresh now"),
    ]

    COLUMNS = [
        ("Symbol", "symbol"),
        ("Company", "company"),
        ("Bid", "bid"),
        ("Ask", "ask"),
        ("Spread", "spread"),
        ("Last", "last"),
        (f"SMA{SMA_PERIOD}", "sma5"),
        ("Signal", "signal"),
    ]

    def __init__(self, trader: shift.Trader, symbols: list[str]) -> None:
        super().__init__()
        self.trader = trader
        self.symbols = symbols
        self._rows: dict[str, SymbolRow] = {}
        self._selected: str | None = symbols[0] if symbols else None

    # -- layout --------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            yield DataTable(id="table", zebra_stripes=True, cursor_type="row")
            with Vertical(id="side"):
                yield PortfolioPanel(id="portfolio")
                yield PricePanel(id="chart")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "SHIFT Market Monitor"
        self.sub_title = f"{self.trader.username}  ·  {len(self.symbols)} symbols"
        table = self.query_one(DataTable)
        for label, key in self.COLUMNS:
            table.add_column(label, key=key)
        for sym in self.symbols:
            table.add_row(*([sym] + [""] * (len(self.COLUMNS) - 1)), key=sym)
        self.set_interval(REFRESH_SECONDS, self.action_refresh)
        self.action_refresh()

    # -- refresh cycle -------------------------------------------------------
    def action_refresh(self) -> None:
        """Kick off a background read of the API (keeps the UI responsive)."""
        self.gather_snapshot()

    @work(exclusive=True, thread=True)
    def gather_snapshot(self) -> None:
        """Worker thread: pull data from SHIFT, then hand it to the UI thread."""
        rows: list[SymbolRow] = []
        for sym in self.symbols:
            bp = self.trader.get_best_price(sym)
            samples = list(self.trader.get_sample_prices(sym, True))  # mid prices
            rows.append(
                SymbolRow(
                    symbol=sym,
                    company=self.trader.get_company_name(sym),
                    bid=bp.get_bid_price(),
                    ask=bp.get_ask_price(),
                    last=self.trader.get_last_price(sym),
                    sma5=sma(samples),
                    samples=samples,
                )
            )

        ps = self.trader.get_portfolio_summary()
        snap = Snapshot(
            rows=rows,
            bp=ps.get_total_bp(),
            total_shares=ps.get_total_shares(),
            realized_pl=ps.get_total_realized_pl(),
            timestamp=ps.get_timestamp(),
        )
        # plotext + Textual widgets must be touched on the UI thread:
        self.call_from_thread(self.apply_snapshot, snap)

    def apply_snapshot(self, snap: Snapshot) -> None:
        table = self.query_one(DataTable)
        for row in snap.rows:
            self._rows[row.symbol] = row
            self._update_table_row(table, row)

        self.query_one(PortfolioPanel).update_summary(
            snap.bp, snap.total_shares, snap.realized_pl, snap.timestamp
        )
        self._draw_chart()

    def _update_table_row(self, table: DataTable, row: SymbolRow) -> None:
        def price(v: float) -> Text:
            return Text(f"{v:,.2f}" if v > 0 else "—", justify="right")

        if row.signal == "ABOVE":
            signal = Text("▲ ABOVE", style="bold green")
        elif row.signal == "BELOW":
            signal = Text("▼ BELOW", style="bold red")
        else:
            signal = Text("—", style="dim")

        spread = Text(
            f"{row.spread:,.2f}" if row.ask > 0 and row.bid > 0 else "—",
            style="yellow",
            justify="right",
        )
        company = Text(row.company[:22] if row.company else "—", overflow="ellipsis")
        sma_txt = Text(
            f"{row.sma5:,.2f}" if row.sma5 is not None else "—", justify="right"
        )

        table.update_cell(row.symbol, "company", company)
        table.update_cell(row.symbol, "bid", price(row.bid))
        table.update_cell(row.symbol, "ask", price(row.ask))
        table.update_cell(row.symbol, "spread", spread)
        table.update_cell(row.symbol, "last", price(row.last))
        table.update_cell(row.symbol, "sma5", sma_txt)
        table.update_cell(row.symbol, "signal", signal)

    # -- chart ---------------------------------------------------------------
    def _draw_chart(self) -> None:
        chart = self.query_one(PricePanel)
        row = self._rows.get(self._selected) if self._selected else None
        if row is None:
            chart.draw("", [])
            return
        chart.draw(
            f"{row.symbol} — mid price (1s samples)",
            row.samples,
            (rolling_sma(row.samples), f"SMA{SMA_PERIOD}"),
        )

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        self._selected = str(event.row_key.value)
        self._draw_chart()


# --- lab entry point --------------------------------------------------------
def run(trader: shift.Trader) -> None:
    """Set up the market-data feeds this lab needs, then launch the TUI."""
    import time

    trader.sub_all_order_book()  # subscribe to every LOB stream
    trader.request_company_names()  # company names, once at startup

    symbols = sorted(trader.get_stock_list())
    if not symbols:
        raise RuntimeError("No tradable symbols returned by the server.")

    # Start SHIFT's rolling sample-price buffer so the SMA has data to chew on.
    trader.request_sample_prices(
        symbols, sampling_frequency=1.0, sampling_window=SAMPLE_WINDOW
    )
    time.sleep(2)  # let the buffer begin filling

    MarketMonitor(trader, symbols).run()
