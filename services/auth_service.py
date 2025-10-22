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
        # 環境変数のデバッグ
        print(f"[DEBUG] GOOGLE_CLIENT_SECRETS_JSON exists: {os.getenv('GOOGLE_CLIENT_SECRETS_JSON') is not None}")
        print(f"[DEBUG] GOOGLE_CLIENT_SECRETS_FILE: {os.getenv('GOOGLE_CLIENT_SECRETS_FILE')}")
        print(f"[DEBUG] GOOGLE_CLIENT_SECRETS_JSON value: {os.getenv('GOOGLE_CLIENT_SECRETS_JSON')[:100] if os.getenv('GOOGLE_CLIENT_SECRETS_JSON') else 'None'}...")
        print(f"[DEBUG] All environment variables: {[k for k, v in os.environ.items() if 'GOOGLE' in k or 'SERVER' in k]}")
        
        # 環境変数からJSON文字列を取得してファイルとして保存
        client_secrets_env = os.getenv('GOOGLE_CLIENT_SECRETS_JSON')
        
        # 環境変数が設定されていない場合は警告を表示（エラーにはしない）
        if not client_secrets_env:
            print("[WARNING] GOOGLE_CLIENT_SECRETS_JSON environment variable is not set")
            print("[WARNING] Google OAuth features will be disabled")
            self.google_oauth_enabled = False
            # 早期リターンを削除し、後続の処理を実行
        else:
            self.google_oauth_enabled = True
        
        # client_secrets_envが設定されている場合のみファイル作成処理を実行
        if client_secrets_env:
            try:
                # 絶対パスでclient_secrets.jsonファイルを指定
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                client_secrets_path = os.path.join(base_dir, 'client_secrets.json')
                
                # JSON文字列をファイルとして保存
                with open(client_secrets_path, 'w') as f:
                    f.write(client_secrets_env)
                print(f"[DEBUG] client_secrets.json created at {client_secrets_path}")
                
                self.client_secrets_file = client_secrets_path
            except Exception as e:
                print(f"[ERROR] Failed to create client_secrets.json: {e}")
                # フォールバック: デフォルトパスを使用
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                default_client_secrets = os.path.join(base_dir, 'client_secrets.json')
                self.client_secrets_file = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', default_client_secrets)
        else:
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
        # リダイレクトURIの設定（新しいプロジェクトのURLに合わせる）
        default_redirect_uri = os.getenv('SERVER_URL', 'http://localhost:5000') + '/auth/callback'
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', default_redirect_uri)
        print(f"[DEBUG] Google OAuth redirect_uri: {self.redirect_uri}")
        
        # client_secrets_envが設定されている場合のみファイルチェックとフロー設定を実行
        if client_secrets_env:
            # ファイルの存在確認と内容チェック
            print(f"[DEBUG] client_secrets_file path: {self.client_secrets_file}")
            if os.path.exists(self.client_secrets_file):
                try:
                    with open(self.client_secrets_file, 'r') as f:
                        content = f.read()
                        print(f"[DEBUG] client_secrets.json content length: {len(content)}")
                        if len(content.strip()) == 0:
                            raise Exception("client_secrets.json is empty")
                        # JSONとして解析できるかテスト
                        json.loads(content)
                        print("[DEBUG] client_secrets.json is valid JSON")
                except Exception as e:
                    print(f"[ERROR] client_secrets.json validation failed: {e}")
                    raise
            else:
                print(f"[ERROR] client_secrets.json file not found at: {self.client_secrets_file}")
                raise FileNotFoundError(f"client_secrets.json not found at {self.client_secrets_file}")
            
            # 認証フローの設定
            self.flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
        else:
            # Google OAuthが無効な場合の処理
            print("[DEBUG] Google OAuth is disabled - skipping flow setup")
            self.flow = None
    
    def get_auth_url(self, user_id):
        """認証URLを生成"""
        if not hasattr(self, 'google_oauth_enabled') or not self.google_oauth_enabled:
            print("[DEBUG] Google OAuth is disabled")
            return None
        try:
            print(f"[DEBUG] get_auth_url: user_id={user_id}")
            print(f"[DEBUG] get_auth_url: redirect_uri={self.redirect_uri}")
            # 環境変数からJSON文字列を取得してファイルとして保存
            client_secrets_env = os.getenv('GOOGLE_CLIENT_SECRETS_JSON')
            if client_secrets_env:
                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    client_secrets_path = os.path.join(base_dir, 'client_secrets.json')
                    
                    with open(client_secrets_path, 'w') as f:
                        f.write(client_secrets_env)
                    
                    client_secrets_file = client_secrets_path
                except Exception as e:
                    print(f"[ERROR] Failed to create client_secrets.json: {e}")
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    default_client_secrets = os.path.join(base_dir, 'client_secrets.json')
                    client_secrets_file = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', default_client_secrets)
            else:
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
            print(f"[DEBUG] get_auth_url: access_type=offline, prompt=consent")
            print(f"[DEBUG] get_auth_url: auth_url={auth_url}")
            logger.info(f"Auth URL generated for user: {user_id}")
            return auth_url
        except Exception as e:
            print(f"[DEBUG] get_auth_url: error={e}")
            logger.error(f"Auth URL generation error: {e}")
            return None
    
    def handle_callback(self, code, state):
        """認証コールバックの処理"""
        if not hasattr(self, 'google_oauth_enabled') or not self.google_oauth_enabled:
            return False
        try:
            print(f"[DEBUG] handle_callback: code={code[:20] if code else 'None'}, state={state}")
            # コールバック時も新しいFlowインスタンスを作成し、stateを復元
            # 環境変数からJSON文字列を取得してファイルとして保存
            client_secrets_env = os.getenv('GOOGLE_CLIENT_SECRETS_JSON')
            if client_secrets_env:
                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    client_secrets_path = os.path.join(base_dir, 'client_secrets.json')
                    
                    with open(client_secrets_path, 'w') as f:
                        f.write(client_secrets_env)
                    
                    client_secrets_file = client_secrets_path
                except Exception as e:
                    print(f"[ERROR] Failed to create client_secrets.json: {e}")
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    default_client_secrets = os.path.join(base_dir, 'client_secrets.json')
                    client_secrets_file = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', default_client_secrets)
            else:
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
            print(f"[DEBUG] handle_callback: refresh_token length={len(credentials.refresh_token) if credentials.refresh_token else 0}")

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
            print(f"[DEBUG] get_credentials: credentials.expired={credentials.expired}, refresh_token exists={credentials.refresh_token is not None}")
            print(f"[DEBUG] get_credentials: token expiry info - valid={credentials.valid}, expired={credentials.expired}")
            if credentials.expired and credentials.refresh_token:
                try:
                    print(f"[DEBUG] get_credentials: トークン更新開始 user_id={user_id}")
                    credentials.refresh(Request())
                    print(f"[DEBUG] get_credentials: トークン更新成功 user_id={user_id}")

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
                    print(f"[DEBUG] get_credentials: 更新されたトークンを保存完了 user_id={user_id}")

                except RefreshError as e:
                    print(f"[ERROR] get_credentials: RefreshError for user: {user_id}, error: {e}")
                    print(f"[ERROR] get_credentials: RefreshError details - error_type={type(e).__name__}, error_message={str(e)}")
                    logger.error(f"Token refresh failed for user: {user_id}, error: {e}")
                    # トークンが無効になった場合は削除
                    session_manager.save_google_token(user_id, None)
                    print(f"[DEBUG] get_credentials: 無効なトークンを削除 user_id={user_id}")
                    return None
                except Exception as e:
                    print(f"[ERROR] get_credentials: トークン更新で予期しないエラー user_id={user_id}, error: {e}")
                    logger.error(f"Unexpected error during token refresh for user: {user_id}, error: {e}")
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
    
    def check_token_status(self, user_id):
        """トークンの状態を詳細にチェック"""
        try:
            from .session_manager import SessionManager
            session_manager = SessionManager()
            
            token_json = session_manager.get_google_token(user_id)
            if not token_json:
                return {"status": "no_token", "message": "トークンが保存されていません"}
            
            token_info = json.loads(token_json)
            credentials = Credentials(
                token=token_info['token'],
                refresh_token=token_info['refresh_token'],
                token_uri=token_info['token_uri'],
                client_id=token_info['client_id'],
                client_secret=token_info['client_secret'],
                scopes=token_info['scopes']
            )
            
            return {
                "status": "valid" if credentials.valid else "expired",
                "expired": credentials.expired,
                "valid": credentials.valid,
                "has_refresh_token": credentials.refresh_token is not None,
                "token_length": len(credentials.token) if credentials.token else 0,
                "refresh_token_length": len(credentials.refresh_token) if credentials.refresh_token else 0
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
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