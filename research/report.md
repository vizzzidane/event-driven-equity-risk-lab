# Event-Driven Equity Risk Lab: Research Report

## Abstract

This project studies whether large stock-level abnormal price-volume events create persistent post-event abnormal returns. The research begins with a broad event-study framework, then narrows into a specific finding: negative abnormal price-volume events tend to reverse over a medium-term horizon.

The initial MVP used 10 large-cap stocks. The project was later expanded to an 88-stock liquid US equity universe. The expanded universe produced a much larger event panel, increasing the sample from 1,448 events to 12,266 events. The signal weakened in magnitude after expansion, but the negative-event reversal pattern remained statistically meaningful.

The strongest current expanded-universe result is a negative-event reversal strategy with global trade pacing. The strategy buys after large negative abnormal price-volume events, holds for 30 trading days, uses SPY-adjusted abnormal returns, includes 5 bps per side transaction costs, caps positions at 5 concurrent trades, and requires at least 10 calendar days between new trades globally.

Under the expanded global-paced walk-forward validation, the strategy produced a 112.73% total abnormal return, 0.73 annualized abnormal Sharpe, -14.21% max abnormal drawdown, and 77.43% average gross exposure over 2016-2025.

The result is not presented as a universal stock-market anomaly. The project finds that the effect is asymmetric, heterogeneous across tickers, weaker in some periods, sensitive to costs, and vulnerable to event clustering. The current evidence supports a narrower conclusion: negative abnormal price-volume shocks often behave like temporary overreactions, but some represent genuine repricing and should not be treated as mean-reversion opportunities.

## 1. Research Question

The central research question is:

> When do equity events produce tradable post-event abnormal returns, and when does the apparent signal disappear after transaction costs, placebo baselines, parameter sensitivity, exposure controls, and walk-forward validation?

The project focuses on event-driven equity behaviour rather than broad market-regime allocation. Each observation is a `ticker + event_date` pair. The goal is to test whether stocks exhibit continuation or reversal after abnormal stock-level shocks.

## 2. Data and Universe

The initial MVP universe consisted of 10 liquid large-cap stocks:

```text
AAPL, MSFT, NVDA, AMZN, META, GOOGL, JPM, XOM, JNJ, HD
```

The expanded universe contains 88 liquid US equities across technology, financials, healthcare, consumer, industrials, energy, materials, utilities, and communication services.

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

This removes broad SPY exposure, but it does not yet control for sector, beta, or factor exposures. For the MVP and expanded validation, this is sufficient to test whether the event effect survives a basic market adjustment.

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

## 5. Initial MVP Event Study

The first 10-stock event panel contained:

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

The initial event study showed positive average abnormal returns after abnormal price-volume events. However, this raw result alone was not enough to claim alpha because it could be driven by the small stock universe, market period, or repeated exposure to a few high-momentum names.

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

## 8. Initial Backtest Design

The first strategy backtest used the following base rules:

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

The optimized walk-forward test selected parameters using only prior years.

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

These optimized walk-forward results reflect the earlier research setup before expanded-universe pacing controls were added.

This changes the interpretation of the project. The signal does not disappear after universe expansion, but deployment must control event clustering and persistent exposure.

## 12. Expanded Universe Validation

After the initial MVP research pass, the project was expanded from 10 large-cap stocks to an 88-stock liquid US equity universe.

The expanded universe produced a much larger event panel:

| Metric | MVP Universe | Expanded Universe |
|---|---:|---:|
| Stocks | 10 | 88 |
| Events | 1,448 | 12,266 |
| Positive events | 774 | 6,244 |
| Negative events | 674 | 6,022 |

The expanded event-study result remained positive:

| Group | Events | 20d Mean Abnormal Return | 20d Hit Rate | 20d t-stat |
|---|---:|---:|---:|---:|
| All events | 12,266 | 0.50% | 51.56% | 7.14 |
| Positive events | 6,244 | 0.49% | 51.44% | 5.02 |
| Negative events | 6,022 | 0.50% | 51.68% | 5.07 |

The signal weakened in magnitude compared with the original 10-stock MVP, but the expanded sample is broader and more statistically credible.

The event-type analysis continued to select negative-event reversal as the strongest candidate:

| Horizon | Strategy | Events | Mean Return | Avg bps/event | Hit Rate | t-stat |
|---:|---|---:|---:|---:|---:|---:|
| 5d | Negative Event Reversal | 6,022 | 0.134% | 13.41 bps | 50.76% | 2.31 |
| 10d | Negative Event Reversal | 6,022 | 0.284% | 28.41 bps | 51.59% | 3.79 |
| 20d | Negative Event Reversal | 6,022 | 0.503% | 50.34 bps | 51.68% | 5.07 |

This suggests that the original finding was not only a 10-stock artifact.

## 13. Expanded Universe Backtest

The expanded 88-stock abnormal-return backtest used the same negative-event reversal idea with a 30-trading-day holding period.

| Metric | Result |
|---|---:|
| Universe size | 88 |
| Trades | 457 |
| Win rate | 52.52% |
| Average trade abnormal return | 1.00% |
| Median trade abnormal return | 0.48% |
| Total abnormal return | 126.16% |
| Annualized abnormal Sharpe | 0.63 |
| Max abnormal drawdown | -26.08% |
| Active day ratio | 99.20% |
| Average gross exposure | 95.74% |

The effect survived universe expansion, but the strategy became almost continuously invested. This exposed a new failure mode: in a broader universe, the event detector creates enough signals to keep the portfolio close to fully deployed most of the time.

## 14. Exposure Control: Cooldown and Global Pacing

A same-ticker cooldown was tested first.

| Cooldown | Accepted Trades | Avg Trade Return | Sharpe | Max Drawdown | Avg Gross Exposure |
|---:|---:|---:|---:|---:|---:|
| 0d | 457 | 1.00% | 0.63 | -26.08% | 95.74% |
| 5d | 454 | 0.93% | 0.59 | -27.36% | 95.11% |
| 10d | 453 | 0.80% | 0.52 | -27.08% | 94.90% |
| 20d | 453 | 1.06% | 0.69 | -19.67% | 94.90% |
| 30d | 452 | 0.92% | 0.63 | -19.99% | 94.69% |

The 20-day same-ticker cooldown improved drawdown and Sharpe, but it did not solve the main exposure problem because other stocks continued to generate enough events to keep the strategy highly invested.

A global pacing rule was then tested. This limits how often the strategy can add new trades across the entire universe.

| Min Days Between New Trades | Accepted Trades | Avg Trade Return | Sharpe | Max Drawdown | Avg Gross Exposure |
|---:|---:|---:|---:|---:|---:|
| 0 | 457 | 1.00% | 0.63 | -26.08% | 95.74% |
| 1 | 457 | 1.08% | 0.71 | -23.28% | 95.74% |
| 2 | 454 | 0.63% | 0.42 | -20.55% | 95.11% |
| 3 | 450 | 0.70% | 0.45 | -21.22% | 94.27% |
| 5 | 428 | 0.68% | 0.40 | -25.76% | 89.66% |
| 10 | 368 | 1.39% | 0.77 | -14.19% | 77.10% |

The 10-calendar-day global pacing rule was the best current realism layer. It improved Sharpe, reduced drawdown, and lowered average gross exposure.

The updated expanded-universe candidate is:

| Component | Rule |
|---|---|
| Strategy | Negative Event Reversal |
| Universe | 88 liquid US equities |
| Event threshold | `event_strength <= -2.0` |
| Volume confirmation | `volume_shock >= 1.2` |
| Holding period | 30 trading days |
| Transaction cost | 5 bps per side |
| Position cap | Max 5 concurrent positions |
| Exposure control | Minimum 10 calendar days between new trades globally |

This changes the interpretation of the project. The signal does not disappear after universe expansion, but deployment must control event clustering and persistent exposure.

### 14.1 Expanded Global-Paced Walk-Forward Validation

The strongest current validation layer applies the expanded-universe global pacing rule in a fixed-rule yearly walk-forward test from 2016 to 2025.

Fixed rule:

```text
event_strength <= -2.0
volume_shock >= 1.2
hold = 30 trading days
transaction cost = 5 bps per side
max concurrent positions = 5
minimum 10 calendar days between new trades globally
```

Full expanded global-paced walk-forward result:

| Metric | Result |
|---|---:|
| Test period | 2016-2025 |
| Trades | 327 |
| Win rate | 51.38% |
| Average trade abnormal return | 1.27% |
| Median trade abnormal return | 0.13% |
| Total abnormal return | 112.73% |
| Annualized abnormal Sharpe | 0.73 |
| Max abnormal drawdown | -14.21% |
| Average gross exposure | 77.43% |

Yearly results:

| Year | Trades | Abnormal Return | Sharpe | Max Drawdown |
|---:|---:|---:|---:|---:|
| 2016 | 34 | 18.32% | 1.66 | -4.76% |
| 2017 | 33 | 9.11% | 1.00 | -9.24% |
| 2018 | 33 | 13.97% | 1.46 | -6.99% |
| 2019 | 33 | -6.28% | -0.58 | -13.26% |
| 2020 | 31 | 0.62% | 0.12 | -14.19% |
| 2021 | 33 | 9.95% | 0.99 | -8.80% |
| 2022 | 31 | 16.39% | 1.34 | -8.55% |
| 2023 | 33 | 11.70% | 1.17 | -6.44% |
| 2024 | 33 | -7.23% | -0.67 | -10.60% |
| 2025 | 33 | 15.65% | 1.09 | -7.17% |

This is currently the strongest validation layer in the project because it combines expanded-universe testing, abnormal returns, transaction costs, position caps, global pacing, and fixed-rule yearly walk-forward validation.

The result is positive overall, but not positive every year. The weak years were 2019 and 2024, showing that the strategy remains regime-sensitive and should not be interpreted as a universal anomaly.

## 15. Failure Modes

The main failure modes are:

| Failure Mode | Mechanism |
|---|---|
| Genuine repricing | Some negative events are not overreactions but the start of a real decline |
| Ticker heterogeneity | Performance is uneven across stocks |
| Stress/repricing years | Some periods show weaker reversal behaviour depending on validation method |
| Cost drag | The strategy fails under very high transaction cost assumptions |
| Over-filtering | Very strict event thresholds reduce the trade set and can remove the edge |
| Persistent exposure | The expanded universe creates too many events unless pacing is added |
| Event clustering | Repeated events can keep the portfolio almost continuously invested |

Ticker-level validation showed that performance was not uniform. Some high-volatility growth and semiconductor names contributed strongly, while several energy, telecom, and industrial names were weaker.

The main interpretation is that some negative events are temporary overreactions, while others are the beginning of genuine fundamental repricing. The current model does not yet fully distinguish between these two cases.

## 16. Limitations

The project is still an MVP research system.

Current limitations:

1. The expanded universe is larger but still manually selected.
2. Event detection is based on price-volume shocks, not actual earnings announcement dates.
3. The strategy still has meaningful exposure even after global pacing.
4. Sector-neutral attribution has not yet been implemented.
5. The abnormal-return model uses SPY adjustment only, not beta-adjusted or factor-adjusted returns.
6. The optimized parameter-selection walk-forward framework has not yet been rerun under the expanded-universe global-pacing setup.
7. Results are heterogeneous across tickers and years.
8. The project has not yet been tested on a full production-grade equity universe.
9. The test suite covers core logic, but not the full research pipeline.

## 17. Future Work

Planned extensions:

1. Add sector classification and sector attribution analysis.
2. Add actual earnings announcement dates.
3. Add earnings surprise and analyst revision data.
4. Add sector-neutral portfolio construction and sector-adjusted abnormal returns.
5. Compare SPY-adjusted, beta-adjusted, sector-adjusted, and factor-adjusted abnormal returns.
6. Add stronger exposure controls through monthly trade budgets or volatility targeting.
7. Add event spacing rules that combine same-ticker cooldown and global pacing.
8. Add more tests around walk-forward parameter selection and portfolio construction.
9. Update figures to include expanded-universe global pacing results.
10. Produce a final PDF-style research note with figures and appendix tables.

## 18. Conclusion

The project began with a broad question about post-event equity drift and narrowed into a specific finding: negative abnormal price-volume events exhibit a medium-term reversal pattern.

The original 10-stock MVP showed strong early evidence for the effect. The later 88-stock expanded universe made the result more credible by increasing the event panel from 1,448 to 12,266 events. The signal weakened in magnitude, but the negative-event reversal thesis remained intact.

The expanded universe also revealed an important deployment issue. Without pacing, the strategy becomes almost continuously invested, with an active day ratio near 99% and average gross exposure near 96%. This makes the naive expanded strategy less realistic.

The strongest current validation layer is the expanded global-paced walk-forward framework. Using abnormal returns, transaction costs, position caps, and a minimum 10-calendar-day gap between new trades globally, the strategy produced a 112.73% total abnormal return, 0.73 annualized abnormal Sharpe, -14.21% max abnormal drawdown, and 77.43% average gross exposure over 2016-2025.

The current conclusion is:

> Negative abnormal price-volume events tend to reverse over a medium-term horizon. The effect survives expansion from 10 stocks to 88 liquid US equities, but naive deployment becomes too continuously invested. Global pacing, transaction costs, position caps, and fixed-rule walk-forward validation materially improve realism while preserving a positive long-term abnormal return profile.

This makes the project a credible event-driven equity research system, while leaving clear room for future improvements in actual event data, sector controls, factor adjustment, walk-forward validation under the expanded universe, and stronger exposure management.