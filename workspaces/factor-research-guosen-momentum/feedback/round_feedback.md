# Factor Research Round Feedback

## Source

- Report: `国信证券_金融工程专题研究：动量类因子全解析_【发现报告 fxbaogao.com】.pdf`
- Target: extract 5 zer0factor-implementable factors.
- Status: completed through archive.

## Completed Factors

1. `ret20_0`
2. `ret240_20_remove_up_limit`
3. `rank_mom120_20`
4. `smooth240_1`
5. `overnight_mom20`

All five factors were generated as `FactorSpec + FactorFrame + compute()` modules and verified with:

- ruff check
- dynamic import
- small fixture execution
- standard output schema: `trade_date, ts_code, value`

## Useful Patterns

- Report formulas can be converted cleanly when they use price, return, open, close, and rolling windows.
- Path momentum maps well to pandas wide-panel operations.
- Cross-sectional rank logic should be explicit about rank direction, missing values, and minimum valid stock count.
- Every factor should preserve the report's expected direction; `smooth240_1` is intentionally marked as lower-is-better because the report observes reversal-like behavior.

## Contract Gaps

- Exact limit-up exclusion needs limit price or board-specific涨停 metadata. The generated implementation uses a 9.5% close-return threshold approximation.
- New stock, ST, and suspended-stock filters are mentioned in the report but are not currently part of `FactorFrame`.
- Announcement-date factors such as EAR, AOG, JOR, and OverNightMom20AnnDate were excluded because announcement calendars and benchmark/index returns are not in the current standard contract.
- Idiosyncratic momentum was excluded because it needs market, size, and value factor returns plus regression support.

## Next Recommendations

- Add optional provider-level masks for `is_st`, `is_suspended`, `listed_days`, and `limit_up`.
- Add benchmark/index panels if future factors need excess returns.
- Backtest the five completed factors before promoting them into the permanent factor library.
