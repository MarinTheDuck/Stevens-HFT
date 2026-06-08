"""Lab 3: Triple Barrier Labelling  (Lecture 4 — Core Strategy Elements).

Applies the Triple Barrier Method (Lopez de Prado) to real SHIFT mid-price
series and analyses the resulting label distribution:

  * Each entry gets +1 if an upper barrier (take-profit) is hit first,
    -1 if a lower barrier (stop-loss) is hit first, or 0 if the vertical
    barrier (time limit T) expires first.
  * Barrier widths are volatility-scaled: h = p0 * (1 +/- c * sigma).

The app collects ~200 mid prices for TWO symbols and rebuilds the distribution
live as the buffer fills, comparing c = 0.5 / 1.5 / 3.0. The extension computes
price-based features at each entry and correlates them with the label.

Entry point used by main.py: run(trader).
"""
from __future__ import annotations

import time
from collections import Counter

import numpy as np
import shift
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from UI import PricePanel

NAME = "Triple Barrier"
IMPLEMENTED = True

VOL_WINDOW = 20  # periods for the rolling volatility estimate
T_VERTICAL = 30  # vertical barrier (time limit) in periods
C_VALUES = [0.5, 1.5, 3.0]  # barrier-width multipliers to compare
TARGET_SAMPLES = 200
FEATURES = ("sma_ratio", "trend", "volatility", "momentum")


# --- core triple-barrier maths (faithful to the lecture slides) -------------
def compute_volatility(prices: list[float], window: int = VOL_WINDOW) -> float | None:
    """Rolling std of log returns over the last `window` periods."""
    if len(prices) < window + 1:
        return None
    p = np.asarray(prices[-(window + 1):], dtype=float)
    if np.any(p <= 0):
        return None
    log_rets = np.log(p[1:] / p[:-1])
    return float(np.std(log_rets))


def label_entry(
    prices: list[float], t0: int, h_up: float, h_down: float, T: int
) -> int:
    """+1 if the upper barrier is hit first, -1 lower, 0 if time runs out."""
    for t in range(t0 + 1, min(t0 + T + 1, len(prices))):
        p = prices[t]
        if p >= h_up:
            return 1
        if p <= h_down:
            return -1
    return 0


def apply_triple_barrier(
    prices: list[float],
    c: float = 1.5,
    T: int = T_VERTICAL,
    vol_window: int = VOL_WINDOW,
) -> list[tuple[int, float, int]]:
    """Label every viable entry. Returns (index, entry_price, label) tuples."""
    results: list[tuple[int, float, int]] = []
    for t0 in range(vol_window, len(prices) - T):
        p0 = prices[t0]
        sigma = compute_volatility(prices[: t0 + 1], vol_window)
        if not sigma:  # None or 0.0
            continue
        h_up = p0 * (1 + c * sigma)
        h_down = p0 * (1 - c * sigma)
        results.append((t0, p0, label_entry(prices, t0, h_up, h_down, T)))
    return results


def verdict(counts: Counter) -> str:
    """One-line read on whether the label distribution is healthy."""
    total = sum(counts.values())
    if total == 0:
        return "—"
    z, pos, neg = counts[0] / total, counts[1] / total, counts[-1] / total
    if z > 0.8:
        return "too many 0 · widen T / lower c"
    if pos > 0.8 or neg > 0.8:
        return "too narrow · noise"
    lo, hi = min(pos, neg), max(pos, neg)
    if lo > 0 and hi / lo > 3:
        return "imbalanced ±1"
    return "balanced ✓"


# --- feature engineering (extension) ----------------------------------------
def price_features(prices: list[float], t0: int) -> dict[str, float] | None:
    """Price-only features known at entry index t0 (offline approximation)."""
    if t0 < VOL_WINDOW:
        return None
    window = prices[: t0 + 1]
    sma5 = float(np.mean(window[-5:]))
    sma20 = float(np.mean(window[-20:]))
    mid = window[-1]
    return {
        "sma_ratio": mid / sma5 - 1 if sma5 else 0.0,
        "trend": sma5 / sma20 - 1 if sma20 else 0.0,
        "volatility": compute_volatility(window) or 0.0,
        "momentum": float(np.log(window[-1] / window[-2]))
        if window[-2] > 0
        else 0.0,
    }


def feature_correlations(
    prices: list[float], results: list[tuple[int, float, int]]
) -> dict[str, float]:
    """Pearson correlation of each feature with the label, across entries."""
    cols: dict[str, list[float]] = {k: [] for k in FEATURES}
    labels: list[int] = []
    for t0, _p0, lab in results:
        feats = price_features(prices, t0)
        if feats is None:
            continue
        for k in FEATURES:
            cols[k].append(feats[k])
        labels.append(lab)

    out = {k: 0.0 for k in FEATURES}
    if len(labels) < 3:
        return out
    y = np.asarray(labels, dtype=float)
    if np.std(y) == 0:
        return out
    for k, vals in cols.items():
        x = np.asarray(vals, dtype=float)
        if np.std(x) > 0:
            out[k] = float(np.corrcoef(x, y)[0, 1])
    return out


# --- widgets ----------------------------------------------------------------
class FeaturePanel(Static):
    """Feature-vs-label correlations for the selected symbol (c = 1.5)."""

    DEFAULT_CSS = """
    FeaturePanel { height: 10; border: round $secondary; padding: 0 1; }
    """

    def show(self, symbol: str, corr: dict[str, float]) -> None:
        t = Text()
        t.append(f"  Feature ↔ label corr · {symbol} (c=1.5)\n\n", style="bold")
        if not any(corr.values()):
            t.append("  collecting entries…", style="dim italic")
            self.update(t)
            return
        best = max(corr, key=lambda k: abs(corr[k]))
        for name, value in sorted(corr.items(), key=lambda kv: -abs(kv[1])):
            bar = "█" * int(round(abs(value) * 20))
            color = "green" if value >= 0 else "red"
            style = f"bold {color}" if name == best else color
            t.append(f"  {name:<12}", style="dim" if name != best else "bold")
            t.append(f"{value:+.2f} ", style=style)
            t.append(f"{bar}\n", style=color)
        self.update(t)


class Lab3App(App):
    """Live Triple Barrier label-distribution explorer."""

    CSS = """
    Screen { layout: vertical; }
    #status { height: 3; border: round $accent; padding: 0 1; content-align: left middle; }
    #body { height: 1fr; }
    #table { width: 3fr; border: round $primary; }
    #right { width: 2fr; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [("q", "quit", "Back to menu")]

    COLUMNS = [
        ("Symbol", "symbol"),
        ("c", "c"),
        ("N", "n"),
        ("+1", "pos"),
        ("0", "zero"),
        ("−1", "neg"),
        ("Verdict", "verdict"),
    ]

    def __init__(self, trader: shift.Trader, symbols: list[str]) -> None:
        super().__init__()
        self.trader = trader
        self.symbols = symbols
        self.selected = symbols[0]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="status")
        with Horizontal(id="body"):
            yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="right"):
                yield PricePanel(id="chart")
                yield FeaturePanel(id="features")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Lab 3 · Triple Barrier"
        self.sub_title = " vs ".join(self.symbols)
        table = self.query_one(DataTable)
        for label, key in self.COLUMNS:
            table.add_column(label, key=key)
        for sym in self.symbols:
            for c in C_VALUES:
                table.add_row(
                    sym, f"{c:g}", "0", "0", "0", "0", "—", key=f"{sym}|{c:g}"
                )
        self.set_interval(2.0, self.refresh_data)
        self.refresh_data()

    # -- refresh -------------------------------------------------------------
    def refresh_data(self) -> None:
        self.gather()

    @work(exclusive=True, thread=True)
    def gather(self) -> None:
        data: dict[str, dict] = {}
        for sym in self.symbols:
            prices = list(self.trader.get_sample_prices(sym, True))
            per_c = {c: apply_triple_barrier(prices, c=c) for c in C_VALUES}
            data[sym] = {"prices": prices, "per_c": per_c}

        sel = data[self.selected]
        prices = sel["prices"]
        results = sel["per_c"][1.5]
        corr = feature_correlations(prices, results)

        # barriers of the most recent labelled entry, for the chart
        hlines = []
        if results:
            t0, p0, _ = results[-1]
            sigma = compute_volatility(prices[: t0 + 1]) or 0.0
            hlines = [(p0 * (1 + 1.5 * sigma), "green"),
                      (p0 * (1 - 1.5 * sigma), "red")]

        self.call_from_thread(self.apply, data, corr, hlines)

    def apply(self, data: dict, corr: dict, hlines: list) -> None:
        table = self.query_one(DataTable)
        total_n = 0
        for sym in self.symbols:
            n = len(data[sym]["prices"])
            total_n = max(total_n, n)
            for c in C_VALUES:
                results = data[sym]["per_c"][c]
                counts = Counter(lab for _, _, lab in results)
                self._update_row(table, sym, c, len(results), counts)

        progress = min(total_n, TARGET_SAMPLES)
        self.query_one("#status", Static).update(
            Text.assemble(
                ("  Samples ", "dim"),
                (f"{progress}/{TARGET_SAMPLES}  ", "bold cyan"),
                ("│ ", "dim"),
                (f"{'█' * int(20 * progress / TARGET_SAMPLES):<20}", "cyan"),
                ("  T=", "dim"), (f"{T_VERTICAL}", "bold"),
                ("  vol_window=", "dim"), (f"{VOL_WINDOW}", "bold"),
            )
        )

        prices = data[self.selected]["prices"]
        self.query_one(PricePanel).draw(
            f"{self.selected} — mid price + 1.5σ barriers", prices, hlines=hlines
        )
        self.query_one(FeaturePanel).show(self.selected, corr)

    def _update_row(
        self, table: DataTable, sym: str, c: float, n: int, counts: Counter
    ) -> None:
        total = sum(counts.values())

        def cell(label: int, color: str) -> Text:
            k = counts[label]
            pct = f" {100 * k / total:.0f}%" if total else ""
            return Text(f"{k}{pct}", style=color, justify="right")

        key = f"{sym}|{c:g}"
        table.update_cell(key, "n", Text(str(n), justify="right"))
        table.update_cell(key, "pos", cell(1, "green"))
        table.update_cell(key, "zero", cell(0, "yellow"))
        table.update_cell(key, "neg", cell(-1, "red"))
        v = verdict(counts)
        vstyle = "green" if v.endswith("✓") else "dim" if v == "—" else "yellow"
        table.update_cell(key, "verdict", Text(v, style=vstyle))

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        sym = str(event.row_key.value).split("|")[0]
        if sym != self.selected:
            self.selected = sym
            self.refresh_data()


# --- lab entry point --------------------------------------------------------
def _pick_symbols(trader: shift.Trader) -> list[str]:
    syms = trader.get_stock_list()
    chosen = [s for s in ("AAPL", "MSFT") if s in syms]
    for s in sorted(syms):
        if len(chosen) >= 2:
            break
        if s not in chosen:
            chosen.append(s)
    return chosen[:2]


def run(trader: shift.Trader) -> None:
    symbols = _pick_symbols(trader)
    if len(symbols) < 2:
        raise RuntimeError("Need at least two tradable symbols for Lab 3.")

    trader.request_sample_prices(
        symbols, sampling_frequency=1.0, sampling_window=TARGET_SAMPLES + 50
    )
    time.sleep(2)  # let the buffers begin filling
    Lab3App(trader, symbols).run()
