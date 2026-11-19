import numpy as np
import pandas as pd

from kavzi_trader.evals.realized_variance import RealizedVariance

DAY = "day"
SYMBOL = "symbol"
TARGET = "target"
HAR_WINDOWS = (1, 7, 30)
EXTRA_WINDOWS = (3, 14)


class HarFeatures:
    """Long panel of log realized variances at each close and the 7-day target."""

    @staticmethod
    def panel(
        returns: pd.DataFrame,
        covariates: dict[str, pd.DataFrame] | None = None,
        extra: bool = False,
    ) -> pd.DataFrame:
        """Rows (day, symbol); log-variance features, covariates and ``TARGET``."""
        windows = HAR_WINDOWS + (EXTRA_WINDOWS if extra else ())
        columns = {
            f"log_v{w}": np.log(RealizedVariance.backward(returns, w)) for w in windows
        }
        if extra:
            # Signed return: variance rises more after falls (leverage effect).
            columns["ret"] = returns
        for name, frame in (covariates or {}).items():
            columns[name] = frame.reindex(index=returns.index, columns=returns.columns)
        columns[TARGET] = np.log(RealizedVariance.forward(returns))
        per_symbol = {
            symbol: pd.DataFrame(
                {name: frame[symbol] for name, frame in columns.items()}
            )
            for symbol in returns.columns
        }
        return pd.concat(per_symbol, names=[SYMBOL, DAY])

    @staticmethod
    def to_wide(values: pd.Series, like: pd.DataFrame) -> pd.DataFrame:
        """Panel values back to (days, symbols) shaped like ``like``."""
        wide = pd.DataFrame(
            {s: values.xs(s, level=SYMBOL) for s in values.index.unique(SYMBOL)}
        )
        return wide.reindex(index=like.index, columns=like.columns)

    @staticmethod
    def feature_names(panel: pd.DataFrame) -> list[str]:
        return [c for c in panel.columns if c != TARGET]
