import os
import logging
import psycopg2
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import re

logger = logging.getLogger(__name__)

class RestrictionChecker:
    def __init__(self, content_type: str = "AI経理秘書"):
        self.content_type = content_type
        self.database_url = os.getenv('DATABASE_URL')
    
    def check_user_restriction(self, line_user_id: str, email: str = None) -> Dict[str, Any]:
        """
        ユーザーの利用制限をチェックする（契約期間ベース）
        
        Args:
            line_user_id: LINEユーザーID
            email: メールアドレス（オプション）
            
        Returns:
            Dict containing:
            - is_restricted: bool (制限されているかどうか)
            - reason: str (制限理由)
            - subscription_info: Dict (契約情報)
        """
        if not self.database_url:
            logger.error("DATABASE_URL not set")
            return {
                "is_restricted": False,
                "reason": "database_not_configured",
                "subscription_info": None
            }
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # ユーザーを検索（email優先、次にline_user_id）
                    user = None
                    if email:
                        cursor.execute("""
                            SELECT id, email, line_user_id 
                            FROM users 
                            WHERE LOWER(email) = LOWER(%s)
                        """, (email,))
                        user = cursor.fetchone()
                        if user:
                            logger.info(f"User found by email: {email}")
                    
                    if not user and line_user_id:
                        cursor.execute("""
                            SELECT id, email, line_user_id 
                            FROM users 
                            WHERE line_user_id = %s
                        """, (line_user_id,))
                        user = cursor.fetchone()
                        if user:
                            logger.info(f"User found by line_user_id: {line_user_id}")
                    
                    if not user:
                        logger.info(f"User not found in database: line_user_id={line_user_id}, email={email}")
                        return {
                            "is_restricted": True,
                            "reason": "user_not_found",
                            "subscription_info": None
                        }
                    
                    user_id, user_email, user_line_id = user
                    
                    # アクティブな契約をチェック
                    cursor.execute("""
                        SELECT id, content_type, start_date, end_date, status
                        FROM subscriptions 
                        WHERE user_id = %s 
                        AND content_type = %s 
                        AND status = 'active'
                        AND end_date > CURRENT_TIMESTAMP
                        ORDER BY end_date DESC
                        LIMIT 1
                    """, (user_id, self.content_type))
                    
                    subscription = cursor.fetchone()
                    
                    if subscription:
                        sub_id, sub_content_type, start_date, end_date, status = subscription
                        logger.info(f"Active subscription found for user {user_id}: end_date={end_date}")
                        return {
                            "is_restricted": False,
                            "reason": "active_subscription",
                            "subscription_info": {
                                "id": sub_id,
                                "content_type": sub_content_type,
                                "start_date": start_date,
                                "end_date": end_date,
                                "status": status
                            }
                        }
                    else:
                        # 契約がない場合、usage_logsの最新記録をチェック（後方互換性）
                        cursor.execute("""
                            SELECT MAX(created) as last_usage
                            FROM usage_logs 
                            WHERE user_id = %s 
                            AND content_type = %s
                        """, (user_id, self.content_type))
                        
                        last_usage_result = cursor.fetchone()
                        last_usage = last_usage_result[0] if last_usage_result else None
                        
                        if last_usage:
                            # 最後の使用から30日以内なら一時的に許可（移行期間）
                            days_since_last_usage = (datetime.now(timezone.utc) - last_usage).days
                            if days_since_last_usage <= 30:
                                logger.info(f"User {user_id} has recent usage (within 30 days): {days_since_last_usage} days ago")
                                return {
                                    "is_restricted": False,
                                    "reason": "recent_usage_legacy",
                                    "subscription_info": {
                                        "last_usage": last_usage,
                                        "days_since_last_usage": days_since_last_usage
                                    }
                                }
                        
                        logger.info(f"User {user_id} has no active subscription or recent usage")
                        return {
                            "is_restricted": True,
                            "reason": "no_active_subscription",
                            "subscription_info": None
                        }
                        
        except Exception as e:
            logger.error(f"Database error in check_user_restriction: {e}")
            return {
                "is_restricted": False,  # エラー時は制限しない（安全側）
                "reason": "database_error",
                "subscription_info": None
            }
    
    def get_restriction_message(self) -> Dict[str, Any]:
        """制限メッセージを取得"""
        return {
            "type": "template",
            "alt_text": "AI経理秘書は解約されています。公式LINEで再登録してください。",
            "template": {
                "type": "buttons",
                "text": "AI経理秘書は解約されています。公式LINEで再登録してください。",
                "actions": [
                    {
                        "type": "uri",
                        "label": "AIコレクションズ公式LINE",
                        "uri": "https://lin.ee/eyYpOKq"
                    },
                    {
                        "type": "uri",
                        "label": "サービス詳細",
                        "uri": "https://lp-production-9e2c.up.railway.app/"
                    }
                ]
            }
        }
    
    def _is_valid_email(self, email: str) -> bool:
        """メールアドレスの形式をチェック"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

def safe_check_restriction(line_user_id: str, email: str = None, content_type: str = "AI経理秘書") -> Dict[str, Any]:
    """
    制限チェックの安全なラッパー関数
    
    Args:
        line_user_id: LINEユーザーID
        email: メールアドレス（オプション）
        content_type: コンテンツタイプ
        
    Returns:
        Dict containing restriction check result
    """
    try:
        checker = RestrictionChecker(content_type)
        return checker.check_user_restriction(line_user_id, email)
    except Exception as e:
        logger.error(f"Error in safe_check_restriction: {e}")
        return {
            "is_restricted": False,  # エラー時は制限しない（安全側）
            "reason": "error",
            "subscription_info": None
        }

# 契約管理用のユーティリティ関数
def create_subscription(user_id: int, content_type: str, duration_days: int = 30) -> bool:
    """
    新しい契約を作成する
    
    Args:
        user_id: ユーザーID
        content_type: コンテンツタイプ
        duration_days: 契約期間（日数）
        
    Returns:
        bool: 作成成功時True
    """
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False
    
    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cursor:
                # 既存のアクティブな契約を無効化
                cursor.execute("""
                    UPDATE subscriptions 
                    SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND content_type = %s AND status = 'active'
                """, (user_id, content_type))
                
                # 新しい契約を作成
                cursor.execute("""
                    INSERT INTO subscriptions (user_id, content_type, start_date, end_date, status)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '%s days', 'active')
                """, (user_id, content_type, duration_days))
                
                conn.commit()
                logger.info(f"Subscription created for user {user_id}, content_type {content_type}, duration {duration_days} days")
                return True
                
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        return False

def extend_subscription(subscription_id: int, additional_days: int) -> bool:
    """
    既存の契約を延長する
    
    Args:
        subscription_id: 契約ID
        additional_days: 延長日数
        
    Returns:
        bool: 延長成功時True
    """
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False
    
    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE subscriptions 
                    SET end_date = end_date + INTERVAL '%s days', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND status = 'active'
                """, (additional_days, subscription_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Subscription {subscription_id} extended by {additional_days} days")
                    return True
                else:
                    logger.warning(f"Subscription {subscription_id} not found or not active")
                    return False
                    
    except Exception as e:
        logger.error(f"Error extending subscription: {e}")
        return False

def cancel_subscription(subscription_id: int) -> bool:
    """
    契約をキャンセルする
    
    Args:
        subscription_id: 契約ID
        
    Returns:
        bool: キャンセル成功時True
    """
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False
    
    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE subscriptions 
                    SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND status = 'active'
                """, (subscription_id,))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Subscription {subscription_id} cancelled")
                    return True
                else:
                    logger.warning(f"Subscription {subscription_id} not found or not active")
                    return False
                    
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        return False

def get_user_subscriptions(user_id: int) -> list:
    """
    ユーザーの契約一覧を取得する
    
    Args:
        user_id: ユーザーID
        
    Returns:
        list: 契約情報のリスト
    """
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not set")
        return []
    
    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, content_type, start_date, end_date, status, created_at, updated_at
                    FROM subscriptions 
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                
                subscriptions = []
                for row in cursor.fetchall():
                    subscriptions.append({
                        "id": row[0],
                        "content_type": row[1],
                        "start_date": row[2],
                        "end_date": row[3],
                        "status": row[4],
                        "created_at": row[5],
                        "updated_at": row[6]
                    })
                
                return subscriptions
                
    except Exception as e:
        logger.error(f"Error getting user subscriptions: {e}")
        return [] 