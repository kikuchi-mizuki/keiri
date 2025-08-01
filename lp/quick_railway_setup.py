#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Railwayトークン一度だけ設定スクリプト
"""

import os
import sys

def quick_railway_setup():
    """Railwayトークンを一度だけ設定"""
    try:
        print("=== Railwayトークン一度だけ設定 ===")
        
        # 現在の設定を確認
        railway_token = os.getenv('RAILWAY_TOKEN')
        railway_project_id = os.getenv('RAILWAY_PROJECT_ID')
        
        if railway_token and railway_project_id:
            print("✅ Railwayトークンは既に設定されています")
            print(f"  RAILWAY_TOKEN: {'設定済み'}")
            print(f"  RAILWAY_PROJECT_ID: {railway_project_id}")
            print("\n🎉 設定完了！企業登録フォームを試してください。")
            return True
        
        print("\n📋 Railwayトークンを一度だけ設定してください")
        print("この設定は一度行えば、以降の企業登録で自動的に使用されます。")
        print("\n手順:")
        print("1. https://railway.app/dashboard にログイン")
        print("2. 右上のプロフィールアイコン → Account Settings → API")
        print("3. Generate Token でトークンを生成")
        print("4. 生成されたトークンをコピー")
        
        # ユーザーからRailwayトークンを入力
        railway_token = input("\nRailwayトークンを入力してください: ").strip()
        
        if not railway_token:
            print("❌ Railwayトークンが入力されていません")
            return False
        
        # プロジェクトIDを入力
        print("\n📋 RailwayプロジェクトIDを取得してください")
        print("1. Railwayダッシュボードでプロジェクトを開く")
        print("2. URLからプロジェクトIDを確認")
        print("   例: https://railway.app/project/3e9475ce-ff6a-4443-ab6c-4eb21b7f4017")
        print("   プロジェクトID: 3e9475ce-ff6a-4443-ab6c-4eb21b7f4017")
        
        railway_project_id = input("\nRailwayプロジェクトIDを入力してください: ").strip()
        
        if not railway_project_id:
            print("❌ RailwayプロジェクトIDが入力されていません")
            return False
        
        # ベースドメインを設定
        base_domain = "lp-production-9e2c.up.railway.app"
        
        # .envファイルを作成または更新
        env_file = '.env'
        env_content = f"""# Railway設定（一度だけ設定）
RAILWAY_TOKEN={railway_token}
RAILWAY_PROJECT_ID={railway_project_id}
BASE_DOMAIN={base_domain}

# その他の環境変数（必要に応じて追加）
"""
        
        try:
            with open(env_file, 'w') as f:
                f.write(env_content)
            
            print(f"✅ Railway設定を{env_file}に保存しました")
            
            # 環境変数としても設定
            os.environ['RAILWAY_TOKEN'] = railway_token
            os.environ['RAILWAY_PROJECT_ID'] = railway_project_id
            os.environ['BASE_DOMAIN'] = base_domain
            
            print("✅ 環境変数としても設定しました")
            
            # 設定確認
            print(f"\n📊 設定内容:")
            print(f"  RAILWAY_TOKEN: {'設定済み' if os.getenv('RAILWAY_TOKEN') else '未設定'}")
            print(f"  RAILWAY_PROJECT_ID: {os.getenv('RAILWAY_PROJECT_ID') or '未設定'}")
            print(f"  BASE_DOMAIN: {os.getenv('BASE_DOMAIN') or '未設定'}")
            
            return True
            
        except Exception as e:
            print(f"❌ ファイル保存エラー: {e}")
            return False
            
    except Exception as e:
        print(f"❌ 設定エラー: {e}")
        return False

def test_railway_connection():
    """Railway接続をテスト"""
    try:
        print("\n=== Railway接続テスト ===")
        
        railway_token = os.getenv('RAILWAY_TOKEN')
        railway_project_id = os.getenv('RAILWAY_PROJECT_ID')
        
        if not railway_token or not railway_project_id:
            print("❌ Railway設定が不完全です")
            return False
        
        import requests
        
        headers = {
            'Authorization': f'Bearer {railway_token}',
            'Content-Type': 'application/json'
        }
        
        query = """
        query {
            me {
                id
                email
                name
            }
        }
        """
        
        response = requests.post(
            'https://backboard.railway.app/graphql/v2',
            headers=headers,
            json={'query': query},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'me' in data['data']:
                user = data['data']['me']
                print(f"✅ Railway接続成功")
                print(f"  ユーザー: {user['name']} ({user['email']})")
                return True
            else:
                print("❌ Railwayトークンが無効です")
                return False
        else:
            print(f"❌ Railway APIエラー: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 接続テストエラー: {e}")
        return False

if __name__ == "__main__":
    if quick_railway_setup():
        print("\n🎉 Railwayトークン設定が完了しました！")
        
        # 接続テスト
        if test_railway_connection():
            print("\n✅ すべての設定が正常に完了しました！")
            print("\n📝 次のステップ:")
            print("1. 企業登録フォームにアクセス")
            print("2. 企業情報を入力")
            print("3. フォーム送信時にRailwayプロジェクトが自動複製されます")
            print("\n💡 この設定は一度だけ行えば、以降の企業登録で自動的に使用されます。")
        else:
            print("\n⚠️ 接続テストに失敗しました。設定を確認してください。")
    else:
        print("\n❌ Railwayトークン設定に失敗しました。") 