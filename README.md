# Event-Driven Equity Risk Lab

A systematic equity research project studying whether large stock-level information shocks create persistent post-event abnormal returns.

The project focuses on **event-driven equity behaviour**, not broad market-regime allocation. Each observation is a `ticker + event_date` pair, and the core question is whether stocks drift or reverse after abnormal price-volume events.

## Research Question

When do equity events produce tradable post-event abnormal returns, and when does the apparent signal disappear after transaction costs, liquidity constraints, placebo baselines, or failure-mode conditions?

## Core Finding

The strongest current result is an asymmetric event effect:

> Negative abnormal price-volume events show a medium-term reversal pattern.

A strategy that buys after negative abnormal price-volume events and holds for around 30 trading days produced positive SPY-adjusted abnormal returns in both fixed-rule and optimized walk-forward validation.

The current best out-of-sample-style result is the optimized walk-forward test from 2018 to 2025:

| Metric | Result |
|---|---:|
| Trades | 254 |
| Win rate | 57.09% |
| Average trade abnormal return | 1.81% |
| Median trade abnormal return | 1.20% |
| Total abnormal return | 140.63% |
| Annualized abnormal Sharpe | 1.03 |
| Max abnormal drawdown | -10.71% |

All returns above are abnormal returns, calculated as:

```text
stock return - SPY return