#!/usr/bin/env python3
"""
アプリケーション起動時の自動マイグレーション

このスクリプトはapp.pyから自動的に呼び出され、
データベースのマイグレーションを必要に応じて実行します。
"""

import os
import psycopg2
import logging

logger = logging.getLogger(__name__)

def check_and_migrate():
    """必要に応じてマイグレーションを実行"""

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        logger.warning("DATABASE_URL not set, skipping migration")
        return

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # カラムが存在するかチェック
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name IN ('name', 'phone_number', 'bank_account_holder');
        """)

        existing_columns = [row[0] for row in cursor.fetchall()]

        # 必要なマイグレーションを特定
        migrations_needed = []

        if 'name' not in existing_columns:
            migrations_needed.append(("name", "ALTER TABLE users ADD COLUMN name TEXT;"))

        if 'phone_number' not in existing_columns:
            migrations_needed.append(("phone_number", "ALTER TABLE users ADD COLUMN phone_number TEXT;"))

        if 'bank_account_holder' not in existing_columns:
            migrations_needed.append(("bank_account_holder", "ALTER TABLE users ADD COLUMN bank_account_holder TEXT;"))

        # マイグレーション実行
        if migrations_needed:
            logger.info(f"🔄 Running {len(migrations_needed)} migration(s)...")

            for col_name, sql in migrations_needed:
                logger.info(f"  Adding column: {col_name}")
                cursor.execute(sql)

            conn.commit()
            logger.info("✅ Migrations completed successfully")
        else:
            logger.info("✅ Database schema is up to date")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        # エラーが発生してもアプリケーションは起動を続ける
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    check_and_migrate()
