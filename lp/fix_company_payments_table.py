#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
company_paymentsテーブルのスキーマ修正スクリプト
"""

import os
import sys
from utils.db import get_db_connection, get_db_type

def fix_company_payments_table():
    """company_paymentsテーブルのスキーマを修正"""
    try:
        print("=== company_paymentsテーブルスキーマ修正 ===")
        
        conn = get_db_connection()
        c = conn.cursor()
        
        db_type = get_db_type()
        print(f"データベースタイプ: {db_type}")
        
        if db_type == 'postgresql':
            # PostgreSQL用のスキーマ修正
            
            # 1. テーブルが存在するかチェック
            c.execute('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'company_payments'
                )
            ''')
            
            if not c.fetchone()[0]:
                print("company_paymentsテーブルを作成中...")
                c.execute('''
                    CREATE TABLE company_payments (
                        id SERIAL PRIMARY KEY,
                        company_id INTEGER NOT NULL,
                        stripe_subscription_id VARCHAR(255),
                        content_type VARCHAR(100),
                        amount INTEGER,
                        status VARCHAR(50) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
                    )
                ''')
                print("✅ company_paymentsテーブルを作成しました")
            else:
                print("company_paymentsテーブルは既に存在します")
                
                # 既存のテーブル構造を確認
                c.execute('''
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'company_payments'
                    ORDER BY ordinal_position
                ''')
                
                existing_columns = [row[0] for row in c.fetchall()]
                print(f"既存のカラム: {existing_columns}")
                
                # 不足しているカラムを追加
                if 'content_type' not in existing_columns:
                    print("content_typeカラムを追加中...")
                    c.execute('''
                        ALTER TABLE company_payments 
                        ADD COLUMN content_type VARCHAR(100)
                    ''')
                    print("✅ content_typeカラムを追加しました")
                
                if 'amount' not in existing_columns:
                    print("amountカラムを追加中...")
                    c.execute('''
                        ALTER TABLE company_payments 
                        ADD COLUMN amount INTEGER
                    ''')
                    print("✅ amountカラムを追加しました")
                
                if 'status' not in existing_columns:
                    print("statusカラムを追加中...")
                    c.execute('''
                        ALTER TABLE company_payments 
                        ADD COLUMN status VARCHAR(50) DEFAULT 'active'
                    ''')
                    print("✅ statusカラムを追加しました")
                
                if 'created_at' not in existing_columns:
                    print("created_atカラムを追加中...")
                    c.execute('''
                        ALTER TABLE company_payments 
                        ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ''')
                    print("✅ created_atカラムを追加しました")
            
        else:
            # SQLite用のスキーマ修正
            c.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='company_payments'
            ''')
            
            if not c.fetchone():
                print("company_paymentsテーブルを作成中...")
                c.execute('''
                    CREATE TABLE company_payments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id INTEGER NOT NULL,
                        stripe_subscription_id TEXT,
                        content_type TEXT,
                        amount INTEGER,
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (id)
                    )
                ''')
                print("✅ company_paymentsテーブルを作成しました")
            else:
                print("company_paymentsテーブルは既に存在します")
                
                # 既存のテーブル構造を確認
                c.execute('PRAGMA table_info(company_payments)')
                existing_columns = [row[1] for row in c.fetchall()]
                print(f"既存のカラム: {existing_columns}")
                
                # 不足しているカラムを追加
                if 'content_type' not in existing_columns:
                    print("content_typeカラムを追加中...")
                    c.execute('ALTER TABLE company_payments ADD COLUMN content_type TEXT')
                    print("✅ content_typeカラムを追加しました")
                
                if 'amount' not in existing_columns:
                    print("amountカラムを追加中...")
                    c.execute('ALTER TABLE company_payments ADD COLUMN amount INTEGER')
                    print("✅ amountカラムを追加しました")
                
                if 'status' not in existing_columns:
                    print("statusカラムを追加中...")
                    c.execute('ALTER TABLE company_payments ADD COLUMN status TEXT DEFAULT "active"')
                    print("✅ statusカラムを追加しました")
                
                if 'created_at' not in existing_columns:
                    print("created_atカラムを追加中...")
                    c.execute('ALTER TABLE company_payments ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                    print("✅ created_atカラムを追加しました")
        
        conn.commit()
        conn.close()
        
        print("✅ company_paymentsテーブルのスキーマ修正が完了しました")
        
        # 修正後のテーブル構造を確認
        verify_table_structure()
        
        return True
        
    except Exception as e:
        print(f"❌ スキーマ修正エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_table_structure():
    """テーブル構造を確認"""
    try:
        print("\n=== 修正後のテーブル構造確認 ===")
        
        conn = get_db_connection()
        c = conn.cursor()
        
        db_type = get_db_type()
        
        if db_type == 'postgresql':
            # PostgreSQL用の構造確認
            c.execute('''
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'company_payments'
                ORDER BY ordinal_position
            ''')
            
            columns = c.fetchall()
            
            print("📋 company_payments テーブル構造:")
            for column in columns:
                print(f"  - {column[0]}: {column[1]} ({'NULL可' if column[2] == 'YES' else 'NULL不可'})")
                if column[3]:
                    print(f"    デフォルト値: {column[3]}")
            
        else:
            # SQLite用の構造確認
            c.execute('PRAGMA table_info(company_payments)')
            columns = c.fetchall()
            
            print("📋 company_payments テーブル構造:")
            for column in columns:
                print(f"  - {column[1]}: {column[2]} ({'NULL可' if column[3] == 0 else 'NULL不可'})")
                if column[4]:
                    print(f"    デフォルト値: {column[4]}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ テーブル構造確認エラー: {e}")

def main():
    """メイン関数"""
    print("🚀 company_paymentsテーブルスキーマ修正を開始します")
    
    # スキーマ修正
    if fix_company_payments_table():
        print("✅ スキーマ修正が完了しました")
        
        print("\n🎉 company_paymentsテーブルの準備が完了しました！")
        print("\n📋 次のステップ:")
        print("1. 企業登録システムのテストを再実行")
        print("2. 企業情報登録フォームをテスト")
        print("3. 自動デプロイ機能をテスト")
        
    else:
        print("❌ スキーマ修正に失敗しました")

if __name__ == "__main__":
    main() 