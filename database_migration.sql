-- usage_logsベース制限チェックシステム用データベースマイグレーション
-- Railway PostgreSQLで実行してください

-- 1. usersテーブルにemailカラムを追加（既存の場合はスキップ）
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS line_user_id VARCHAR(255);

-- 2. 既存データの確認
SELECT id, email, line_user_id, stripe_customer_id, stripe_subscription_id FROM users;

-- 3. usage_logsテーブルの確認
SELECT 
    ul.id,
    ul.user_id,
    u.email,
    u.line_user_id,
    ul.content_type,
    ul.usage_quantity,
    ul.is_free,
    ul.created
FROM usage_logs ul
LEFT JOIN users u ON ul.user_id = u.id
ORDER BY ul.created DESC;

-- 4. テスト用データの挿入（必要に応じて）
-- 利用可能なユーザーの例（usage_logsに記録あり）
INSERT INTO usage_logs (user_id, usage_quantity, is_free, content_type, created)
SELECT id, 1, true, 'AI経理秘書', CURRENT_TIMESTAMP
FROM users 
WHERE email = 'test@example.com'
ON CONFLICT DO NOTHING;

-- 5. インデックスの作成（パフォーマンス向上）
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_line_user_id ON users(line_user_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_user_content ON usage_logs(user_id, content_type);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created ON usage_logs(created);

-- 6. 制限チェックのテストクエリ
-- 特定のメールアドレスでusage_logsをチェック
SELECT 
    u.id,
    u.email,
    u.line_user_id,
    COUNT(ul.id) as usage_count,
    CASE WHEN COUNT(ul.id) > 0 THEN '利用可能' ELSE '制限中' END as status
FROM users u
LEFT JOIN usage_logs ul ON u.id = ul.user_id AND ul.content_type = 'AI経理秘書'
WHERE u.email = 'test@example.com'
GROUP BY u.id, u.email, u.line_user_id;

-- 契約期間管理のためのテーブルを追加
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    content_type VARCHAR(100) NOT NULL,
    start_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active', 'cancelled', 'expired'
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- インデックスを作成
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_content ON subscriptions(user_id, content_type);
CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date ON subscriptions(end_date);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

-- 既存の usage_logs から契約期間を推定して subscriptions テーブルに移行するためのサンプルクエリ
-- 注意: 実際の運用では、既存データの移行戦略を慎重に検討してください
/*
INSERT INTO subscriptions (user_id, content_type, start_date, end_date, status)
SELECT 
    ul.user_id,
    ul.content_type,
    MIN(ul.created) as start_date,
    MAX(ul.created) + INTERVAL '30 days' as end_date, -- 仮定: 30日間の契約期間
    'active' as status
FROM usage_logs ul
WHERE ul.created >= CURRENT_DATE - INTERVAL '30 days' -- 最近30日間のデータのみ
GROUP BY ul.user_id, ul.content_type
ON CONFLICT (user_id, content_type) DO NOTHING;
*/