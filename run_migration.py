#!/usr/bin/env python3
"""
データベースマイグレーション実行スクリプト

使用方法:
    python run_migration.py

環境変数:
    DATABASE_URL: PostgreSQLの接続URL（必須）
"""

import os
import sys
import psycopg2

def run_migration():
    """マイグレーションSQLを実行"""

    # DATABASE_URLを取得
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ エラー: DATABASE_URL環境変数が設定されていません")
        print("\n使用方法:")
        print("  export DATABASE_URL='your_database_url'")
        print("  python run_migration.py")
        sys.exit(1)

    print("🔄 データベースマイグレーションを開始します...")
    print(f"📍 接続先: {database_url[:30]}...")

    try:
        # データベースに接続
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        print("✅ データベースに接続しました")

        # マイグレーションSQL
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS bank_account_holder TEXT;"
        ]

        # 各マイグレーションを実行
        for i, sql in enumerate(migrations, 1):
            print(f"\n🔧 マイグレーション {i}/{len(migrations)} を実行中...")
            print(f"   SQL: {sql}")
            cursor.execute(sql)
            print(f"✅ 完了")

        # コミット
        conn.commit()
        print("\n✅ すべてのマイグレーションが正常に完了しました")

        # 確認クエリ: usersテーブルのカラム一覧を取得
        print("\n📋 現在のusersテーブルのカラム:")
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position;
        """)

        columns = cursor.fetchall()
        for col_name, col_type in columns:
            print(f"   - {col_name}: {col_type}")

        # クリーンアップ
        cursor.close()
        conn.close()
        print("\n✅ データベース接続をクローズしました")

        return True

    except psycopg2.Error as e:
        print(f"\n❌ データベースエラーが発生しました:")
        print(f"   {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 予期しないエラーが発生しました:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("  データベースマイグレーション")
    print("  会社情報フィールド追加: name, phone_number, bank_account_holder")
    print("=" * 60)

    run_migration()

    print("\n" + "=" * 60)
    print("  🎉 マイグレーション完了!")
    print("=" * 60)
