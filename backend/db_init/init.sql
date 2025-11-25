-- Initial PostgreSQL setup
-- Runs automatically on first startup

-- Create UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create HSTORE extension for key-value storage
CREATE EXTENSION IF NOT EXISTS "hstore";

-- Verify database ready
SELECT 'DocuFlow PostgreSQL initialized successfully!' AS status;
