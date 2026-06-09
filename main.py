#!/usr/bin/env python3
"""Finance Week — lab launcher (Textual UI).

Opens a single SHIFT connection, then shows a menu. Pick a lab to run it;
when you exit that lab you come back to the menu. The connection is held open
across labs and closed cleanly only when you quit the launcher.

    python main.py               # menu (prompts for login if not configured)
    python main.py 1             # jump straight into Lab 1, then return to menu
    python main.py --lab 2
    python main.py --username YOUR_USERNAME --password YOUR_PASSWORD

Credentials are read from --username/--password, otherwise the env vars
SHIFT_USERNAME / SHIFT_PASSWORD. If they are still the placeholders below
(e.g. after a fresh clone), you are prompted for them at startup.
"""
from __future__ import annotations

import argparse
import getpass
import os

import shift
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView

import Lab1
import Lab2
import Lab3
import Lab4
import Lab5
from connection import Connection

# Placeholder logins shipped in the repo. If these are still in place at
# startup (a fresh clone with no env vars / flags), we prompt the user.
PLACEHOLDER_USERNAME = "YOUR_USERNAME"
PLACEHOLDER_PASSWORD = "YOUR_PASSWORD"

LABS = {
    1: Lab1,
    2: Lab2,
    3: Lab3,
    4: Lab4,
    5: Lab5,
}


class LauncherApp(App):
    """A small menu that returns the chosen lab number (or None to quit)."""

    TITLE = "Finance Week — Labs"
    SUB_TITLE = "High Frequency Trading"

    CSS = """
    Screen { align: center middle; }
    #menu { width: 64; height: auto; border: round $primary; padding: 1 2; }
    #hint { text-align: center; color: $text-muted; padding-top: 1; }
    ListView { height: auto; background: $surface; }
    ListItem { padding: 0 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, labs: dict[int, object]) -> None:
        super().__init__()
        self.labs = labs

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="menu"):
            items = []
            for num, mod in self.labs.items():
                ready = getattr(mod, "IMPLEMENTED", False)
                chip = "[green]● ready[/]" if ready else "[dim]○ todo[/]"
                items.append(
                    ListItem(Label(f" [b]{num}.[/b]  {mod.NAME}    {chip}"),
                             id=f"lab-{num}")
                )
            yield ListView(*items, id="labs")
            yield Label("↑/↓ to move · Enter to launch · q to quit", id="hint")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        num = int(event.item.id.removeprefix("lab-"))
        mod = self.labs[num]
        if getattr(mod, "IMPLEMENTED", False):
            self.exit(num)
        else:
            self.notify(
                f"{mod.NAME} is not implemented yet.",
                severity="warning",
                timeout=2.0,
            )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Finance Week lab launcher.")
    p.add_argument("lab", nargs="?", type=int, choices=sorted(LABS),
                   help="Lab to start with (omit for the menu).")
    p.add_argument("--lab", dest="lab_flag", type=int, choices=sorted(LABS))
    p.add_argument(
        "--username",
        default=os.environ.get("SHIFT_USERNAME", PLACEHOLDER_USERNAME),
    )
    p.add_argument(
        "--password",
        default=os.environ.get("SHIFT_PASSWORD", PLACEHOLDER_PASSWORD),
    )
    p.add_argument("--config", default="initiator.cfg")
    return p.parse_args()


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Use the supplied login, or prompt if it's still the placeholder."""
    username, password = args.username, args.password
    if not username or username == PLACEHOLDER_USERNAME:
        username = input("SHIFT username: ").strip()
    if not password or password == PLACEHOLDER_PASSWORD:
        password = getpass.getpass("SHIFT password: ")
    return username, password


def main() -> None:
    args = parse_args()
    username, password = resolve_credentials(args)
    try:
        with Connection(username, password, args.config) as trader:
            pending = args.lab or args.lab_flag  # optional lab to open first
            while True:
                if pending is not None:
                    num, pending = pending, None
                else:
                    num = LauncherApp(LABS).run()
                    if num is None:
                        break  # user quit the menu -> clean disconnect
                LABS[num].run(trader)
    except shift.ConnectionTimeoutError:
        print("Timeout: server is alive but did not acknowledge our FIX Logon.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as exc:  # noqa: BLE001 — surface startup errors plainly
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
