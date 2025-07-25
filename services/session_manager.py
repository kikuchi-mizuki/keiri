import json
import sqlite3
import os
from datetime import datetime, timedelta
import logging
import traceback

logger = logging.getLogger(__name__)

class SessionManager:
    """ユーザーセッション管理クラス"""
    
    def __init__(self):
        db_url = os.getenv('DATABASE_URL', 'sqlite:///sessions.db')
        # SQLiteファイルパスを抽出
        if db_url.startswith('sqlite:///'):
            db_path = db_url.replace('sqlite:///', '')
        else:
            db_path = 'sessions.db'
        abs_db_path = os.path.abspath(db_path)
        print(f"[DEBUG] SessionManager: DBファイル絶対パス={abs_db_path}")
        self.db_path = abs_db_path
        self._init_db()
    
    def _init_db(self):
        """データベースの初期化"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            # セッションテーブルの作成
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id TEXT PRIMARY KEY,
                    session_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ユーザー情報テーブルの作成
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    company_name TEXT,
                    address TEXT,
                    bank_account TEXT,
                    google_refresh_token TEXT,
                    spreadsheet_id TEXT,
                    estimate_spreadsheet_id TEXT,
                    invoice_spreadsheet_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 既存テーブルに新しいカラムを追加（存在しない場合のみ）
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN estimate_spreadsheet_id TEXT')
                logger.info("Added estimate_spreadsheet_id column to users table")
            except sqlite3.OperationalError:
                # カラムが既に存在する場合は無視
                pass
            
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN invoice_spreadsheet_id TEXT')
                logger.info("Added invoice_spreadsheet_id column to users table")
            except sqlite3.OperationalError:
                # カラムが既に存在する場合は無視
                pass
            
            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    def create_session(self, user_id, session_data):
        """新しいセッションを作成"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            # 既存のセッションがあれば更新、なければ新規作成
            cursor.execute('''
                INSERT OR REPLACE INTO sessions (user_id, session_data, updated_at)
                VALUES (?, ?, ?)
            ''', (user_id, json.dumps(session_data), datetime.now()))
            
            conn.commit()
            conn.close()
            logger.info(f"Session created/updated for user: {user_id}")
            
        except Exception as e:
            logger.error(f"Session creation error: {e}")
    
    def get_session(self, user_id):
        """セッション情報を取得"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT session_data FROM sessions 
                WHERE user_id = ? AND updated_at > ?
            ''', (user_id, datetime.now() - timedelta(hours=24)))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                session_data = json.loads(result[0])
                logger.info(f"Session retrieved for user: {user_id}")
                return session_data
            else:
                logger.info(f"No active session found for user: {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Session retrieval error: {e}")
            return None
    
    def update_session(self, user_id, updates):
        """セッション情報を更新"""
        try:
            current_session = self.get_session(user_id) or {}
            updated_session = {**current_session, **updates}
            
            self.create_session(user_id, updated_session)
            logger.info(f"Session updated for user: {user_id}")
            
        except Exception as e:
            logger.error(f"Session update error: {e}")
    
    def delete_session(self, user_id):
        """セッションを削除"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            logger.info(f"Session deleted for user: {user_id}")
            
        except Exception as e:
            logger.error(f"Session deletion error: {e}")
    
    def save_user_info(self, user_id, user_info):
        """ユーザー情報を永続化"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()

            # 既存ユーザーのgoogle_refresh_tokenを取得
            cursor.execute('SELECT google_refresh_token FROM users WHERE user_id = ?', (user_id,))
            existing_token = cursor.fetchone()
            if existing_token:
                google_refresh_token = existing_token[0]
            else:
                google_refresh_token = None

            # INSERT OR REPLACEだとトークンが消えるので、REPLACEではなくUPDATE/INSERTを分岐
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            user_exists = cursor.fetchone()
            if user_exists:
                # UPDATE時はトークンを保持
                cursor.execute('''
                    UPDATE users SET company_name = ?, address = ?, bank_account = ?, updated_at = ?
                    WHERE user_id = ?
                ''', (
                    user_info.get('company_name'),
                    user_info.get('address'),
                    user_info.get('bank_account'),
                    datetime.now(),
                    user_id
                ))
            else:
                # INSERT時はトークンはNoneでOK
                cursor.execute('''
                    INSERT INTO users (user_id, company_name, address, bank_account, google_refresh_token, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    user_info.get('company_name'),
                    user_info.get('address'),
                    user_info.get('bank_account'),
                    google_refresh_token,
                    datetime.now(),
                    datetime.now()
                ))

            conn.commit()
            conn.close()
            logger.info(f"User info saved for user: {user_id}")
        except Exception as e:
            logger.error(f"User info save error: {e}")
    
    def get_user_info(self, user_id):
        """ユーザー情報を取得"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT company_name, address, bank_account 
                FROM users WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'company_name': result[0],
                    'address': result[1],
                    'bank_account': result[2]
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"User info retrieval error: {e}")
            return None
    
    def save_google_token(self, user_id, refresh_token):
        """Google認証トークンを保存"""
        try:
            print(f"[DEBUG] save_google_token: user_id={user_id}, refresh_token={refresh_token}")
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            # まずユーザーが存在するかチェック
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            user_exists = cursor.fetchone()
            print(f"[DEBUG] save_google_token: user_exists={user_exists}")
            
            if user_exists:
                # 既存ユーザーの場合、UPDATE
                cursor.execute('''
                    UPDATE users SET google_refresh_token = ?, updated_at = ?
                    WHERE user_id = ?
                ''', (refresh_token, datetime.now(), user_id))
            else:
                # 新規ユーザーの場合、INSERT（他のフィールドはNULLで初期化）
                cursor.execute('''
                    INSERT INTO users (user_id, company_name, address, bank_account, google_refresh_token, created_at, updated_at)
                    VALUES (?, NULL, NULL, NULL, ?, ?, ?)
                ''', (user_id, refresh_token, datetime.now(), datetime.now()))
            
            conn.commit()
            conn.close()
            logger.info(f"Google token saved for user: {user_id}")
            
        except Exception as e:
            print(f"[ERROR] save_google_token: {e}")
            traceback.print_exc()
            logger.error(f"Google token save error: {e}")
    
    def get_google_token(self, user_id):
        """Google認証トークンを取得"""
        try:
            print(f"[DEBUG] get_google_token: user_id={user_id}")
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            # 全カラム取得に変更
            cursor.execute('''
                SELECT * FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            print(f"[DEBUG] get_google_token: 全カラムresult={result}")
            conn.close()
            # 旧来の動作も維持
            if result and len(result) >= 5:
                google_refresh_token = result[4]
                print(f"[DEBUG] get_google_token: google_refresh_token={google_refresh_token}")
                return google_refresh_token
            else:
                print(f"[DEBUG] get_google_token: トークンカラムが見つかりません")
                return None
        except Exception as e:
            print(f"[ERROR] get_google_token: {e}")
            traceback.print_exc()
            logger.error(f"Google token retrieval error: {e}")
            return None 

    def save_spreadsheet_id(self, user_id, spreadsheet_id):
        """ユーザーごとのスプレッドシートIDを保存"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET spreadsheet_id = ?, updated_at = ? WHERE user_id = ?
            ''', (spreadsheet_id, datetime.now(), user_id))
            conn.commit()
            conn.close()
            logger.info(f"Spreadsheet ID saved for user: {user_id}")
        except Exception as e:
            logger.error(f"Spreadsheet ID save error: {e}")

    def get_spreadsheet_id(self, user_id):
        """ユーザーごとのスプレッドシートIDを取得"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT spreadsheet_id FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                return result[0]
            else:
                return None
        except Exception as e:
            logger.error(f"Spreadsheet ID retrieval error: {e}")
            return None

    def save_estimate_spreadsheet_id(self, user_id, spreadsheet_id):
        """見積書用スプレッドシートIDを保存"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET estimate_spreadsheet_id = ?, updated_at = ? WHERE user_id = ?
            ''', (spreadsheet_id, datetime.now(), user_id))
            conn.commit()
            conn.close()
            logger.info(f"Estimate spreadsheet ID saved for user: {user_id}")
        except Exception as e:
            logger.error(f"Estimate spreadsheet ID save error: {e}")

    def get_estimate_spreadsheet_id(self, user_id):
        """見積書用スプレッドシートIDを取得"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT estimate_spreadsheet_id FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                return result[0]
            else:
                return None
        except Exception as e:
            logger.error(f"Estimate spreadsheet ID retrieval error: {e}")
            return None

    def save_invoice_spreadsheet_id(self, user_id, spreadsheet_id):
        """請求書用スプレッドシートIDを保存"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET invoice_spreadsheet_id = ?, updated_at = ? WHERE user_id = ?
            ''', (spreadsheet_id, datetime.now(), user_id))
            conn.commit()
            conn.close()
            logger.info(f"Invoice spreadsheet ID saved for user: {user_id}")
        except Exception as e:
            logger.error(f"Invoice spreadsheet ID save error: {e}")

    def get_invoice_spreadsheet_id(self, user_id):
        """請求書用スプレッドシートIDを取得"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT invoice_spreadsheet_id FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                return result[0]
            else:
                return None
        except Exception as e:
            logger.error(f"Invoice spreadsheet ID retrieval error: {e}")
            return None 