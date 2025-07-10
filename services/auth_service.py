import os
import json
import logging
import traceback
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from flask import url_for, request

logger = logging.getLogger(__name__)

class AuthService:
    """Google OAuth認証管理クラス"""
    
    def __init__(self):
        # 絶対パスでclient_secrets.jsonファイルを指定
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_client_secrets = os.path.join(base_dir, 'client_secrets.json')
        self.client_secrets_file = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', default_client_secrets)
        
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/calendar'
        ]
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/callback')
        
        # 認証フローの設定
        self.flow = Flow.from_client_secrets_file(
            self.client_secrets_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
    
    def get_auth_url(self, user_id):
        """認証URLを生成"""
        try:
            # 絶対パスでclient_secrets.jsonファイルを指定
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_client_secrets = os.path.join(base_dir, 'client_secrets.json')
            client_secrets_file = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', default_client_secrets)
            
            flow = Flow.from_client_secrets_file(
                client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent',
                state=user_id  # stateパラメータとしてuser_idを渡す
            )
            print(f"[DEBUG] get_auth_url: auth_url={auth_url}")
            logger.info(f"Auth URL generated for user: {user_id}")
            return auth_url
        except Exception as e:
            print(f"[DEBUG] get_auth_url: error={e}")
            logger.error(f"Auth URL generation error: {e}")
            return None
    
    def handle_callback(self, code, state):
        """認証コールバックの処理"""
        try:
            print(f"[DEBUG] handle_callback: code={code[:20] if code else 'None'}, state={state}")
            # コールバック時も新しいFlowインスタンスを作成し、stateを復元
            # 絶対パスでclient_secrets.jsonファイルを指定
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_client_secrets = os.path.join(base_dir, 'client_secrets.json')
            client_secrets_file = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', default_client_secrets)
            
            flow = Flow.from_client_secrets_file(
                client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            flow.fetch_token(code=code)
            credentials = flow.credentials
            print(f"[DEBUG] handle_callback: credentials.refresh_token={credentials.refresh_token}")

            # refresh_tokenが取得できていなければエラー
            if not credentials.refresh_token:
                raise Exception("Google認証でrefresh_tokenが取得できませんでした。アカウント設定で再認証を許可してください。")

            # ユーザーIDをstateから取得
            user_id = state

            # トークン情報を保存
            token_info = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': 'https://oauth2.googleapis.com/token',  # 固定値
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            print(f"[DEBUG] handle_callback: token_info={token_info}")

            # セッション管理に保存
            from .session_manager import SessionManager
            session_manager = SessionManager()
            session_manager.save_google_token(user_id, json.dumps(token_info))

            # 保存直後に再取得してprintデバッグ
            saved_token = session_manager.get_google_token(user_id)
            print(f"[DEBUG] handle_callback: save直後 get_google_token({user_id})={saved_token}")

            logger.info(f"Authentication completed for user: {user_id}")
            return True

        except Exception as e:
            print(f"[ERROR] handle_callback: {e}")
            traceback.print_exc()
            logger.error(f"Auth callback error: {e}")
            return False
    
    def get_credentials(self, user_id):
        """ユーザーの認証情報を取得"""
        try:
            from .session_manager import SessionManager
            session_manager = SessionManager()

            token_json = session_manager.get_google_token(user_id)
            print(f"[DEBUG] get_credentials: token_json={token_json}")
            if not token_json:
                logger.error(f"No google token found for user: {user_id}")
                return None

            token_info = json.loads(token_json)

            credentials = Credentials(
                token=token_info['token'],
                refresh_token=token_info['refresh_token'],
                token_uri=token_info['token_uri'],
                client_id=token_info['client_id'],
                client_secret=token_info['client_secret'],
                scopes=token_info['scopes']
            )
            print(f"[DEBUG] get_credentials: credentials.refresh_token={credentials.refresh_token}")

            # refresh_tokenがNoneの場合はエラー
            if not credentials.refresh_token:
                logger.error(f"refresh_token is None for user: {user_id}")
                return None

            # トークンの有効期限をチェック
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())

                    # 更新されたトークンを保存
                    updated_token_info = {
                        'token': credentials.token,
                        'refresh_token': credentials.refresh_token,
                        'token_uri': credentials.token_uri,
                        'client_id': credentials.client_id,
                        'client_secret': credentials.client_secret,
                        'scopes': credentials.scopes
                    }
                    session_manager.save_google_token(user_id, json.dumps(updated_token_info))

                except RefreshError:
                    print(f"[ERROR] get_credentials: RefreshError for user: {user_id}")
                    logger.error(f"Token refresh failed for user: {user_id}")
                    return None

            return credentials

        except Exception as e:
            print(f"[ERROR] get_credentials: {e}")
            traceback.print_exc()
            logger.error(f"Credentials retrieval error: {e}")
            return None
    
    def is_authenticated(self, user_id):
        """ユーザーが認証済みかチェック"""
        try:
            credentials = self.get_credentials(user_id)
            return credentials is not None
            
        except Exception as e:
            logger.error(f"Authentication check error: {e}")
            return False
    
    def revoke_access(self, user_id):
        """アクセス権限を削除"""
        try:
            credentials = self.get_credentials(user_id)
            if credentials:
                # revokeメソッドの代わりにトークンを削除
                pass
            
            # トークンを削除
            from .session_manager import SessionManager
            session_manager = SessionManager()
            session_manager.save_google_token(user_id, None)
            
            logger.info(f"Access revoked for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Access revocation error: {e}")
            return False 