# KavziTrader Database Schema

This document outlines the database schema for the KavziTrader platform, including table structures, relationships, and implementation details.

## Overview

KavziTrader uses PostgreSQL as its primary database for storing market data, models, trading plans, and performance metrics. The database schema is designed to efficiently handle time-series data while maintaining relationships between various trading components.

## Database Design Principles

1. **Time-Series Optimization**: Optimized storage and indexing for efficient time-series queries
2. **Referential Integrity**: Foreign key constraints to maintain data consistency
3. **JSON Support**: Use of JSONB fields for flexible storage of configuration data
4. **Partitioning**: Table partitioning for large tables (e.g., market data) by time periods
5. **Indexing Strategy**: Strategic indexes on frequently queried columns
6. **Audit Trails**: Timestamps on all records for audit purposes

## Implementation Details

### PostgreSQL Configuration

The platform uses PostgreSQL 14+ with the following configuration considerations:

- TimescaleDB extension for time-series data optimization
- PG_TRGM extension for text search capabilities
- Appropriate shared_buffers and work_mem settings for trading workloads
- WAL (Write-Ahead Logging) configuration for durability and performance

### ORM Integration

SQLAlchemy is used as the ORM (Object-Relational Mapping) layer with the following components:

- Declarative base models for all entities
- Session management for transaction control
- Query building through SQLAlchemy expressions
- Custom types for trading-specific data

### Migration System

Database migrations are managed through Alembic with the following approach:

- Version-controlled migration scripts
- Automated migration generation
- Upgrade and downgrade capabilities
- Database initialization scripts

## Detailed Table Schemas

### Market Data Tables

#### `market_data` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| symbol | VARCHAR(20) | Trading pair symbol | NOT NULL |
| interval | VARCHAR(10) | Timeframe (1m, 5m, 1h, etc.) | NOT NULL |
| timestamp | TIMESTAMP | Data timestamp | NOT NULL |
| opened | DECIMAL(18,8) | Opening price | NOT NULL |
| high | DECIMAL(18,8) | Highest price | NOT NULL |
| low | DECIMAL(18,8) | Lowest price | NOT NULL |
| closed | DECIMAL(18,8) | Closing price | NOT NULL |
| volume | DECIMAL(24,8) | Trading volume | NOT NULL |
| quote_volume | DECIMAL(24,8) | Quote asset volume | NULL |
| trades | INTEGER | Number of trades | NULL |
| taker_buy_base_volume | DECIMAL(24,8) | Taker buy base volume | NULL |
| taker_buy_quote_volume | DECIMAL(24,8) | Taker buy quote volume | NULL |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Composite index on (symbol, interval, timestamp)
- Index on timestamp for time-based queries

#### `features` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| market_data_id | INTEGER | Reference to market data | FOREIGN KEY |
| feature_name | VARCHAR(100) | Name of the feature | NOT NULL |
| feature_value | DECIMAL(24,8) | Value of the feature | NOT NULL |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Index on market_data_id for fast lookups
- Composite index on (market_data_id, feature_name)

### Model Tables

#### `models` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| name | VARCHAR(100) | Model name | NOT NULL |
| version | VARCHAR(20) | Model version | NOT NULL |
| architecture | VARCHAR(100) | Model architecture type | NOT NULL |
| description | TEXT | Model description | NULL |
| file_path | VARCHAR(255) | Path to model file | NOT NULL |
| metrics | JSONB | Performance metrics | NULL |
| hyperparameters | JSONB | Hyperparameters used | NULL |
| created_at | TIMESTAMP | Model creation time | NOT NULL, DEFAULT NOW() |
| is_active | BOOLEAN | Whether model is active | NOT NULL, DEFAULT FALSE |

**Indexes**:
- Unique index on (name, version)
- Index on is_active

#### `model_training_runs` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| model_id | INTEGER | Reference to model | FOREIGN KEY |
| start_time | TIMESTAMP | Training start time | NOT NULL |
| end_time | TIMESTAMP | Training end time | NULL |
| epochs | INTEGER | Number of epochs trained | NOT NULL |
| parameters | JSONB | Training parameters | NOT NULL |
| train_metrics | JSONB | Training metrics | NULL |
| validation_metrics | JSONB | Validation metrics | NULL |
| dataset_info | JSONB | Information about the dataset | NOT NULL |
| status | VARCHAR(20) | Status of training run | NOT NULL |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |

### Trading Tables

#### `strategies` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| name | VARCHAR(100) | Strategy name | NOT NULL, UNIQUE |
| description | TEXT | Strategy description | NULL |
| model_id | INTEGER | Associated model ID | FOREIGN KEY |
| parameters | JSONB | Strategy parameters | NULL |
| created_at | TIMESTAMP | Strategy creation time | NOT NULL, DEFAULT NOW() |
| is_active | BOOLEAN | Whether strategy is active | NOT NULL, DEFAULT FALSE |

**Indexes**:
- Index on name
- Index on model_id
- Index on is_active

#### `trading_plans` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| name | VARCHAR(100) | Plan name | NOT NULL |
| description | TEXT | Plan description | NULL |
| strategy_id | INTEGER | Strategy ID | FOREIGN KEY |
| risk_parameters | JSONB | Risk management parameters | NOT NULL |
| entry_conditions | JSONB | Entry conditions | NOT NULL |
| exit_conditions | JSONB | Exit conditions | NOT NULL |
| schedule | JSONB | Trading schedule | NULL |
| filters | JSONB | Market filters | NULL |
| symbols | JSONB | Trading pairs | NOT NULL |
| created_at | TIMESTAMP | Plan creation time | NOT NULL, DEFAULT NOW() |
| is_active | BOOLEAN | Whether plan is active | NOT NULL, DEFAULT FALSE |

**Indexes**:
- Index on strategy_id
- Index on is_active
- Index on name

#### `trades` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| strategy_id | INTEGER | Strategy ID | FOREIGN KEY |
| plan_id | INTEGER | Trading plan ID | FOREIGN KEY |
| symbol | VARCHAR(20) | Trading pair | NOT NULL |
| side | VARCHAR(4) | BUY or SELL | NOT NULL |
| order_type | VARCHAR(20) | MARKET, LIMIT, etc. | NOT NULL |
| quantity | DECIMAL(24,8) | Order quantity | NOT NULL |
| price | DECIMAL(18,8) | Order price | NOT NULL |
| executed_price | DECIMAL(18,8) | Actual execution price | NULL |
| status | VARCHAR(20) | Order status | NOT NULL |
| profit_loss | DECIMAL(18,8) | P&L for this trade | NULL |
| profit_loss_percentage | DECIMAL(10,4) | P&L percentage | NULL |
| commission | DECIMAL(18,8) | Trading fee | NULL |
| order_id | VARCHAR(50) | Exchange order ID | NULL |
| entry_time | TIMESTAMP | Position entry time | NULL |
| exit_time | TIMESTAMP | Position exit time | NULL |
| entry_reason | TEXT | Reason for entry | NULL |
| exit_reason | TEXT | Reason for exit | NULL |
| is_paper_trading | BOOLEAN | Paper or real trading | NOT NULL |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Index on strategy_id
- Index on plan_id
- Index on symbol
- Index on entry_time
- Index on is_paper_trading
- Composite index on (symbol, entry_time)

### Performance and Portfolio Tables

#### `performance` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| strategy_id | INTEGER | Strategy ID | FOREIGN KEY |
| plan_id | INTEGER | Trading plan ID | FOREIGN KEY |
| start_time | TIMESTAMP | Period start time | NOT NULL |
| end_time | TIMESTAMP | Period end time | NOT NULL |
| total_trades | INTEGER | Number of trades | NOT NULL |
| winning_trades | INTEGER | Number of winning trades | NOT NULL |
| losing_trades | INTEGER | Number of losing trades | NOT NULL |
| win_rate | DECIMAL(5,2) | Win percentage | NOT NULL |
| profit_loss | DECIMAL(18,8) | Total P&L | NOT NULL |
| profit_loss_percentage | DECIMAL(10,4) | P&L percentage | NOT NULL |
| max_drawdown | DECIMAL(10,4) | Maximum drawdown | NOT NULL |
| sharpe_ratio | DECIMAL(10,4) | Sharpe ratio | NULL |
| average_profit | DECIMAL(18,8) | Average profit per trade | NULL |
| average_loss | DECIMAL(18,8) | Average loss per trade | NULL |
| profit_factor | DECIMAL(10,4) | Profit factor | NULL |
| recovery_factor | DECIMAL(10,4) | Recovery factor | NULL |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Index on strategy_id
- Index on plan_id
- Composite index on (strategy_id, start_time, end_time)

#### `portfolios` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| name | VARCHAR(100) | Portfolio name | NOT NULL |
| initial_balance | DECIMAL(18,8) | Initial portfolio value | NOT NULL |
| current_balance | DECIMAL(18,8) | Current portfolio value | NOT NULL |
| currency | VARCHAR(10) | Base currency | NOT NULL |
| is_paper_trading | BOOLEAN | Paper or real portfolio | NOT NULL |
| created_at | TIMESTAMP | Portfolio creation time | NOT NULL, DEFAULT NOW() |
| updated_at | TIMESTAMP | Last update time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Index on name
- Index on is_paper_trading

#### `portfolio_assets` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| portfolio_id | INTEGER | Portfolio ID | FOREIGN KEY |
| asset | VARCHAR(20) | Asset symbol | NOT NULL |
| quantity | DECIMAL(24,8) | Asset quantity | NOT NULL |
| average_buy_price | DECIMAL(18,8) | Average purchase price | NOT NULL |
| current_price | DECIMAL(18,8) | Current market price | NOT NULL |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |
| updated_at | TIMESTAMP | Last update time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Index on portfolio_id
- Composite index on (portfolio_id, asset)

### System Tables

#### `system_logs` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| log_level | VARCHAR(10) | DEBUG, INFO, WARNING, ERROR | NOT NULL |
| component | VARCHAR(100) | System component | NOT NULL |
| message | TEXT | Log message | NOT NULL |
| details | JSONB | Additional details | NULL |
| timestamp | TIMESTAMP | Log timestamp | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Index on log_level
- Index on component
- Index on timestamp

#### `system_config` Table
| Column | Type | Description | Constraints |
|--------|------|-------------|-------------|
| id | SERIAL | Unique identifier | PRIMARY KEY |
| key | VARCHAR(100) | Configuration key | NOT NULL, UNIQUE |
| value | TEXT | Configuration value | NOT NULL |
| description | TEXT | Description of config | NULL |
| is_editable | BOOLEAN | Whether config is user-editable | NOT NULL, DEFAULT TRUE |
| created_at | TIMESTAMP | Record creation time | NOT NULL, DEFAULT NOW() |
| updated_at | TIMESTAMP | Last update time | NOT NULL, DEFAULT NOW() |

**Indexes**:
- Unique index on key

## Database Relationships

### Primary Relationships

1. **Market Data to Features**:
   - One-to-many: Each market data point can have multiple features

2. **Models to Strategies**:
   - One-to-many: A model can be used by multiple strategies

3. **Strategies to Trading Plans**:
   - One-to-many: A strategy can be used in multiple trading plans

4. **Trading Plans to Trades**:
   - One-to-many: A trading plan can generate multiple trades

5. **Portfolios to Portfolio Assets**:
   - One-to-many: A portfolio contains multiple assets

## Database Query Examples

### SQLAlchemy Model Example

```python
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class MarketData(Base):
    __tablename__ = 'market_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    interval = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    open = Column(Numeric(18, 8), nullable=False)
    high = Column(Numeric(18, 8), nullable=False)
    low = Column(Numeric(18, 8), nullable=False)
    close = Column(Numeric(18, 8), nullable=False)
    volume = Column(Numeric(24, 8), nullable=False)
    quote_volume = Column(Numeric(24, 8))
    trades = Column(Integer)
    taker_buy_base_volume = Column(Numeric(24, 8))
    taker_buy_quote_volume = Column(Numeric(24, 8))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    features = relationship("Feature", back_populates="market_data")

    __table_args__ = (
        # Composite index for efficient time series queries
        {'postgresql_partition_by': 'RANGE (timestamp)'}
    )
```

### Common Query Operations

#### Fetching Recent Market Data

```python
# Get the last 24 hours of BTC data at 1-hour intervals
from datetime import datetime, timedelta
from sqlalchemy import desc

now = datetime.utcnow()
yesterday = now - timedelta(days=1)

recent_btc_data = session.query(MarketData).\
    filter(
        MarketData.symbol == 'BTCUSDT',
        MarketData.interval == '1h',
        MarketData.timestamp >= yesterday,
        MarketData.timestamp <= now
    ).\
    order_by(MarketData.timestamp.desc()).\
    all()
```

#### Calculating Performance Metrics

```python
# Get win rate for a strategy over the last month
from sqlalchemy import func

start_date = datetime.utcnow() - timedelta(days=30)

performance = session.query(
    func.count(Trade.id).label("total_trades"),
    func.sum(case([(Trade.profit_loss > 0, 1)], else_=0)).label("winning_trades")
).\
    filter(
        Trade.strategy_id == strategy_id,
        Trade.exit_time >= start_date
    ).\
    first()

win_rate = performance.winning_trades / performance.total_trades if performance.total_trades > 0 else 0
```

## Database Maintenance

### Backup Strategy

1. **Daily Full Backups**: Complete database backup every 24 hours
2. **Hourly WAL Archiving**: Continuous archiving of Write-Ahead Log for point-in-time recovery
3. **Retention Policy**: 7 days of full backups, 30 days of WAL archives

### Performance Optimization

1. **Regular VACUUM**: Schedule VACUUM ANALYZE to reclaim space and update statistics
2. **Index Maintenance**: Regular reindexing of fragmented indexes
3. **Partitioning Strategy**: Automatically create new partitions for time-series data
4. **Query Monitoring**: Track slow queries and optimize as needed

### Scaling Considerations

1. **Read Replicas**: Implementation of read replicas for reporting and analytics
2. **Partitioning**: Time-based partitioning for historical data
3. **Archive Strategy**: Moving older data to cold storage with restoration capability

## Security Implementation

1. **Role-Based Access**: Separate database roles for different access patterns
2. **Encryption**: Encryption of sensitive data fields
3. **Connection Security**: SSL/TLS for database connections
4. **Audit Logging**: Tracking of database changes and access patterns
