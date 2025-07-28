import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class RestrictionChecker:
    """解約制限チェック機能を提供するクラス"""
    
    def __init__(self, content_type: str = "AI経理秘書"):
        self.content_type = content_type
        self.database_url = os.getenv('DATABASE_URL')
        
    def check_user_restriction(self, line_user_id: str) -> Dict[str, Any]:
        """
        ユーザーの利用制限をチェックする
        
        Args:
            line_user_id: LINEユーザーID
            
        Returns:
            Dict containing:
                - is_restricted: bool (制限されているかどうか)
                - error: str (エラーメッセージ、エラーがある場合)
                - user_id: int (データベースのユーザーID、見つかった場合)
        """
        try:
            if not self.database_url:
                logger.warning("DATABASE_URL not set, skipping restriction check")
                return {"is_restricted": False, "error": None, "user_id": None}
            
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # ユーザーIDを取得
                    cur.execute("""
                        SELECT id FROM users 
                        WHERE line_user_id = %s
                    """, (line_user_id,))
                    
                    user_result = cur.fetchone()
                    if not user_result:
                        logger.info(f"User not found in database: {line_user_id}")
                        return {"is_restricted": False, "error": None, "user_id": None}
                    
                    user_id = user_result['id']
                    
                    # 解約履歴をチェック
                    cur.execute("""
                        SELECT COUNT(*) as count 
                        FROM cancellation_history 
                        WHERE user_id = %s AND content_type = %s
                    """, (user_id, self.content_type))
                    
                    result = cur.fetchone()
                    is_restricted = result['count'] > 0
                    
                    logger.info(f"Restriction check for user {line_user_id}: {is_restricted}")
                    
                    return {
                        "is_restricted": is_restricted,
                        "error": None,
                        "user_id": user_id
                    }
                    
        except psycopg2.Error as e:
            logger.error(f"Database error during restriction check: {e}")
            return {
                "is_restricted": False,
                "error": f"Database connection error: {str(e)}",
                "user_id": None
            }
        except Exception as e:
            logger.error(f"Unexpected error during restriction check: {e}")
            return {
                "is_restricted": False,
                "error": f"Unexpected error: {str(e)}",
                "user_id": None
            }
    
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

def safe_check_restriction(line_user_id: str, content_type: str = "AI経理秘書") -> Dict[str, Any]:
    """
    安全な制限チェックを実行する（エラーハンドリング付き）
    
    Args:
        line_user_id: LINEユーザーID
        content_type: コンテンツタイプ
        
    Returns:
        制限チェック結果
    """
    try:
        checker = RestrictionChecker(content_type)
        return checker.check_user_restriction(line_user_id)
    except Exception as e:
        logger.error(f"Error in safe_check_restriction: {e}")
        return {
            "is_restricted": False,
            "error": f"Check failed: {str(e)}",
            "user_id": None
        } 