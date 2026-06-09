# Tutorials — the logic behind each lab

Per-lab write-ups explaining the **code logic** and the **SHIFT API usage**
only (the Textual/Rich/plotext UI is intentionally left out). Each file also
quotes the original lab task from its source lecture.

Start with **[CourseRecap.md](CourseRecap.md)** — a one-file summary of all
eight lectures, the SHIFT API, and how the labs fit together.

| Lab | Topic | Source lecture | Trades? |
|-----|-------|----------------|---------|
| [Lab 1](Lab1.md) | Market Monitor — live quotes + 5-period SMA signal | Lecture 2 | read-only |
| [Lab 2](Lab2.md) | First Algorithm — momentum / mean-reversion / imbalance | Lecture 3 | yes |
| [Lab 3](Lab3.md) | Triple Barrier labelling + feature correlation | Lecture 4 | read-only |
| [Lab 4](Lab4.md) | Strategy Lab — Crossover / MACD / Bollinger / Z-Score / VWAP | Lecture 5 | yes |
| [Lab 5](Lab5.md) | Market Maker — inventory skew, adaptive spread, risk metrics | Lecture 6 | yes |

Code lives one level up: [`Lab1.py`](../Lab1.py) … [`Lab5.py`](../Lab5.py),
with shared helpers in [`connection.py`](../connection.py) and [`UI.py`](../UI.py).
