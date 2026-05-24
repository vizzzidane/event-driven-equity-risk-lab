# Event-Driven Equity Risk Lab: Research Report

## Abstract

This project studies whether large stock-level abnormal price-volume events create persistent post-event abnormal returns. The research begins with a broad event-study framework, then narrows into a specific finding: negative abnormal price-volume events tend to reverse over a medium-term horizon.

The strongest current result is a negative-event reversal strategy that buys after large negative abnormal price-volume events and holds for around 30 trading days. The strategy is evaluated using SPY-adjusted abnormal returns, transaction costs, placebo tests, sensitivity analysis, and walk-forward validation.

In the optimized walk-forward test from 2018 to 2025, the strategy produced:

| Metric | Result |
|---|---:|
| Total abnormal return | 140.63% |
| Annualized abnormal Sharpe | 1.03 |
| Max abnormal drawdown | -10.71% |
| Trades | 254 |
| Win rate | 57.09% |

The result is not presented as a universal stock-market anomaly. The effect is asymmetric, heterogeneous across tickers, weaker in stress/repricing years, and sensitive to very high transaction costs. The current evidence supports a narrower conclusion: negative abnormal price-volume shocks often behave like temporary overreactions, but some represent genuine repricing.

## 1. Research Question

The central research question is:

> When do equity events produce tradable post-event abnormal returns, and when does the apparent signal disappear after transaction costs, placebo baselines, parameter sensitivity, and walk-forward validation?

The project focuses on event-driven equity behaviour rather than broad market-regime allocation. Each observation is a `ticker + event_date` pair. The goal is to test whether stocks exhibit continuation or reversal after abnormal stock-level shocks.

## 2. Data and Universe

The initial MVP universe consists of 10 liquid large-cap stocks:

```text
AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, XOM, JNJ, HD
```

SPY is used as the market benchmark.

The current dataset spans:

```text
2015-01-02 to 2026-05-22
```

Daily price and volume data are downloaded using `yfinance`. Generated data files are ignored by Git and can be rebuilt by running the pipeline.

## 3. Abnormal Return Definition

Daily abnormal return is calculated as:

```text
abnormal_return_i,t = stock_return_i,t - SPY_return_t
```

This removes broad SPY exposure, but it does not yet control for sector, beta, or factor exposures. For the MVP, this is sufficient to test whether the event effect survives a basic market adjustment.

## 4. Event Definition

For each stock, the project computes a rolling 20-day abnormal volatility estimate using only prior data:

```text
rolling_20d_abnormal_vol_i,t
```

Event strength is then defined as:

```text
event_strength_i,t = abnormal_return_i,t / rolling_20d_abnormal_vol_i,t
```

Volume shock is defined as:

```text
volume_shock_i,t = current_volume_i,t / trailing_20d_avg_volume_i,t
```

The baseline negative event definition is:

```text
event_strength <= -2.0
volume_shock >= 1.2
avg_20d_dollar_volume >= 50,000,000
```

Rolling baselines are shifted by one day, so event-day return and event-day volume are not used in the pre-event volatility and volume estimates.

## 5. Event Study

The first event panel contained:

| Metric | Value |
|---|---:|
| Events | 1,448 |
| Positive events | 774 |
| Negative events | 674 |
| Tickers | 10 |
| Date range | 2015-02-12 to 2026-04-24 |

Initial 20-day event-study results:

| Group | 20d Mean Abnormal Return | 20d Hit Rate | 20d t-stat |
|---|---:|---:|---:|
| All events | 0.80% | 53.45% | 4.37 |
| Positive events | 0.79% | 52.45% | 3.06 |
| Negative events | 0.82% | 54.60% | 3.13 |

The initial event study showed positive average abnormal returns after abnormal price-volume events. However, this raw result alone was not enough to claim alpha because it could be driven by the stock universe, market period, or repeated exposure to high-momentum names.

## 6. Directional Drift and Reversal

The project then separated continuation from reversal.

For positive events:

```text
drift = future abnormal return > 0
```

For negative events:

```text
drift = future abnormal return < 0
reversal = future abnormal return > 0
```

This revealed an asymmetric pattern:

| Event Type | 20d Behaviour |
|---|---|
| Positive events | Continuation / drift |
| Negative events | Rebound / reversal |

The strongest early candidate became:

```text
Negative Event Reversal
```

meaning:

```text
buy after a large negative abnormal price-volume event
```

## 7. Placebo Tests

### 7.1 Random Placebo

A random placebo test sampled random stock-date observations. Random placebo events performed similarly to real events in several cases, which weakened the broad initial interpretation.

This was a useful failure check. It showed that the raw event effect could not be treated as unique to detected events.

### 7.2 Matched Placebo

A stricter matched placebo sampled non-event dates from the same stock and same year. This controls for ticker-specific behaviour and time-period effects.

Matched placebo result for negative-event reversal:

| Strategy | Horizon | Real | Matched Placebo | Difference |
|---|---:|---:|---:|---:|
| Negative Event Reversal | 20d | 0.82% | 0.51% | 30.3 bps |

This supported the narrower finding that negative-event reversal was stronger than same-stock, same-year non-event baselines.

## 8. Backtest Design

The strategy backtest uses the following base rules:

| Component | Rule |
|---|---|
| Strategy | Negative Event Reversal |
| Entry | Next trading day after event |
| Direction | Long |
| Holding period | Tested across 5d, 10d, 20d, 30d, 60d |
| Return stream | Stock return minus SPY return |
| Transaction cost | 5 bps per side |
| Positioning | Equal-weight active positions |
| Position cap | Max 5 concurrent positions |

The first raw backtest used stock returns. A stricter version used abnormal returns, which is more credible because it removes broad SPY exposure.

The 20-day abnormal-return backtest produced:

| Metric | Result |
|---|---:|
| Trades | 456 |
| Win rate | 54.61% |
| Average trade abnormal return | 0.83% |
| Total abnormal return | 108.70% |
| Annualized abnormal Sharpe | 0.70 |
| Max abnormal drawdown | -22.68% |

This showed that the strategy did not collapse after removing market exposure.

## 9. Robustness Checks

### 9.1 Cost Sensitivity

| Cost per Side | Round Trip | Avg Trade Abnormal Return | Total Abnormal Return | Sharpe |
|---:|---:|---:|---:|---:|
| 1 bps | 2 bps | 0.91% | 124.50% | 0.77 |
| 5 bps | 10 bps | 0.83% | 108.70% | 0.70 |
| 10 bps | 20 bps | 0.73% | 90.51% | 0.62 |
| 25 bps | 50 bps | 0.43% | 44.89% | 0.38 |
| 50 bps | 100 bps | -0.07% | -8.20% | -0.03 |

The edge survives moderate costs but fails under very high slippage.

### 9.2 Holding Period Sensitivity

| Hold | Trades | Avg Trade Abnormal Return | Total Abnormal Return | Sharpe | Max Drawdown |
|---:|---:|---:|---:|---:|---:|
| 5d | 632 | 0.05% | 3.22% | 0.08 | -22.46% |
| 10d | 572 | 0.33% | 42.69% | 0.40 | -17.51% |
| 20d | 456 | 0.83% | 108.70% | 0.70 | -22.68% |
| 30d | 362 | 1.86% | 267.66% | 1.18 | -13.16% |
| 60d | 208 | 1.82% | 96.57% | 0.56 | -17.25% |

The reversal effect was strongest around 30 trading days, suggesting it is a medium-term recovery effect rather than an immediate bounce.

### 9.3 Threshold Sensitivity

| Event Strength | Volume Shock | Trades | Avg Trade Abnormal Return | Total Abnormal Return | Sharpe | Max Drawdown |
|---:|---:|---:|---:|---:|---:|---:|
| 1.5 | 1.0 | 427 | 0.95% | 110.93% | 0.57 | -25.69% |
| 2.0 | 1.2 | 362 | 1.86% | 267.66% | 1.18 | -13.16% |
| 2.5 | 1.5 | 241 | 1.37% | 87.49% | 0.67 | -22.24% |
| 3.0 | 2.0 | 133 | 1.47% | 47.89% | 0.57 | -10.84% |
| 3.5 | 2.5 | 80 | -0.10% | -0.28% | 0.02 | -11.34% |

The balanced threshold setting performed best:

```text
event_strength <= -2.0
volume_shock >= 1.2
```

Loose thresholds diluted the signal. Very strict thresholds reduced the trade set and likely captured events that were more likely to represent genuine repricing.

## 10. Risk Filter Analysis

Several practical filters were tested:

| Filter | Trades | Avg Trade Abnormal Return | Sharpe | Max Drawdown |
|---|---:|---:|---:|---:|
| Baseline | 362 | 1.86% | 1.18 | -13.16% |
| Exclude XOM | 343 | 1.97% | 1.15 | -23.53% |
| Exclude 2022 | 330 | 1.73% | 1.10 | -13.16% |
| Exclude extreme strength > 6 | 357 | 1.87% | 1.16 | -14.35% |
| Cap volume shock at 3 | 353 | 1.75% | 1.08 | -13.82% |
| Practical combined filter | 331 | 2.06% | 1.14 | -23.53% |

No simple filter clearly beat the baseline on risk-adjusted performance. The cleanest current rule remains the baseline.

This is an important research result because it avoids unnecessary overfitting.

## 11. Walk-Forward Validation

### 11.1 Fixed-Rule Walk-Forward

The fixed-rule yearly test used:

```text
event_strength <= -2.0
volume_shock >= 1.2
hold = 30 trading days
```

Full fixed-rule walk-forward result:

| Metric | Result |
|---|---:|
| Test period | 2016-2025 |
| Trades | 325 |
| Win rate | 57.54% |
| Average trade abnormal return | 1.95% |
| Median trade abnormal return | 1.33% |
| Total abnormal return | 247.95% |
| Annualized abnormal Sharpe | 1.26 |
| Max abnormal drawdown | -9.30% |

The fixed rule produced positive abnormal returns in every yearly test slice from 2016 to 2025.

### 11.2 Optimized Walk-Forward

The optimized walk-forward test is the strongest current validation.

For each test year, parameters were selected using only prior years.

Candidate grid:

| Parameter | Values |
|---|---|
| Event strength threshold | 1.5, 2.0, 2.5, 3.0 |
| Volume shock threshold | 1.0, 1.2, 1.5, 2.0 |
| Holding period | 10, 20, 30 |

Full optimized walk-forward result:

| Metric | Result |
|---|---:|
| Test period | 2018-2025 |
| Trades | 254 |
| Win rate | 57.09% |
| Average trade abnormal return | 1.81% |
| Median trade abnormal return | 1.20% |
| Total abnormal return | 140.63% |
| Annualized abnormal Sharpe | 1.03 |
| Max abnormal drawdown | -10.71% |

Yearly optimized results:

| Year | Abnormal Return | Sharpe |
|---:|---:|---:|
| 2018 | 6.49% | 0.54 |
| 2019 | 16.68% | 1.69 |
| 2020 | 2.23% | 0.24 |
| 2021 | 17.12% | 1.76 |
| 2022 | 0.84% | 0.13 |
| 2023 | 21.78% | 1.88 |
| 2024 | 17.59% | 1.56 |
| 2025 | 12.01% | 1.22 |

The strategy remained positive in every optimized test year. The 30-day holding period was selected every year.

## 12. Failure Modes

The main failure modes are:

| Failure Mode | Mechanism |
|---|---|
| Genuine repricing | Some negative events are not overreactions but the start of a real decline |
| Ticker heterogeneity | Performance is uneven across stocks |
| Stress/repricing years | 2020 and 2022 were weaker than normal years |
| Cost drag | The strategy fails under very high transaction cost assumptions |
| Over-filtering | Very strict event thresholds reduce the trade set and can remove the edge |
| Persistent exposure | The strategy is active most of the time, so exposure management still needs work |

Ticker-level validation showed that performance was not uniform. META was the strongest contributor, while XOM was the weakest contributor.

Trade-level year validation showed that 2022 was the weakest year and 2024 was the strongest year.

The main interpretation is that some negative events are temporary overreactions, while others are the beginning of a genuine fundamental repricing. The current model does not yet fully distinguish between these two cases.

## 13. Limitations

The project is still an MVP research system.

Current limitations:

1. The universe is small: 10 large-cap stocks.
2. Event detection is based on price-volume shocks, not actual earnings announcement dates.
3. The strategy is active most of the time, so exposure control needs improvement.
4. Sector-neutral attribution has not yet been implemented.
5. The abnormal-return model uses SPY adjustment only, not beta-adjusted or factor-adjusted returns.
6. The optimized walk-forward test uses a small parameter grid.
7. Results are heterogeneous across tickers and years.
8. The project has not yet been tested on a broader equity universe.

## 14. Future Work

Planned extensions:

1. Expand the universe to 50-100 liquid US equities.
2. Add actual earnings announcement dates.
3. Add earnings surprise and analyst revision data.
4. Add sector classification and sector-neutral attribution.
5. Compare SPY-adjusted, beta-adjusted, sector-adjusted, and factor-adjusted abnormal returns.
6. Add stronger exposure controls to reduce persistent market participation.
7. Add event spacing rules to avoid clustered repeated entries.
8. Add more tests around walk-forward parameter selection and portfolio construction.
9. Produce a final PDF-style research note with figures and appendix tables.

## 15. Conclusion

The project began with a broad question about post-event equity drift and narrowed into a specific finding: negative abnormal price-volume events exhibit a medium-term reversal pattern.

The evidence is strongest for a 30-trading-day holding window. The effect survives matched placebo comparison, transaction costs, threshold sensitivity, holding-period sensitivity, and optimized walk-forward validation. However, the strategy is not universal. It is heterogeneous across tickers, weaker in stress/repricing years, and vulnerable when negative events represent genuine repricing rather than temporary overreaction.

The current conclusion is:

> Negative abnormal price-volume events tend to reverse over a medium-term horizon. A simple strategy buying after these events and holding for around 30 trading days remains positive after SPY adjustment, transaction costs, matched placebo comparison, and optimized walk-forward validation.

This makes the project a credible event-driven equity research system, while leaving clear room for future improvements in universe expansion, event data quality, sector controls, and exposure management.