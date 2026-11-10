"""Built-in factor instances grouped for batch computation."""

from zer0factor.factors.market_cap import LogCirculatingMarketCap, LogTotalMarketCap
from zer0factor.factors.returns import (
    DailyReturn,
    IntradayReturn,
    OpenReturn,
    OvernightReturn,
)

RETURN_FACTORS = (
    DailyReturn(),
    OpenReturn(),
    IntradayReturn(),
    OvernightReturn(),
)
MARKET_CAP_FACTORS = (
    LogTotalMarketCap(),
    LogCirculatingMarketCap(),
)

# Trading days of market data needed before the first written date.
RETURN_FACTORS_LOOKBACK = 1  # x / x.shift(1)
MARKET_CAP_FACTORS_LOOKBACK = 0  # same-day values; z-scores are cross-sectional

FACTOR_GROUPS = {
    "returns": RETURN_FACTORS,
    "market_cap": MARKET_CAP_FACTORS,
}
