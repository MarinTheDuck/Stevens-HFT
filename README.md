# Finance Week — HFT Labs

A set of high-frequency-trading lab exercises built on the **SHIFT** Python API,
wrapped in a single terminal UI (Textual + Rich + plotext). Launch `main.py`,
pick a lab from the menu, and return to the menu when you exit it. One SHIFT
connection is opened up front and shared across every lab.

> **SHIFT framework reference:** <https://github.com/hanlonlab/shift-python> —
> install, configuration, and full API docs for the `shift` module these labs
> build on.

## Labs

| # | Name | Source | Status |
|---|------|--------|--------|
| 1 | **Market Monitor** — live bid/ask/spread/last + 5-period SMA signal, portfolio summary, price chart | Lecture 2 | ✅ ready |
| 2 | **First Algorithm** — switchable momentum / mean-reversion / order-imbalance strategy with risk guards | Lecture 3 | ✅ ready |
| 3 | **Triple Barrier** — label real price series, compare the distribution across `c = 0.5/1.5/3.0`, feature correlations | Lecture 4 | ✅ ready |
| 4 | **Strategy Lab** — pick one of MA Crossover / MACD / Bollinger / Z-Score / VWAP at launch, then trade it live | Lecture 5 | ✅ ready |
| 5 | **Market Maker** — two-sided quoting with inventory skew, adaptive spread, one-sided pausing, and a risk readout | Lecture 6 | ✅ ready |
| 6–8 | — | — | ⬜ stubs |

## Project layout

```
main.py         Launcher: nice menu, lab switching, login handling
connection.py   SHIFT connect / guaranteed clean disconnect (context manager)
UI.py           Reusable Textual widgets (PortfolioPanel, PricePanel)
Lab1.py … Lab8.py   One module per lab, each exposing run(trader)
initiator.cfg   SHIFT connection config  (instructor-provided, git-ignored)
docs/           Lecture PDFs              (course material, git-ignored)
```

Each lab module exposes a uniform contract — `NAME`, `IMPLEMENTED`, and
`run(trader)` — so adding a lab is just filling in its `run()` and flipping
`IMPLEMENTED = True`; no changes to `main.py` needed.

## Prerequisites

- The **`shift`** conda environment with the `shift` Python module installed.
- Python packages: `textual`, `rich`, `plotext`, `numpy`.
- An `initiator.cfg` (and the FIX data dictionaries it references) from your
  instructor, plus your SHIFT username and password.

## Setup

```bash
conda activate shift
pip install textual rich plotext numpy

# Put the instructor-provided initiator.cfg in the project root.
# (It is git-ignored, so each person supplies their own.)
```

## Running

```bash
python main.py            # open the menu
python main.py 1          # jump straight into a lab, then return to the menu
python main.py --lab 3
```

### Login

The repo ships with placeholder credentials (`YOUR_USERNAME` / `YOUR_PASSWORD`).
If you don't override them, `main.py` **prompts you at startup**. You can supply
them three ways (highest priority first):

```bash
python main.py --username YOUR_USERNAME --password YOUR_PASSWORD
# or
export SHIFT_USERNAME=...   SHIFT_PASSWORD=...
python main.py
# or just run it and answer the prompts
```

Never commit your real credentials. Keep them in env vars or type them at the
prompt.

## Controls

**Menu** — `↑/↓` move · `Enter` launch · `q` quit (disconnects cleanly).

**Lab 1 — Market Monitor** — `↑/↓` pick the charted symbol · `r` refresh · `q` back.

**Lab 2 — First Algorithm** — `Space` start/stop trading · `1/2/3` switch
strategy · `f` flatten position · `q` back.
⚠️ This lab submits **real orders** on the SHIFT simulation. It starts
*armed but paused* — nothing trades until you press `Space`.

**Lab 3 — Triple Barrier** — highlight a table row to switch the analysed
symbol · `q` back.

**Lab 4 — Strategy Lab** — pick a strategy on the launch screen, then `Space`
start/stop · `f` flatten · `q` back to the picker / menu. Momentum strategies
hold until an opposite signal; mean-reversion strategies close on return to the
mean. ⚠️ Submits **real orders**; starts *armed but paused*.

**Lab 5 — Market Maker** — `Space` start/stop · `m` switch basic ⇄ inventory-aware
quoting · `e` toggle flat-position exit · `f` flatten · `q` back. ⚠️ Submits
**real orders**; starts *armed but paused*.

## Notes

- Lecture PDFs (`docs/`) and `initiator.cfg` are git-ignored — they are course
  material / per-machine config, not part of the code.
- `numpy` is installed to the user site (`~/.local/...`) but imports fine from
  the `shift` conda env.
