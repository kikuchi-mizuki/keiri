-- メールアドレスベース制限チェックシステム用データベースマイグレーション
-- Railway PostgreSQLで実行してください

-- 1. usersテーブルにemailカラムを追加
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD CONSTRAINT users_email_unique UNIQUE (email);

-- 2. 既存データの確認
SELECT id, line_user_id, email, created_at FROM users;

-- 3. テスト用データの挿入（必要に応じて）
-- 解約済みユーザーの例
INSERT INTO users (line_user_id, email, created_at) 
VALUES ('U1b9d0d75b0c770dc1107dde349d572f7', 'test@example.com', CURRENT_TIMESTAMP)
ON CONFLICT (line_user_id) DO UPDATE SET email = EXCLUDED.email;

-- 4. 解約履歴の確認
SELECT 
    ch.id,
    ch.user_id,
    u.line_user_id,
    u.email,
    ch.content_type,
    ch.cancelled_at
FROM cancellation_history ch
JOIN users u ON ch.user_id = u.id;

-- 5. インデックスの作成（パフォーマンス向上）
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_line_user_id ON users(line_user_id);
CREATE INDEX IF NOT EXISTS idx_cancellation_history_user_content ON cancellation_history(user_id, content_type);