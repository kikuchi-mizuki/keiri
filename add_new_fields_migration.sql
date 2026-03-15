-- 会社情報拡張のためのマイグレーションスクリプト
-- 以下のフィールドを追加：
-- 1. name（代表者名/担当者名）
-- 2. phone_number（電話番号）
-- 3. bank_account_holder（口座名義）

-- PostgreSQL用
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bank_account_holder TEXT;

-- マイグレーション確認
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
