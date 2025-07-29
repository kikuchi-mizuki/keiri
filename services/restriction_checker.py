import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, Dict, Any
import re

logger = logging.getLogger(__name__)

class RestrictionChecker:
    """解約制限チェック機能を提供するクラス（usage_logsベース）"""
    
    def __init__(self, content_type: str = "AI経理秘書"):
        self.content_type = content_type
        self.database_url = os.getenv('DATABASE_URL')
        
    def check_user_restriction(self, line_user_id: str, email: str = None) -> Dict[str, Any]:
        """
        ユーザーの利用制限をチェックする（usage_logsベース）
        
        Args:
            line_user_id: LINEユーザーID
            email: メールアドレス（オプション）
            
        Returns:
            Dict containing:
                - is_restricted: bool (制限されているかどうか)
                - error: str (エラーメッセージ、エラーがある場合)
                - user_id: int (データベースのユーザーID、見つかった場合)
                - check_method: str (チェック方法: 'email' or 'line_user_id')
                - usage_found: bool (usage_logsに記録があるかどうか)
        """
        try:
            if not self.database_url:
                logger.warning("DATABASE_URL not set, skipping restriction check")
                return {
                    "is_restricted": False, 
                    "error": None, 
                    "user_id": None, 
                    "check_method": None,
                    "usage_found": False
                }
            
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    user_id = None
                    check_method = None
                    
                    # メールアドレスでの検索（優先）
                    if email and self._is_valid_email(email):
                        cur.execute("""
                            SELECT id FROM users 
                            WHERE email = %s
                        """, (email.lower(),))
                        
                        user_result = cur.fetchone()
                        if user_result:
                            user_id = user_result['id']
                            check_method = 'email'
                            logger.info(f"User found by email: {email}")
                    
                    # メールアドレスで見つからない場合はLINEユーザーIDで検索
                    if not user_id:
                        cur.execute("""
                            SELECT id FROM users 
                            WHERE line_user_id = %s
                        """, (line_user_id,))
                        
                        user_result = cur.fetchone()
                        if user_result:
                            user_id = user_result['id']
                            check_method = 'line_user_id'
                            logger.info(f"User found by line_user_id: {line_user_id}")
                    
                    if not user_id:
                        logger.info(f"User not found in database: line_user_id={line_user_id}, email={email}")
                        return {
                            "is_restricted": False, 
                            "error": None, 
                            "user_id": None, 
                            "check_method": None,
                            "usage_found": False
                        }
                    
                    # usage_logsテーブルで利用履歴をチェック
                    cur.execute("""
                        SELECT COUNT(*) as count 
                        FROM usage_logs 
                        WHERE user_id = %s AND content_type = %s
                    """, (user_id, self.content_type))
                    
                    result = cur.fetchone()
                    usage_found = result['count'] > 0
                    
                    # usage_logsに記録がない場合は制限
                    is_restricted = not usage_found
                    
                    logger.info(f"Usage check for user {user_id} (method: {check_method}): usage_found={usage_found}, is_restricted={is_restricted}")
                    
                    return {
                        "is_restricted": is_restricted,
                        "error": None,
                        "user_id": user_id,
                        "check_method": check_method,
                        "usage_found": usage_found
                    }
                    
        except psycopg2.Error as e:
            logger.error(f"Database error during restriction check: {e}")
            return {
                "is_restricted": False,
                "error": f"Database connection error: {str(e)}",
                "user_id": None,
                "check_method": None,
                "usage_found": False
            }
        except Exception as e:
            logger.error(f"Unexpected error during restriction check: {e}")
            return {
                "is_restricted": False,
                "error": f"Unexpected error: {str(e)}",
                "user_id": None,
                "check_method": None,
                "usage_found": False
            }
    
    def _is_valid_email(self, email: str) -> bool:
        """メールアドレスの形式をチェック"""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def get_restriction_message(self) -> Dict[str, Any]:
        """
        制限メッセージを生成する
        
        Returns:
            LINE Button Template用のメッセージデータ
        """
        return {
            "type": "template",
            "altText": "AI経理秘書の利用制限",
            "template": {
                "type": "buttons",
                "title": "AI経理秘書の利用制限",
                "text": "AI経理秘書は解約されているため、公式LINEを利用できません。AIコレクションズの公式LINEで再度ご登録いただき、サービスをご利用ください。",
                "actions": [
                    {
                        "type": "uri",
                        "label": "AIコレクションズ公式LINE",
                        "uri": "https://line.me/R/ti/p/@ai_collections"
                    },
                    {
                        "type": "uri",
                        "label": "サービス詳細",
                        "uri": "https://ai-collections.herokuapp.com"
                    }
                ]
            }
        }

def safe_check_restriction(line_user_id: str, email: str = None, content_type: str = "AI経理秘書") -> Dict[str, Any]:
    """
    安全な制限チェックを実行する（エラーハンドリング付き）
    
    Args:
        line_user_id: LINEユーザーID
        email: メールアドレス（オプション）
        content_type: コンテンツタイプ
        
    Returns:
        制限チェック結果
    """
    try:
        checker = RestrictionChecker(content_type)
        return checker.check_user_restriction(line_user_id, email)
    except Exception as e:
        logger.error(f"Error in safe_check_restriction: {e}")
        return {
            "is_restricted": False,
            "error": f"Check failed: {str(e)}",
            "user_id": None,
            "check_method": None,
            "usage_found": False
        } 