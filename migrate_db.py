#!/usr/bin/env python3
"""
データベースマイグレーションスクリプト
"""

import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lp.utils.db import migrate_add_pending_charge

def main():
    print("🔄 データベースマイグレーションを開始します...")
    
    try:
        migrate_add_pending_charge()
        print("✅ マイグレーションが完了しました")
    except Exception as e:
        print(f"❌ マイグレーションエラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 