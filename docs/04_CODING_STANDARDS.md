# KavziTrader Coding Standards

This document outlines the coding standards and best practices to be followed throughout the KavziTrader codebase. Adherence to these standards ensures code quality, maintainability, and consistency.

## General Principles

### KISS (Keep It Simple, Stupid)

- Prefer simple solutions over complex ones
- Break complex problems into simpler sub-problems
- Use clear, straightforward algorithms
- Avoid premature optimization
- Aim for readability over cleverness

### Avoid Overengineering

- Don't add complexity until it's clearly needed
- Solve the problem at hand, not hypothetical future problems
- Prefer concrete implementations over excessive abstraction
- Recognize when a simple function is better than a class hierarchy
- Question designs that require extensive configuration or customization

### Code Clarity

- Write code that clearly expresses intent
- Choose descriptive variable and function names
- Limit nesting to improve readability (max 3-4 levels)
- Include strategic comments that explain "why" not "what"
- Organize code in logical, consistent patterns
- Consider future maintainers who may not understand the original context

### DRY (Don't Repeat Yourself)

- Avoid code duplication
- Extract reusable functionality into functions and classes
- Leverage inheritance and composition for shared behavior
- Use abstraction to separate concerns
- Define constants and configuration values in one place

### SOLID Principles

#### Single Responsibility Principle (SRP)
- Each class should have only one reason to change
- Classes should be focused and cohesive
- Separate different responsibilities into different classes

#### Open/Closed Principle (OCP)
- Software entities should be open for extension but closed for modification
- Use abstract base classes and interfaces for extensibility
- Leverage dependency injection for flexible component integration

#### Liskov Substitution Principle (LSP)
- Subtypes must be substitutable for their base types
- Derived classes must not alter the expected behavior of base classes
- Avoid violating contracts established by base classes

#### Interface Segregation Principle (ISP)
- Clients should not be forced to depend on interfaces they don't use
- Keep interfaces focused and minimal
- Split large interfaces into smaller, more specific ones

#### Dependency Inversion Principle (DIP)
- High-level modules should not depend on low-level modules
- Both should depend on abstractions
- Abstractions should not depend on details; details should depend on abstractions
- Use dependency injection to decouple components

## Python 3.13 Specific Standards

### Type Hints

Type hints are **mandatory** in all code. Python 3.13 supports modern type hint syntax that should be utilized.

**IMPORTANT: Always use Python 3.11+ type hint syntax, never use older syntax.** This means:
- Use `list[str]` instead of `List[str]`
- Use `dict[str, int]` instead of `Dict[str, int]`
- Use `T | None` instead of `Optional[T]`
- Use `T1 | T2` instead of `Union[T1, T2]`

The older syntax is deprecated and will be removed in future Python versions.

```python
# Good (Python 3.11+ syntax)
def calculate_rsi(prices: list[float], period: int = 14) -> list[float]:
    """Calculate Relative Strength Index."""
    # Implementation

# Bad (Older syntax)
from typing import List, Optional, Union
def calculate_rsi(prices: List[float], period: Optional[int] = 14) -> Union[List[float], None]:
    # Implementation
```

#### Type Hint Best Practices

- Use built-in collection generics (`list[str]`, `dict[str, int]`, etc.)
- Use `None | T` instead of `Optional[T]` for optional parameters
- Use `T1 | T2` instead of `Union[T1, T2]` for parameters accepting multiple types
- Use `TypedDict` for dictionaries with known structure
- Use `Literal` for parameters with specific string values
- Use `Protocol` for structural typing
- Use `@overload` for functions with multiple signatures

```python
from typing import Literal, TypedDict, Protocol, overload, Generic, TypeVar

# TypedDict example
class TradeInfo(TypedDict):
    symbol: str
    price: float
    quantity: float
    side: Literal["BUY", "SELL"]

# Protocol example
class DataSource(Protocol):
    def fetch_data(self, symbol: str, interval: str) -> list[dict[str, float]]:
        ...

# Generics example
T = TypeVar('T')
class Repository(Generic[T]):
    def get(self, id: str) -> T | None:
        ...

    def save(self, entity: T) -> None:
        ...

# Overload example (only use when absolutely necessary)
@overload
def process_data(data: list[float]) -> float: ...

@overload
def process_data(data: list[str]) -> str: ...

def process_data(data: list[float] | list[str]) -> float | str:
    """Process data based on its type."""
    if all(isinstance(x, float) for x in data):
        return sum(data) / len(data)
    return "".join(data)
```

### No Function Overloading

Function overloading (creating multiple functions with the same name but different signatures) is **strictly prohibited** in KavziTrader. This is because Python does not natively support function overloading, and attempting to implement it leads to confusion and bugs.

```python
# ❌ INCORRECT - Function overloading
def calculate_metric(values: list[float]) -> float:
    return sum(values) / len(values)

def calculate_metric(values: list[float], weights: list[float]) -> float:  # This will simply replace the previous function
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


# ✅ CORRECT - Distinct function names
def calculate_simple_average(values: list[float]) -> float:
    return sum(values) / len(values)

def calculate_weighted_average(values: list[float], weights: list[float]) -> float:
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


# ✅ CORRECT - Single function with optional parameters
def calculate_average(
    values: list[float],
    weights: list[float] | None = None
) -> float:
    """Calculate average, optionally weighted.

    Args:
        values: The values to average
        weights: Optional weights for each value

    Returns:
        The average value
    """
    if weights is None:
        return sum(values) / len(values)
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)
```

While the `@overload` decorator exists in Python's typing module, it is **only** for type checking purposes and doesn't affect runtime behavior. In KavziTrader, even this usage should be minimized and only used when absolutely necessary for complex type hints that cannot be expressed otherwise.

When faced with what might look like a use case for overloading:
1. Create functions with distinct, descriptive names that indicate their specific purpose
2. Use optional parameters with clear defaults
3. Consider using factory functions or class methods for complex creation patterns
4. Use the Strategy pattern for varying implementations

### Function Design

- Keep functions small and focused (usually < 30 lines)
- Functions should do one thing and do it well
- Use descriptive function names that indicate what they do
- Limit function parameters (ideally ≤ 5)
- Use keyword arguments for clarity
- Return meaningful values or exceptions
- Document function purpose, parameters, and return values

```python
# Good
def calculate_moving_average(
    prices: list[float],
    window: int = 20,
    method: Literal["simple", "exponential"] = "simple",
) -> list[float]:
    """
    Calculate moving average for a series of prices.

    Args:
        prices: List of price values
        window: Window size for moving average
        method: Method to use ('simple' or 'exponential')

    Returns:
        List of moving average values

    Raises:
        ValueError: If window size is larger than prices list or <= 0
    """
    if window <= 0 or window > len(prices):
        raise ValueError(f"Invalid window size: {window}")

    if method == "simple":
        return _calculate_simple_ma(prices, window)
    elif method == "exponential":
        return _calculate_exponential_ma(prices, window)
    else:
        # This should never happen due to Literal type, but for safety
        raise ValueError(f"Unsupported method: {method}")
```

### Error Handling

- Use specific exception types
- Handle exceptions at the appropriate level
- Prefer context managers (`with` statements) for resource management
- Add context information to exceptions when re-raising
- Fail early and clearly

```python
# Good
try:
    data = fetch_market_data(symbol, interval)
    process_data(data)
except HTTPError as e:
    logger.error(f"Failed to fetch market data: {e}")
    raise MarketDataError(f"Could not retrieve data for {symbol}") from e
except (ValueError, KeyError) as e:
    logger.error(f"Invalid data format: {e}")
    raise DataProcessingError(f"Could not process {symbol} data") from e
```

### Logging

Proper logging is essential for monitoring and debugging. Each module should have its own logger instance.

```python
import logging

# Module-level logger
logger = logging.getLogger(__name__)

def process_data(data: list[dict[str, float]]) -> dict[str, float]:
    """Process market data."""
    logger.debug("Processing %d data points", len(data))

    try:
        # Critical operations should be logged
        logger.info("Starting data analysis")
        result = perform_calculation(data)
        logger.info("Data analysis completed")

        # Detailed debugging info
        logger.debug("Result summary: %s", summarize(result))

        return result
    except Exception as e:
        # Log errors with context and full traceback
        logger.exception("Data processing failed: %s", e)
        raise
```

#### Logging Levels

- `DEBUG`: Detailed information for diagnosing problems
- `INFO`: Confirmation that things are working as expected
- `WARNING`: Something unexpected happened, but the application can still work
- `ERROR`: A problem that prevented execution of a function
- `CRITICAL`: A serious error that may prevent the application from continuing

#### Logging Best Practices

1. **Always use `logger.exception()` instead of `logger.error()` when handling exceptions**
   - `logger.exception()` automatically includes the full traceback in the log
   - Only use `logger.exception()` within an exception handler (try/except block)

```python
# ❌ WRONG - Using logger.error for exceptions
try:
    do_something()
except Exception as e:
    logger.error(f"Failed to do something: {e}")
    raise

# ✅ CORRECT - Using logger.exception
try:
    do_something()
except Exception as e:
    logger.exception("Failed to do something: %s", e)
    raise
```

2. **Avoid f-strings in log messages**
   - Use string formatting with positional arguments instead
   - This allows for lazy evaluation of expensive operations if the log level is not enabled
   - It also allows log systems to handle object formatting more efficiently

```python
# ❌ WRONG - Using f-strings in logs
user_count = get_user_count()  # Potentially expensive operation
logger.debug(f"Found {user_count} users")

# ✅ CORRECT - Using string formatting
logger.debug("Found %d users", get_user_count())  # Only evaluated if debug is enabled
```

3. **Include contextual information in log messages**
   - Make sure logs contain enough information to understand what happened
   - For repetitive operations, include identifiers (IDs, names, etc.)

```python
# ❌ WRONG - Vague log message
logger.info("Processing completed")

# ✅ CORRECT - Specific log message with context
logger.info("Order processing completed for order_id=%s, items=%d", order_id, len(items))
```

4. **Use structured logging for complex data**
   - For complex objects, pass them as extra fields rather than forcing them into the message
   - This keeps logs readable while allowing full access to data when needed

```python
# ✅ CORRECT - Structured logging with extra fields
logger.info("User profile updated", extra={
    "user_id": user.id,
    "updated_fields": list(changed_fields),
    "source_ip": request.remote_addr
})
```

### Code Layout and Formatting

- Use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Line length: 88 characters (same as Black)
- 4 spaces for indentation (no tabs)
- Blank lines: 2 before top-level classes/functions, 1 between methods
- Imports at the top of the file, grouped as: standard library, third-party, local
- Use absolute imports within the package

### Documentation

- Use docstrings for all modules, classes, and functions
- Follow Google-style docstring format
- Keep docstrings up-to-date with code changes
- Document complex logic with inline comments
- Update README.md and other markdown documentation for significant changes

```python
def calculate_sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate the Sharpe ratio of an investment.

    The Sharpe ratio measures the performance of an investment compared
    to a risk-free asset, adjusted for risk.

    Args:
        returns: List of period returns (not annualized)
        risk_free_rate: Risk-free rate per period (not annualized)
        periods_per_year: Number of periods in a year (252 for daily, 12 for monthly)

    Returns:
        The annualized Sharpe ratio

    Raises:
        ValueError: If returns is empty or has no variance
    """
```

## Clean Architecture Patterns

### Dependency Injection

- Inject dependencies instead of creating them within functions
- Use dependency inversion to decouple high-level modules from low-level modules
- Consider using a dependency injection container for complex applications

```python
# Good - Dependencies injected
class TradingStrategy:
    def __init__(self, data_source: DataSource, risk_manager: RiskManager):
        self.data_source = data_source
        self.risk_manager = risk_manager

    def execute(self, symbol: str) -> TradeDecision:
        data = self.data_source.fetch_data(symbol)
        position_size = self.risk_manager.calculate_position_size(symbol)
        # Rest of the logic

# Bad - Hard-coded dependencies
class TradingStrategy:
    def __init__(self):
        self.data_source = BinanceDataSource()  # Hard-coded dependency
        self.risk_manager = DefaultRiskManager()  # Hard-coded dependency
```

### Command Query Separation

- Separate commands (functions that change state) from queries (functions that return values)
- Commands should return None or status information
- Queries should have no side effects

```python
# Good
def get_account_balance(account_id: str) -> float:
    """Query: Get account balance."""
    # Return balance without side effects

def execute_trade(order: Order) -> TradeResult:
    """Command: Execute a trade."""
    # Change state and return result
```

### Pydantic Models

Pydantic provides data validation and settings management through Python type annotations. It's particularly useful for configuration and API data validation.

**Note: KavziTrader exclusively uses Pydantic for all data modeling. The use of Python's dataclasses is NOT allowed in this project.**

#### Benefits of Pydantic

- **Data Validation**: Enforces type checking and data constraints
- **Data Parsing**: Handles data conversion
- **Serialization/Deserialization**: To/from JSON, dictionaries, and other formats
- **Schema Generation**: Creates JSON Schema from models
- **Setting Management**: Environment variables and config files

#### When to Use Pydantic

- For API requests and responses
- For configuration management
- For complex data validation
- When working with external data sources

#### Minimize Dictionary Usage

Always prefer Pydantic models over raw dictionaries for structured data. Dictionaries lack:

- Type safety
- Documentation
- Validation
- Self-documentation
- Good IDE support

```python
# ❌ WRONG - Using dictionaries for structured data
def process_trade(trade_dict: dict[str, Any]) -> dict[str, Any]:
    price = trade_dict["price"]
    quantity = trade_dict["quantity"]
    # Risk of KeyError, no type checking for values
    return {"result": "success", "value": price * quantity}

# ✅ CORRECT - Using Pydantic models
class TradeSchema(BaseModel):
    symbol: str
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)

class TradeResultSchema(BaseModel):
    result: Literal["success", "failure"]
    value: float

def process_trade(trade: TradeSchema) -> TradeResultSchema:
    return TradeResultSchema(result="success", value=trade.price * trade.quantity)
```

The benefits include:
- Automatic validation of input data
- IDE autocomplete for model fields
- Better code documentation through type annotations
- Runtime type safety
- Clear separation of concerns

For complex nested data structures, use Pydantic models throughout the hierarchy:

# ❌ WRONG - Using nested dictionaries
def analyze_portfolio(portfolio: dict[str, Any]) -> dict[str, Any]:
    total_value = 0
    for asset in portfolio["assets"]:
        total_value += asset["price"] * asset["quantity"]

    return {
        "portfolio_id": portfolio["id"],
        "analysis": {
            "total_value": total_value,
            "asset_count": len(portfolio["assets"]),
            "date": datetime.now().isoformat()
        }
    }

# ✅ CORRECT - Using nested Pydantic models
from datetime import datetime
from typing import Annotated, list
from pydantic import BaseModel, Field

class AssetSchema(BaseModel):
    symbol: str
    price: Annotated[float, Field(gt=0)]
    quantity: Annotated[float, Field(gt=0)]

class PortfolioSchema(BaseModel):
    id: str
    name: str
    assets: list[AssetSchema]

class AnalysisResultSchema(BaseModel):
    total_value: float
    asset_count: int
    date: datetime

class PortfolioAnalysisSchema(BaseModel):
    portfolio_id: str
    analysis: AnalysisResultSchema

def analyze_portfolio(portfolio: PortfolioSchema) -> PortfolioAnalysisSchema:
    total_value = sum(asset.price * asset.quantity for asset in portfolio.assets)

    return PortfolioAnalysisSchema(
        portfolio_id=portfolio.id,
        analysis=AnalysisResultSchema(
            total_value=total_value,
            asset_count=len(portfolio.assets),
            date=datetime.now()
        )
    )
```

#### Prefer Annotated Fields

Use `Annotated[T, Field(...)]` syntax instead of `:T = Field(...)` for cleaner code and better separation of type annotations from validation rules.

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field

# ❌ ACCEPTABLE but not preferred
class UserOldSchema(BaseModel):
    id: int = Field(...)
    name: str = Field(min_length=2)
    email: str = Field(pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    age: int = Field(ge=18)

# ✅ PREFERRED - Using Annotated syntax
class UserSchema(BaseModel):
    id: Annotated[int, Field(...)]
    name: Annotated[str, Field(min_length=2)]
    email: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")]
    age: Annotated[int, Field(ge=18)]
```

Benefits of using `Annotated`:
- Better separation of type information from validation rules
- Cleaner type hints when viewed in IDEs and documentation tools
- More flexible when adding multiple metadata annotations
- Future-proofing for additional type-related features

#### Important: Use model_validate Instead of ** Unpacking

Never use the `**` unpacking operator to create Pydantic model instances from dictionaries or other objects. This bypasses validation and type conversions. Always use `model_validate` instead:

```python
# ❌ WRONG - bypasses validation
user = UserSchema(**data_dict)

# ✅ CORRECT - ensures proper validation
user = UserSchema.model_validate(data_dict)

# ❌ WRONG - bypasses validation
db_user = UserSchema(**db_model.__dict__)

# ✅ CORRECT - ensures proper validation
db_user = UserSchema.model_validate(db_model)
```

For JSON data, use the appropriate method:

```python
# ✅ CORRECT - for JSON strings
user = UserSchema.model_validate_json(json_string)
```

The `model_validate` approach:
- Ensures all validation rules are applied
- Provides better error messages
- Handles nested models properly
- Properly converts types
- Works with both dictionaries and objects (with from_attributes=True)

#### FastAPI Integration

When working with FastAPI, follow these best practices:

- Use `response_model` to define return types for endpoints
- Create separate models for request (input) and response (output) data
- Use proper status codes with endpoints (e.g., 201 for creation)
- Leverage path and query parameter validation
- Handle errors with appropriate HTTP status codes

```python
from fastapi import FastAPI, HTTPException, Depends
from typing import Literal
from pydantic import BaseModel, Field

app = FastAPI()

class TradeOrderRequestSchema(BaseModel):
    """Model for trade order request data."""
    symbol: str = Field(..., min_length=2, max_length=20)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0)
    price: float | None = Field(None, gt=0)

class TradeOrderResponseSchema(BaseModel):
    """Model for trade order response data."""
    id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float | None
    status: Literal["PENDING", "FILLED", "REJECTED"]

    # Use model_config instead of inner Config class
    model_config = {"from_attributes": True}

@app.post("/orders", response_model=TradeOrderResponseSchema, status_code=201)
async def create_order(order: TradeOrderRequestSchema):
    # Process the order
    db_order = await process_order(order)

    # Return the order (automatically converted to TradeOrderResponseSchema)
    return db_order
```

#### Best Practices for Pydantic Models

```python
from datetime import datetime
from typing import Literal
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
)


class TradeOrderSchema(BaseModel):
    """Model representing a trade order."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., min_length=2, max_length=20)
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    quantity: float = Field(..., gt=0)
    price: float | None = Field(None, gt=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate and standardize the symbol."""
        return v.upper()

    @model_validator(mode="after")
    def validate_price(self) -> "TradeOrderSchema":
        """Ensure price is provided for limit orders."""
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("Price must be specified for LIMIT orders")
        return self


class TradingStrategyConfigSchema(BaseModel):
    """Model for trading strategy configuration."""

    name: str
    description: str | None = None
    enabled: bool = True

    # Strategy parameters
    lookback_period: int = Field(20, ge=1, le=200)
    threshold: float = Field(0.5, ge=0, le=1.0)

    # Risk management
    max_position_size: float = Field(..., gt=0)
    stop_loss_percent: float = Field(0.02, ge=0.01, le=0.1)
    take_profit_percent: float = Field(0.06, ge=0.01, le=0.5)

    @field_validator("take_profit_percent")
    @classmethod
    def validate_profit_ratio(cls, v: float, info) -> float:
        """Ensure take profit is at least 2x the stop loss."""
        data = info.data
        if "stop_loss_percent" in data and v < 2 * data["stop_loss_percent"]:
            raise ValueError("Take profit should be at least 2x the stop loss")
        return v

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return self.model_dump()

    @classmethod
    def from_json_file(cls, path: str) -> "TradingStrategyConfigSchema":
        """Load configuration from JSON file."""
        import json
        with open(path, "r") as f:
            data = json.load(f)
        return cls.model_validate(data)
```

#### Simple Data Models

Even for simple data containers without complex validation requirements, use Pydantic models with frozen config for immutability:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class MarketDataSchema(BaseModel):
    """Model representing market data for a specific timepoint."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)  # Volume can be zero
    timestamp: datetime

    @property
    def range(self) -> float:
        """Calculate price range (high - low)."""
        return self.high - self.low

    @property
    def change_percent(self) -> float:
        """Calculate percent change from open to close."""
        return (self.close - self.open) / self.open * 100
```

## Testing Standards

- Write tests for all functionality
- Use pytest for unit tests
- Aim for high test coverage (>90%)
- Write both unit and integration tests
- Use mock objects to isolate units for testing

```python
# Example test
def test_rsi_calculation():
    """Test RSI calculation function."""
    # Given
    prices = [10.0, 11.0, 10.5, 9.5, 10.0, 10.5, 11.5]

    # When
    rsi_values = calculate_rsi(prices, period=2)

    # Then
    assert len(rsi_values) == len(prices)
    assert rsi_values[0] is None  # First value should be None
    assert 0 <= rsi_values[-1] <= 100  # RSI is always between 0 and 100
```

## Version Control Practices

- Write clear, concise commit messages
- Use feature branches for new development
- Keep commits focused and atomic
- Create pull requests for code review before merging
- Follow semantic versioning for releases

## Conclusion

Following these coding standards will ensure that the KavziTrader codebase remains maintainable, robust, and extensible. These standards are not just rules to follow, but best practices that will make development more efficient and the final product more reliable.

## File and Class Organization

### One Class Per File

Each logical class should be placed in its own file. This enhances readability, maintainability, and ensures proper separation of concerns.

```
# ❌ WRONG - Multiple unrelated classes in one file
# trading_utils.py
class Strategy:
    # Strategy implementation

class RiskCalculator:
    # Risk calculator implementation

class MarketDataFetcher:
    # Data fetcher implementation


# ✅ CORRECT - One class per file
# strategy.py
class Strategy:
    # Strategy implementation

# risk_calculator.py
class RiskCalculator:
    # Risk calculator implementation

# market_data_fetcher.py
class MarketDataFetcher:
    # Data fetcher implementation
```

Related helper functions that specifically support a class should be in the same file as the class they support. Utility functions that are used across multiple classes should be placed in dedicated utility modules.

### File Path Handling

Always use `pathlib.Path` for file path manipulation instead of strings. Using strings for file paths is **strictly prohibited** in KavziTrader.

```python
# ❌ WRONG - Using strings for file paths
def read_config(config_file: str) -> dict:
    with open(config_file, "r") as f:
        return json.load(f)

def save_data(data: list, output_dir: str) -> None:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(os.path.join(output_dir, "data.json"), "w") as f:
        json.dump(data, f)


# ✅ CORRECT - Using Path objects
from pathlib import Path

def read_config(config_file: Path) -> dict:
    with open(config_file, "r") as f:
        return json.load(f)

def save_data(data: list, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "data.json", "w") as f:
        json.dump(data, f)
```

Benefits of using `Path` objects:
- Cross-platform compatibility
- More intuitive path manipulation with the `/` operator
- Built-in methods for common operations like `mkdir()`, `exists()`, `glob()`
- Type-safety and better IDE support
- Better error messages for path-related operations

Function parameters that accept paths should be typed as `Path` only, not `str | Path`, to enforce this standard:

```python
# ❌ WRONG - Allowing str for paths
def load_model(model_path: str | Path) -> Model:
    # Implementation

# ✅ CORRECT - Requiring Path
def load_model(model_path: Path) -> Model:
    # Implementation
```

### Class Naming Conventions

Use consistent naming patterns for different types of classes:

1. **Pydantic Classes**: All Pydantic models should use the `Schema` postfix.

```python
# ❌ WRONG
class User(BaseModel):
    username: str
    email: str

# ✅ CORRECT
class UserSchema(BaseModel):
    username: str
    email: str
```

2. **Service/Business Logic Classes**: Use descriptive names without specific postfixes.

```python
# Examples of correct service/business logic class names
class TradingStrategy:
    # Implementation

class RiskManager:
    # Implementation

class DataProcessor:
    # Implementation
```

### File Naming

- Use snake_case for file names
- File names should clearly reflect the primary class or functionality within
- Be descriptive but concise
- Group related files in appropriate packages/modules

```
src/
  models/
    schemas/
      user_schema.py       # Contains UserSchema
      order_schema.py      # Contains OrderSchema
      asset_schema.py      # Contains AssetSchema
  services/
    auth_service.py        # Contains AuthService
    order_service.py       # Contains OrderService
  utils/
    date_utils.py          # Date utility functions
    validation_utils.py    # Validation utility functions
```

### Import Organization

When organizing imports in a file with a single primary class:

1. Standard library imports
2. Third-party library imports
3. Local/application imports
4. Import the class's dependencies

This structure makes dependency relationships clear and facilitates dependency management.
