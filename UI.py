"""Reusable Textual widgets shared across the labs.

These are deliberately "dumb": they render whatever data they're handed and
hold no SHIFT API logic, so any lab can compose them.

  * PortfolioPanel — account-level summary (buying power, shares, P&L).
  * PricePanel     — a plotext line chart (built on the UI thread, since
                     plotext keeps global state) with an optional overlay line.
"""
from __future__ import annotations

from datetime import datetime

import plotext as plt
from rich.text import Text
from textual.widgets import Static


class PortfolioPanel(Static):
    """Account-level portfolio summary."""

    DEFAULT_CSS = """
    PortfolioPanel { height: 9; border: round $secondary; padding: 0 1; }
    """

    def update_summary(
        self, bp: float, shares: int, pl: float, ts: datetime | None
    ) -> None:
        pl_color = "green" if pl >= 0 else "red"
        text = Text()
        text.append("  Portfolio Summary\n\n", style="bold")
        text.append("  Buying power   ", style="dim")
        text.append(f"${bp:,.2f}\n", style="bold cyan")
        text.append("  Shares traded  ", style="dim")
        text.append(f"{shares:,}\n", style="bold")
        text.append("  Realised P&L   ", style="dim")
        text.append(f"${pl:,.2f}\n", style=f"bold {pl_color}")
        text.append("  Updated at     ", style="dim")
        text.append(f"{ts:%H:%M:%S}" if ts else "—", style="bold")
        self.update(text)


class PricePanel(Static):
    """A plotext chart of a price series with an optional right-aligned overlay."""

    DEFAULT_CSS = """
    PricePanel { height: 1fr; border: round $accent; }
    """

    def draw(
        self,
        title: str,
        series: list[float],
        overlay: tuple[list[float], str] | None = None,
        hlines: list[tuple[float, str]] | None = None,
    ) -> None:
        if len(series) < 2:
            self.update(
                Text(
                    "\n  Waiting for sample-price history…\n"
                    "  (the rolling buffer needs a few seconds to fill)",
                    style="dim italic",
                )
            )
            return

        width = max(self.size.width - 2, 20)
        height = max(self.size.height - 2, 10)

        plt.clf()
        plt.theme("dark")
        plt.plotsize(width, height)
        plt.title(title)
        plt.plot(series, marker="braille", color="cyan", label="price")

        if overlay is not None:
            values, label = overlay
            if values:
                # right-align the overlay with the end of the price series
                x = list(range(len(series) - len(values), len(series)))
                plt.plot(x, values, color="orange", label=label)

        for value, color in hlines or []:  # e.g. take-profit / stop-loss barriers
            plt.hline(value, color)

        self.update(Text.from_ansi(plt.build()))
