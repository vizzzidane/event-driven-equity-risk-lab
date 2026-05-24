# Event-Driven Equity Risk Lab: Research Report

## Abstract

This project studies whether large stock-level abnormal price-volume events create persistent post-event abnormal returns. The research begins with a broad event-study framework, then narrows into a specific finding: negative abnormal price-volume events tend to reverse over a medium-term horizon.

The strongest current result is a negative-event reversal strategy that buys after large negative abnormal price-volume events and holds for around 30 trading days. The strategy is evaluated using SPY-adjusted abnormal returns, transaction costs, placebo tests, sensitivity analysis, and walk-forward validation. In the optimized walk-forward test from 2018 to 2025, the strategy produced a 140.63% total abnormal return, 1.03 annualized abnormal Sharpe, and -10.71% max abnormal drawdown after 5 bps per side transaction costs.

The result is not presented as a universal stock-market anomaly. The project finds that the effect is asymmetric, heterogeneous across tickers, weaker in stress/repricing years, and sensitive to very high transaction costs. The current evidence supports a narrower conclusion: negative abnormal price-volume shocks often behave like temporary overreactions, but some represent genuine repricing and should not be treated as mean-reversion opportunities.

## 1. Research Question

The central question is:

> When do equity events produce tradable post-event abnormal returns, and when does the apparent signal disappear after transaction costs, placebo baselines, parameter sensitivity, and walk-forward validation?

The project focuses on event-driven equity behaviour rather than broad market-regime allocation. Each observation is a `ticker + event_date` pair. The goal is to test whether stocks exhibit continuation or reversal after abnormal stock-level shocks.

## 2. Data and Universe

The initial MVP universe consists of 10 liquid large-cap stocks:

```text
AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, XOM, JNJ, HD