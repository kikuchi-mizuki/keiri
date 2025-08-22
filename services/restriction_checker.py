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
                    
                    # 新しい判定ロジック: subscription_periodsテーブルでサブスクリプション状態をチェック
                    cursor.execute("""
                        SELECT subscription_status, current_period_end, stripe_subscription_id
                        FROM subscription_periods 
                        WHERE user_id = %s AND stripe_subscription_id IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (user_id,))
                    
                    subscription_period = cursor.fetchone()
                    
                    if subscription_period:
                        subscription_status, current_period_end, stripe_subscription_id = subscription_period
                        
                        # 解約制限の判定基準
                        restricted_statuses = ['canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'past_due']
                        active_statuses = ['active', 'trialing']
                        
                        if subscription_status in restricted_statuses:
                            logger.info(f"User {user_id} has restricted subscription status: {subscription_status}")
                            return {
                                "is_restricted": True,
                                "reason": f"subscription_{subscription_status}",
                                "subscription_info": {
                                    "subscription_status": subscription_status,
                                    "current_period_end": current_period_end,
                                    "stripe_subscription_id": stripe_subscription_id
                                }
                            }
                        elif subscription_status in active_statuses:
                            # アクティブな状態でも、期間終了をチェック
                            if current_period_end:
                                # タイムゾーンを統一して比較
                                if current_period_end.tzinfo is None:
                                    # タイムゾーン情報がない場合はUTCとして扱う
                                    current_period_end_utc = current_period_end.replace(tzinfo=timezone.utc)
                                else:
                                    current_period_end_utc = current_period_end
                                
                                if datetime.now(timezone.utc) > current_period_end_utc:
                                    logger.info(f"User {user_id} subscription period has expired: {current_period_end}")
                                    return {
                                        "is_restricted": True,
                                        "reason": "subscription_period_expired",
                                        "subscription_info": {
                                            "subscription_status": subscription_status,
                                            "current_period_end": current_period_end,
                                            "stripe_subscription_id": stripe_subscription_id
                                        }
                                    }
                            
                            logger.info(f"User {user_id} has active subscription: {subscription_status}")
                            return {
                                "is_restricted": False,
                                "reason": "active_subscription",
                                "subscription_info": {
                                    "subscription_status": subscription_status,
                                    "current_period_end": current_period_end,
                                    "stripe_subscription_id": stripe_subscription_id
                                }
                            }
                        else:
                            # 不明なステータスの場合は制限
                            logger.info(f"User {user_id} has unknown subscription status: {subscription_status}")
                            return {
                                "is_restricted": True,
                                "reason": "unknown_subscription_status",
                                "subscription_info": {
                                    "subscription_status": subscription_status,
                                    "current_period_end": current_period_end,
                                    "stripe_subscription_id": stripe_subscription_id
                                }
                            }
                    else:
                        # subscription_periodsにレコードが存在しない場合は制限
                        logger.info(f"User {user_id} has no subscription_periods record")
                        return {
                            "is_restricted": True,
                            "reason": "no_subscription_period",
                            "subscription_info": None
                        }
                        
        except Exception as e:
            logger.error(f"Error checking user restriction: {e}")
            return {
                "is_restricted": True,
                "reason": "database_error",
                "subscription_info": None
            }
    
    def check_subscription_status_by_line_user_id(self, line_user_id: str) -> Dict[str, Any]:
        """
        LINEユーザーIDからサブスクリプション状態をチェックする（新しい判定ロジック）
        
        Args:
            line_user_id: LINEユーザーID
            
        Returns:
            Dict containing:
            - is_available: bool (利用可能かどうか)
            - reason: str (判定理由)
            - subscription_info: Dict (サブスクリプション情報)
        """
        if not self.database_url:
            logger.error("DATABASE_URL not set")
            return {
                "is_available": False,
                "reason": "database_not_configured",
                "subscription_info": None
            }
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # 1. ユーザーIDを取得
                    cursor.execute("""
                        SELECT id FROM users WHERE line_user_id = %s
                    """, (line_user_id,))
                    
                    user_result = cursor.fetchone()
                    if not user_result:
                        logger.info(f"User not found for line_user_id: {line_user_id}")
                        return {
                            "is_available": False,
                            "reason": "user_not_found",
                            "subscription_info": None
                        }
                    
                    user_id = user_result[0]
                    
                    # 2. subscription_periodsテーブルでサブスクリプション状態をチェック
                    cursor.execute("""
                        SELECT subscription_status, current_period_end, stripe_subscription_id
                        FROM subscription_periods 
                        WHERE user_id = %s AND stripe_subscription_id IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (user_id,))
                    
                    subscription_result = cursor.fetchone()
                    
                    # 3. 解約されているかどうかを判定
                    if not subscription_result:
                        # レコードが存在しない場合は解約済みとみなす
                        logger.info(f"No subscription_periods record found for user_id: {user_id}")
                        return {
                            "is_available": False,
                            "reason": "no_subscription_record",
                            "subscription_info": None
                        }
                    
                    subscription_status, current_period_end, stripe_subscription_id = subscription_result
                    
                    # 解約制限の判定基準
                    restricted_statuses = ['canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'past_due']
                    active_statuses = ['active', 'trialing']
                    
                    if subscription_status in restricted_statuses:
                        logger.info(f"User {user_id} has restricted status: {subscription_status}")
                        return {
                            "is_available": False,
                            "reason": f"subscription_{subscription_status}",
                            "subscription_info": {
                                "subscription_status": subscription_status,
                                "current_period_end": current_period_end,
                                "stripe_subscription_id": stripe_subscription_id
                            }
                        }
                    elif subscription_status in active_statuses:
                        # アクティブな状態でも、期間終了をチェック
                        if current_period_end:
                            # タイムゾーンを統一して比較
                            if current_period_end.tzinfo is None:
                                # タイムゾーン情報がない場合はUTCとして扱う
                                current_period_end_utc = current_period_end.replace(tzinfo=timezone.utc)
                            else:
                                current_period_end_utc = current_period_end
                            
                            if datetime.now(timezone.utc) > current_period_end_utc:
                                logger.info(f"User {user_id} subscription period has expired: {current_period_end}")
                                return {
                                    "is_available": False,
                                    "reason": "subscription_period_expired",
                                    "subscription_info": {
                                        "subscription_status": subscription_status,
                                        "current_period_end": current_period_end,
                                        "stripe_subscription_id": stripe_subscription_id
                                    }
                                }
                        
                        logger.info(f"User {user_id} has active subscription: {subscription_status}")
                        return {
                            "is_available": True,
                            "reason": "active_subscription",
                            "subscription_info": {
                                "subscription_status": subscription_status,
                                "current_period_end": current_period_end,
                                "stripe_subscription_id": stripe_subscription_id
                            }
                        }
                    else:
                        # 不明なステータスの場合は制限
                        logger.info(f"User {user_id} has unknown subscription status: {subscription_status}")
                        return {
                            "is_available": False,
                            "reason": "unknown_subscription_status",
                            "subscription_info": {
                                "subscription_status": subscription_status,
                                "current_period_end": current_period_end,
                                "stripe_subscription_id": stripe_subscription_id
                            }
                        }
                        
        except Exception as e:
            logger.error(f"Error checking subscription status: {e}")
            return {
                "is_available": False,
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