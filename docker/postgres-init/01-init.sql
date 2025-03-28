-- Initialize Postgres with extensions and basic configuration

-- Create extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- For text search capabilities
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- For UUID generation

-- Create a separate database for testing (if needed)
CREATE DATABASE kavzitrader_test;

-- Configure the main database
\c kavzitrader

-- Set up TimescaleDB extension if needed
-- Uncomment when TimescaleDB is activated
-- CREATE EXTENSION IF NOT EXISTS timescaledb

-- Add any other initialization here

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE kavzitrader TO postgres;
GRANT ALL PRIVILEGES ON DATABASE kavzitrader_test TO postgres;

-- Create users if needed
-- CREATE USER kavzitrader_app WITH PASSWORD 'app_password';
-- GRANT CONNECT ON DATABASE kavzitrader TO kavzitrader_app;
-- GRANT USAGE ON SCHEMA public, market_data, trading, models, system TO kavzitrader_app;
