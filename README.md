# Event-Driven Equity Risk Lab

A systematic equity research project studying whether large post-event abnormal stock moves produce tradable drift or reversal after accounting for costs, liquidity, volatility, and market regime conditions.

## Research Question

When do equity events produce persistent post-event abnormal returns, and when does the apparent signal disappear after costs, liquidity constraints, volatility, or market regime shifts?

## Initial Scope

Version 1 focuses on large abnormal price and volume events using daily US equity data.

The first milestone is to build an event panel where each row represents a stock-date event and includes:

- event-day abnormal return
- event-day volume shock
- pre-event volatility
- pre-event momentum
- future 5-day return
- future 10-day return
- future 20-day return

## Planned Pipeline

1. Data ingestion
2. Return calculation
3. Abnormal return estimation
4. Event detection
5. Event panel construction
6. Event-study analysis
7. Signal validation
8. Basic backtest
9. Transaction costs and liquidity filters
10. Regime-aware risk layer
11. Walk-forward validation
12. Failure-mode analysis