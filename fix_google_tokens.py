import sqlite3
import json

DB_PATH = "sessions.db"  # 必要に応じてパスを変更してください

def fix_google_tokens(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, google_refresh_token FROM users WHERE google_refresh_token LIKE '%;%'")
    rows = cursor.fetchall()

    fixed_count = 0
    for user_id, token in rows:
        if token:
            # セミコロンをカンマに置換し、残りのセミコロンも除去
            fixed = token.replace(';,', ',').replace(';', '')
            # JSONとしてパースできるかチェック
            try:
                json.loads(fixed)
                cursor.execute("UPDATE users SET google_refresh_token = ? WHERE user_id = ?", (fixed, user_id))
                print(f"[OK] Fixed token for user: {user_id}")
                fixed_count += 1
            except Exception as e:
                print(f"[NG] Failed to fix token for user: {user_id}, error: {e}")

    conn.commit()
    conn.close()
    print(f"修正完了: {fixed_count}件のトークンを修正しました")

if __name__ == "__main__":
    fix_google_tokens(DB_PATH) 