## Commons Package Classes and Functions

### 1. DateTime Schema Module (datetime_schema.py)

#### Classes:
- **DateTimeWithTimezoneSchema**
  - Base Pydantic model for handling datetime fields with timezone information
  - Use case: Ensure all datetime objects have proper timezone information (UTC)

- **TimestampedSchema**
  - Extends DateTimeWithTimezoneSchema to add created_at and updated_at fields
  - Use case: Base class for any model requiring standardized timestamp tracking

#### Functions:
- **ensure_timezone** (validator)
  - Validates and converts datetime fields to have UTC timezone
  - Use case: Validator for ensuring datetime fields have proper timezone information

### 2. Time Utility Module (time_utility.py)

#### Functions:
- **utc_now()**
  - Gets current UTC timestamp with timezone information
  - Use case: Generate consistent UTC timestamps across the application

- **timestamp_filename(prefix, extension="json")**
  - Generates a filename with current timestamp
  - Use case: Create unique filenames with timestamps (format: prefix_YYYYMMDD_HHMMSS.extension)

- **timestamp_path(prefix, directory, extension="json")**
  - Generates a full path with a timestamped filename
  - Use case: Create file paths with unique timestamped filenames

### 3. Logging Module (logging.py)

#### Functions:
- **setup_logging(config=None, log_level=None, log_file=None, console=True, name="kavzitrader")**
  - Sets up application logging with flexible configuration options
  - Use case: Initialize the application's logging system with console and/or file output

- **get_logger(name="kavzitrader")**
  - Gets a logger with the given name that inherits from root logger
  - Use case: Convenient way to get properly configured loggers across the application

### Summary
The commons package provides essential utilities for:
- Datetime handling with proper timezone support
- Consistent timestamp generation and formatting
- Centralized logging configuration
- Standard schemas for models requiring timestamp fields

These utilities ensure consistent handling of common concerns across the KavziTrader platform. 