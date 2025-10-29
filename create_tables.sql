-- 基本的なテーブル作成スクリプト
-- Railway PostgreSQLで実行してください

-- 1. sessionsテーブルの作成
CREATE TABLE IF NOT EXISTS sessions (
    user_id VARCHAR(255) PRIMARY KEY,
    session_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. usersテーブルの作成
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    company_name TEXT,
    address TEXT,
    bank_account TEXT,
    google_refresh_token TEXT,
    spreadsheet_id TEXT,
    estimate_spreadsheet_id TEXT,
    invoice_spreadsheet_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. インデックスの作成
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at);

-- 4. テーブル作成確認
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name IN ('sessions', 'users') 
ORDER BY table_name, ordinal_position;

-- 5. テーブル件数確認
SELECT 'sessions' as table_name, COUNT(*) as count FROM sessions
UNION ALL
SELECT 'users' as table_name, COUNT(*) as count FROM users;
