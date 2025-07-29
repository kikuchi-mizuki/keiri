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

-- 5. インデックスを作成（パフォーマンス向上）
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

-- Stripeサブスクリプション期間管理のためのテーブルを追加
CREATE TABLE IF NOT EXISTS subscription_periods (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    stripe_subscription_id VARCHAR(255) NOT NULL,
    subscription_status VARCHAR(50) NOT NULL, -- 'active', 'trialing', 'canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'past_due'
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- subscription_periodsテーブルのインデックスを作成
CREATE INDEX IF NOT EXISTS idx_subscription_periods_user_id ON subscription_periods(user_id);
CREATE INDEX IF NOT EXISTS idx_subscription_periods_stripe_id ON subscription_periods(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscription_periods_status ON subscription_periods(subscription_status);
CREATE INDEX IF NOT EXISTS idx_subscription_periods_created ON subscription_periods(created_at);

-- テスト用データの挿入（subscription_periodsテーブル）
-- 注意: 実際の運用では、既存のユーザーIDを使用してください
INSERT INTO subscription_periods (user_id, stripe_subscription_id, subscription_status, current_period_start, current_period_end)
VALUES 
    (1, 'sub_active_001', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 days'),
    (2, 'sub_trialing_001', 'trialing', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '7 days'),
    (3, 'sub_canceled_001', 'canceled', CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
    (4, 'sub_incomplete_001', 'incomplete', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 days'),
    (5, 'sub_unpaid_001', 'unpaid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 days')
ON CONFLICT DO NOTHING;

-- 新しい判定ロジックのテストクエリ
-- 特定のユーザーのサブスクリプション状態をチェック
SELECT 
    u.id,
    u.email,
    u.line_user_id,
    sp.subscription_status,
    sp.current_period_end,
    CASE 
        WHEN sp.subscription_status IN ('active', 'trialing') THEN '利用可能'
        WHEN sp.subscription_status IN ('canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'past_due') THEN '利用不可'
        ELSE '利用不可（レコードなし）'
    END as availability_status
FROM users u
LEFT JOIN subscription_periods sp ON u.id = sp.user_id AND sp.stripe_subscription_id IS NOT NULL
WHERE u.id IN (1, 2, 3, 4, 5)
ORDER BY u.id;

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