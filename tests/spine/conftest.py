import pytest

from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from tests.spine.precision.filters import make_precision


@pytest.fixture
def precision() -> SymbolPrecision:
    return make_precision()
