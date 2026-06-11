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

FACTOR_GROUPS = {
    "returns": RETURN_FACTORS,
    "market_cap": MARKET_CAP_FACTORS,
}
