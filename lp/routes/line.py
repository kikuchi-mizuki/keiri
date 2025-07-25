from flask import Blueprint, request, jsonify
import os, json, hmac, hashlib, base64
from services.line_service import send_line_message
from services.line_service import (
    handle_add_content, handle_content_selection,
    handle_content_confirmation, handle_status_check, handle_cancel_request,
    handle_cancel_selection, handle_subscription_cancel, handle_cancel_menu,
    get_welcome_message, get_not_registered_message
)
from utils.message_templates import get_menu_message, get_help_message, get_default_message
from utils.db import get_db_connection

line_bp = Blueprint('line', __name__)

user_states = {}

@line_bp.route('/line/webhook', methods=['POST'])
def line_webhook():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.data.decode('utf-8')
    LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
    if LINE_CHANNEL_SECRET:
        try:
            hash = hmac.new(LINE_CHANNEL_SECRET.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).digest()
            expected_signature = base64.b64encode(hash).decode('utf-8')
            if not hmac.compare_digest(signature, expected_signature):
                return 'Invalid signature', 400
        except Exception:
            return 'Signature verification error', 400
    try:
        events = json.loads(body).get('events', [])
        for event in events:
            # 友達追加イベントの処理
            if event.get('type') == 'follow':
                user_id = event['source']['userId']
                print(f'[DEBUG] 友達追加イベント: user_id={user_id}')
                
                # 直近のline_user_id未設定ユーザーを自動で紐付け
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('SELECT id, stripe_subscription_id FROM users WHERE line_user_id IS NULL ORDER BY created_at DESC LIMIT 1')
                user = c.fetchone()
                print(f'[DEBUG] 友達追加時の未紐付けユーザー検索結果: {user}')
                
                if user:
                    c.execute('UPDATE users SET line_user_id = %s WHERE id = %s', (user_id, user[0]))
                    conn.commit()
                    print(f'[DEBUG] ユーザー紐付け完了: user_id={user_id}, db_user_id={user[0]}')
                    
                    # ボタン付きのウェルカムメッセージを送信
                    try:
                        from services.line_service import send_welcome_with_buttons
                        send_welcome_with_buttons(event['replyToken'])
                        print(f'[DEBUG] ウェルカムメッセージ送信完了: user_id={user_id}')
                    except Exception as e:
                        print(f'[DEBUG] ウェルカムメッセージ送信エラー: {e}')
                        import traceback
                        traceback.print_exc()
                        # エラーが発生した場合は簡単なテキストメッセージを送信
                        send_line_message(event['replyToken'], [{"type": "text", "text": "ようこそ！AIコレクションズへ\n\n「追加」と入力してコンテンツを追加してください。"}])
                else:
                    # 未登録ユーザーの場合
                    print(f'[DEBUG] 未登録ユーザー: user_id={user_id}')
                    from utils.message_templates import get_not_registered_message
                    send_line_message(event['replyToken'], [{"type": "text", "text": get_not_registered_message()}])
                
                conn.close()
                continue
            
            # 友達削除イベントの処理
            elif event.get('type') == 'unfollow':
                user_id = event['source']['userId']
                print(f'[DEBUG] 友達削除イベント: user_id={user_id}')
                
                # line_user_idをクリア（ブロックされた場合の対応）
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('UPDATE users SET line_user_id = NULL WHERE line_user_id = %s', (user_id,))
                conn.commit()
                conn.close()
                print(f'[DEBUG] ユーザー紐付け解除: user_id={user_id}')
                continue
            
            # テキストメッセージの処理
            if event.get('type') == 'message' and event['message'].get('type') == 'text':
                user_id = event['source']['userId']
                text = event['message']['text']
                print(f'[DEBUG] テキストメッセージ受信: user_id={user_id}, text={text}')
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('SELECT id, stripe_subscription_id, line_user_id FROM users WHERE line_user_id = %s', (user_id,))
                user = c.fetchone()
                print(f'[DEBUG] 既存ユーザー検索結果: {user}')
                
                if not user:
                    print(f'[DEBUG] 既存ユーザーが見つからないため、未紐付けユーザーを検索')
                    c.execute('SELECT id, stripe_subscription_id FROM users WHERE line_user_id IS NULL ORDER BY created_at DESC LIMIT 1')
                    user = c.fetchone()
                    print(f'[DEBUG] 未紐付けユーザー検索結果: {user}')
                    
                    if user:
                        print(f'[DEBUG] 未紐付けユーザー発見、紐付け処理開始: user_id={user_id}, db_user_id={user[0]}')
                        c.execute('UPDATE users SET line_user_id = %s WHERE id = %s', (user_id, user[0]))
                        conn.commit()
                        print(f'[DEBUG] 初回メッセージ時のユーザー紐付け完了: user_id={user_id}, db_user_id={user[0]}')
                        # 決済画面からLINEに移動した時の初回案内文
                        print(f'[DEBUG] 案内文送信開始: user_id={user_id}, replyToken={event["replyToken"]}')
                        try:
                            from services.line_service import send_welcome_with_buttons
                            send_welcome_with_buttons(event['replyToken'])
                            print(f'[DEBUG] 初回メッセージ時の案内文送信完了: user_id={user_id}')
                        except Exception as e:
                            print(f'[DEBUG] 初回メッセージ時の案内文送信エラー: {e}')
                            import traceback
                            traceback.print_exc()
                            # エラーが発生した場合は簡単なテキストメッセージを送信
                            send_line_message(event['replyToken'], [{"type": "text", "text": "ようこそ！AIコレクションズへ\n\n「追加」と入力してコンテンツを追加してください。"}])
                    else:
                        print(f'[DEBUG] 未紐付けユーザーも見つからない')
                        send_line_message(event['replyToken'], [{"type": "text", "text": get_not_registered_message()}])
                    conn.close()
                    continue
                user_id_db = user[0]
                stripe_subscription_id = user[1]
                
                # サブスクリプションIDが存在しない場合
                if not stripe_subscription_id:
                    payment_message = {
                        "type": "template",
                        "altText": "決済が必要です",
                        "template": {
                            "type": "buttons",
                            "title": "決済が必要です",
                            "text": "サブスクリプションが設定されていません。\n\n決済画面から登録してください。",
                            "actions": [
                                {
                                    "type": "uri",
                                    "label": "決済画面へ",
                                    "uri": "https://lp-production-9e2c.up.railway.app"
                                }
                            ]
                        }
                    }
                    send_line_message(event['replyToken'], [payment_message])
                    conn.close()
                    continue
                
                # 既存ユーザーの初回メッセージ時に案内文を送信（初回のみ）
                if user_id not in user_states:
                    user_states[user_id] = None
                
                state = user_states.get(user_id, None)
                print(f'[DEBUG] ユーザー状態: user_id={user_id}, state={state}')
                
                if state is None:
                    print(f'[DEBUG] 既存ユーザーの初回メッセージ処理: user_id={user_id}')
                    try:
                        from services.line_service import send_welcome_with_buttons
                        send_welcome_with_buttons(event['replyToken'])
                        print(f'[DEBUG] 既存ユーザーへの案内文送信完了: user_id={user_id}')
                        # 案内文送信済みフラグを設定
                        user_states[user_id] = 'welcome_sent'
                        # 案内文を送信した後は処理を終了（replyTokenは1回しか使用できない）
                        conn.close()
                        continue
                    except Exception as e:
                        print(f'[DEBUG] 既存ユーザーへの案内文送信エラー: {e}')
                        import traceback
                        traceback.print_exc()
                elif state == 'welcome_sent':
                    print(f'[DEBUG] 既存ユーザーの案内文は既に送信済み: user_id={user_id}')
                else:
                    print(f'[DEBUG] ユーザーは特定の状態: user_id={user_id}, state={state}')
                if text == '追加':
                    user_states[user_id] = 'add_select'
                    handle_add_content(event['replyToken'], user_id_db, stripe_subscription_id)
                elif text == 'メニュー':
                    send_line_message(event['replyToken'], [get_menu_message()])
                elif text == 'ヘルプ':
                    send_line_message(event['replyToken'], get_help_message())
                elif text == '状態':
                    handle_status_check(event['replyToken'], user_id_db)
                elif text == '解約':
                    handle_cancel_menu(event['replyToken'], user_id_db, stripe_subscription_id)
                elif text == 'サブスクリプション解約':
                    handle_subscription_cancel(event['replyToken'], user_id_db, stripe_subscription_id)
                elif text == 'コンテンツ解約':
                    user_states[user_id] = 'cancel_select'
                    handle_cancel_request(event['replyToken'], user_id_db, stripe_subscription_id)
                elif state == 'cancel_select' and all(x.strip().isdigit() for x in text.split(',')):
                    print(f'[DEBUG] 解約選択処理: user_id={user_id}, state={state}, text={text}')
                    handle_cancel_selection(event['replyToken'], user_id_db, stripe_subscription_id, text)
                    user_states[user_id] = None
                elif state == 'add_select' and text in ['1', '2', '3', '4']:
                    # 選択したコンテンツ番号を保存
                    user_states[user_id] = f'confirm_{text}'
                    handle_content_selection(event['replyToken'], user_id_db, stripe_subscription_id, text)
                elif text.lower() in ['はい', 'yes', 'y'] and state and state.startswith('confirm_'):
                    # 確認状態からコンテンツ番号を取得
                    content_number = state.split('_')[1]
                    handle_content_confirmation(event['replyToken'], user_id_db, stripe_subscription_id, content_number, True)
                    user_states[user_id] = None
                elif text.lower() in ['いいえ', 'no', 'n'] and state and state.startswith('confirm_'):
                    # 確認状態からコンテンツ番号を取得
                    content_number = state.split('_')[1]
                    handle_content_confirmation(event['replyToken'], user_id_db, stripe_subscription_id, content_number, False)
                    user_states[user_id] = None
                elif '@' in text and '.' in text and len(text) < 100:
                    import unicodedata
                    def normalize_email(email):
                        email = email.strip().lower()
                        email = unicodedata.normalize('NFKC', email)
                        return email
                    normalized_email = normalize_email(text)
                    c.execute('SELECT id, line_user_id FROM users WHERE email = %s', (normalized_email,))
                    user = c.fetchone()
                    if user:
                        if user[1] is None:
                            c.execute('UPDATE users SET line_user_id = %s WHERE id = %s', (user_id, user[0]))
                            conn.commit()
                            print(f'[DEBUG] メールアドレス連携完了: user_id={user_id}, db_user_id={user[0]}')
                            # 決済画面からLINEに移動した時の初回案内文
                            try:
                                from services.line_service import send_welcome_with_buttons
                                send_welcome_with_buttons(event['replyToken'])
                                print(f'[DEBUG] メールアドレス連携時の案内文送信完了: user_id={user_id}')
                            except Exception as e:
                                print(f'[DEBUG] メールアドレス連携時の案内文送信エラー: {e}')
                                import traceback
                                traceback.print_exc()
                                # エラーが発生した場合は簡単なテキストメッセージを送信
                                send_line_message(event['replyToken'], [{"type": "text", "text": "ようこそ！AIコレクションズへ\n\n「追加」と入力してコンテンツを追加してください。"}])
                        else:
                            send_line_message(event['replyToken'], [{"type": "text", "text": 'このメールアドレスは既にLINE連携済みです。'}])
                    else:
                        # 救済策: 直近のline_user_id未設定ユーザーを自動で紐付け
                        c.execute('SELECT id FROM users WHERE line_user_id IS NULL ORDER BY created_at DESC LIMIT 1')
                        fallback_user = c.fetchone()
                        if fallback_user:
                            c.execute('UPDATE users SET line_user_id = %s WHERE id = %s', (user_id, fallback_user[0]))
                            conn.commit()
                            print(f'[DEBUG] 救済策でのユーザー紐付け完了: user_id={user_id}, db_user_id={fallback_user[0]}')
                            # 決済画面からLINEに移動した時の初回案内文
                            try:
                                from services.line_service import send_welcome_with_buttons
                                send_welcome_with_buttons(event['replyToken'])
                                print(f'[DEBUG] 救済策での案内文送信完了: user_id={user_id}')
                            except Exception as e:
                                print(f'[DEBUG] 救済策での案内文送信エラー: {e}')
                                import traceback
                                traceback.print_exc()
                                # エラーが発生した場合は簡単なテキストメッセージを送信
                                send_line_message(event['replyToken'], [{"type": "text", "text": "ようこそ！AIコレクションズへ\n\n「追加」と入力してコンテンツを追加してください。"}])
                        else:
                            send_line_message(event['replyToken'], [{"type": "text", "text": 'ご登録メールアドレスが見つかりません。LPでご登録済みかご確認ください。'}])
                else:
                    send_line_message(event['replyToken'], [get_default_message()])
                conn.close()
            # リッチメニューのpostbackイベントの処理
            elif event.get('type') == 'postback':
                user_id = event['source']['userId']
                postback_data = event['postback']['data']
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('SELECT id, stripe_subscription_id, line_user_id FROM users WHERE line_user_id = %s', (user_id,))
                user = c.fetchone()
                if not user:
                    send_line_message(event['replyToken'], [{"type": "text", "text": get_not_registered_message()}])
                    conn.close()
                    continue
                user_id_db = user[0]
                stripe_subscription_id = user[1]
                # postbackデータに基づいて処理
                if postback_data == 'action=add_content':
                    user_states[user_id] = 'add_select'
                    handle_add_content(event['replyToken'], user_id_db, stripe_subscription_id)
                elif postback_data == 'action=check_status':
                    handle_status_check(event['replyToken'], user_id_db)
                elif postback_data == 'action=cancel_content':
                    handle_cancel_menu(event['replyToken'], user_id_db, stripe_subscription_id)
                elif postback_data == 'action=help':
                    send_line_message(event['replyToken'], get_help_message())
                elif postback_data == 'action=share':
                    share_message = """📢 友達に紹介

AIコレクションズをご利用いただき、ありがとうございます！

🤝 友達にもおすすめしませんか？
• 1個目のコンテンツは無料
• 月額5,000円で複数のAIツールを利用可能
• 従量課金で必要な分だけ追加

🔗 紹介URL：
https://lp-production-9e2c.up.railway.app

友達が登録すると、あなたにも特典があります！"""
                    send_line_message(event['replyToken'], [{"type": "text", "text": share_message}])
                conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
    return jsonify({'status': 'ok'}) 