"""SHIFT connection lifecycle.

A small context manager that connects to the SHIFT server, hands you the
``shift.Trader``, and *always* disconnects cleanly on exit (lab requirement 5).

    from connection import Connection

    with Connection("YOUR_USERNAME", "YOUR_PASSWORD") as trader:
        Lab1.run(trader)
"""
from __future__ import annotations

import time

import shift


class Connection:
    """Connect on ``__enter__``, guarantee a clean disconnect on ``__exit__``."""

    def __init__(
        self, username: str, password: str, config: str = "initiator.cfg"
    ) -> None:
        self.username = username
        self.password = password
        self.config = config
        self.trader: shift.Trader | None = None

    def __enter__(self) -> shift.Trader:
        self.trader = shift.Trader(self.username)
        if not self.trader.connect(self.config, self.password):
            raise RuntimeError("Connection returned False (Logon rejected).")
        time.sleep(1)  # let the initial data sync land
        return self.trader

    def __exit__(self, exc_type, exc, tb) -> bool:
        trader = self.trader
        if trader is not None and trader.is_connected():
            try:
                trader.cancel_all_sample_prices_requests()
            except Exception:
                pass  # harmless if no sampling was ever requested
            trader.disconnect()
            print("Disconnected cleanly.")
        return False  # never swallow exceptions
