#!/usr/bin/env python3

"""
Development setup script for KavziTrader.

This script creates necessary directories and performs initial setup for development.
"""

import sys
from pathlib import Path


def create_dirs() -> None:
    """
    Create necessary directories for development.

    Creates a structured set of directories for data, models, results, logs,
    trading plans, and local configuration.
    """
    # Get project root directory
    root_dir = Path(__file__).resolve().parent.parent

    # Directories to create
    dirs: list[Path] = [
        # Data and model storage
        root_dir / "data",
        root_dir / "data" / "raw",
        root_dir / "data" / "processed",
        root_dir / "models",
        root_dir / "results",
        root_dir / "logs",
        # Trading plans
        root_dir / "trading_plans",
        # Local configuration
        root_dir / "config" / "local",
    ]

    # Create directories
    for directory in dirs:
        if not directory.exists():
            print(f"Creating directory: {directory}")
            directory.mkdir(parents=True, exist_ok=True)
        else:
            print(f"Directory already exists: {directory}")


def create_local_env() -> None:
    """
    Create local environment file if it doesn't exist.

    Copies the .env.example file to .env if the latter doesn't exist,
    prompting the user to update it with their credentials.
    """
    root_dir = Path(__file__).resolve().parent.parent
    env_example = root_dir / ".env.example"
    env_file = root_dir / ".env"

    if not env_file.exists() and env_example.exists():
        print("Creating .env file from .env.example")
        env_file.write_text(env_example.read_text())
        print("Created .env file. Please update it with your credentials.")
    elif not env_example.exists():
        print("Warning: .env.example not found. Cannot create .env file.")
    else:
        print(".env file already exists.")


def main() -> int:
    """
    Run the development setup script.

    Creates directories and environment files for development.

    Returns:
        Exit code (0 for success)
    """
    print("Setting up development environment for KavziTrader...")

    # Create necessary directories
    create_dirs()

    # Create local environment file
    create_local_env()

    print("\nDevelopment setup complete.")
    print("Next steps:")
    print("1. Update the .env file with your API keys and database credentials")
    print("2. Run 'kavzitrader system setup --database' to initialize the database")
    print(
        "3. Run 'kavzitrader data fetch --symbol BTCUSDT --interval 1h --days 30' "
        "to fetch some initial data",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
