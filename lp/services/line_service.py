import requests
import sqlite3
import psycopg2
import os
import stripe
import traceback

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

# LINE関連のサービス層

def send_line_message(reply_token, messages):
    """LINEメッセージ送信（複数メッセージ対応）"""
    import requests
    import os
    import traceback
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
    headers = {
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    # 単一メッセージの場合はリスト化
    if not isinstance(messages, list):
        messages = [messages]
    data = {
        'replyToken': reply_token,
        'messages': messages
    }
    try:
        response = requests.post('https://api.line.me/v2/bot/message/reply', headers=headers, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f'LINEメッセージ送信エラー: {e}')
        traceback.print_exc()
        # エラー詳細をerror.logにも追記
        with open('error.log', 'a', encoding='utf-8') as f:
            f.write('LINEメッセージ送信エラー: ' + str(e) + '\n')
            f.write(traceback.format_exc() + '\n')

def send_welcome_with_buttons(reply_token):
    import requests
    import os
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
    headers = {
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        'replyToken': reply_token,
        'messages': [
            {
                "type": "template",
                "altText": "ようこそ！メニューはこちら",
                "template": {
                    "type": "buttons",
                    "title": "ようこそ！",
                    "text": "ご利用を開始するには下のボタンを押してください。",
                    "actions": [
                        {
                            "type": "message",
                            "label": "コンテンツ追加",
                            "text": "追加"
                        },
                        {
                            "type": "message",
                            "label": "使い方を見る",
                            "text": "ヘルプ"
                        }
                    ]
                }
            }
        ]
    }
    try:
        response = requests.post('https://api.line.me/v2/bot/message/reply', headers=headers, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f'LINEテンプレートメッセージ送信エラー: {e}')
        import traceback
        traceback.print_exc()
        with open('error.log', 'a', encoding='utf-8') as f:
            f.write('LINEテンプレートメッセージ送信エラー: ' + str(e) + '\n')
            f.write(traceback.format_exc() + '\n')

def create_rich_menu():
    rich_menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "AIコレクションズ メニュー",
        "chatBarText": "メニュー",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 500, "height": 843},
                "action": {"type": "postback", "data": "action=add_content", "label": "追加"}
            },
            {
                "bounds": {"x": 500, "y": 0, "width": 500, "height": 843},
                "action": {"type": "postback", "data": "action=cancel_content", "label": "解約"}
            },
            {
                "bounds": {"x": 1000, "y": 0, "width": 500, "height": 843},
                "action": {"type": "postback", "data": "action=check_status", "label": "状態"}
            },
            {
                "bounds": {"x": 1500, "y": 0, "width": 500, "height": 843},
                "action": {"type": "postback", "data": "action=help", "label": "ヘルプ"}
            },
            {
                "bounds": {"x": 2000, "y": 0, "width": 500, "height": 843},
                "action": {"type": "postback", "data": "action=share", "label": "友達に紹介"}
            }
        ]
    }
    headers = {
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    response = requests.post('https://api.line.me/v2/bot/richmenu', headers=headers, json=rich_menu)
    response.raise_for_status()
    return response.json()['richMenuId']

def set_rich_menu_image(rich_menu_id, image_path='static/images/richmenu.png'):
    """リッチメニューに画像を設定"""
    try:
        # リッチメニュー画像を生成
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        # 画像を生成
        width, height = 2500, 843
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # フォント設定（デフォルトフォントを使用）
        try:
            font = ImageFont.truetype("arial.ttf", 60)
        except:
            font = ImageFont.load_default()
        
        # メニュー項目を描画
        menu_items = [
            ("追加", (200, 200)),
            ("状態", (700, 200)),
            ("解約", (1200, 200)),
            ("メニュー", (1700, 200))
        ]
        
        for text, pos in menu_items:
            draw.text(pos, text, fill='black', font=font)
        
        # 画像をバイトデータに変換
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        headers = {
            'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
            'Content-Type': 'image/png'
        }
        
        response = requests.post(
            f'https://api.line.me/v2/bot/richmenu/{rich_menu_id}/content',
            headers=headers,
            data=img_byte_arr
        )
        
        if response.status_code == 200:
            print(f"リッチメニュー画像設定成功: {rich_menu_id}")
            return True
        else:
            print(f"リッチメニュー画像設定失敗: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"リッチメニュー画像設定エラー: {e}")
        return False

def set_default_rich_menu(rich_menu_id):
    """デフォルトリッチメニューを設定"""
    try:
        headers = {
            'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            f'https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}',
            headers=headers
        )
        
        if response.status_code == 200:
            print(f"デフォルトリッチメニュー設定成功: {rich_menu_id}")
            return True
        else:
            print(f"デフォルトリッチメニュー設定失敗: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"デフォルトリッチメニュー設定エラー: {e}")
        return False

def delete_all_rich_menus():
    """既存のリッチメニューをすべて削除"""
    try:
        headers = {
            'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
        }
        
        response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
        
        if response.status_code == 200:
            richmenus = response.json().get('richmenus', [])
            for rm in richmenus:
                delete_response = requests.delete(f'https://api.line.me/v2/bot/richmenu/{rm["richMenuId"]}', headers=headers)
                if delete_response.status_code == 200:
                    print(f"リッチメニュー削除成功: {rm['richMenuId']}")
                else:
                    print(f"リッチメニュー削除失敗: {rm['richMenuId']} - {delete_response.status_code}")
            print(f"既存のリッチメニュー削除完了: {len(richmenus)}件")
        else:
            print(f"リッチメニュー一覧取得失敗: {response.status_code}")
            
    except Exception as e:
        print(f"リッチメニュー削除エラー: {e}")

def setup_rich_menu():
    import time
    delete_all_rich_menus()
    rich_menu_id = create_rich_menu()
    time.sleep(1)  # 作成直後に1秒待機
    set_rich_menu_image(rich_menu_id)
    set_default_rich_menu(rich_menu_id)
    return rich_menu_id 

def get_db_connection():
    DATABASE_URL = os.getenv('DATABASE_URL', 'database.db')
    if DATABASE_URL.startswith('postgresql://'):
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect(DATABASE_URL)

def handle_add_content(reply_token, user_id_db, stripe_subscription_id):
    try:
        content_menu = (
            "📚 コンテンツ選択メニュー\n\n"
            "利用可能なコンテンツを選択してください：\n"
            "1️⃣ AI秘書機能\n"
            "2️⃣ 会計管理ツール\n"
            "3️⃣ スケジュール管理\n"
            "4️⃣ タスク管理\n\n"
            "選択するには：\n"
            "「1」- AI秘書機能\n"
            "「2」- 会計管理ツール\n"
            "「3」- スケジュール管理\n"
            "「4」- タスク管理\n"
            "または、番号を直接入力してください。"
        )
        send_line_message(reply_token, [{"type": "text", "text": content_menu}])
    except Exception as e:
        print(f'コンテンツ選択メニューエラー: {e}')
        send_line_message(reply_token, [{"type": "text", "text": "❌ エラーが発生しました。しばらく時間をおいて再度お試しください。"}])

def handle_content_selection(reply_token, user_id_db, stripe_subscription_id, content_number):
    try:
        content_info = {
            '1': {
                'name': 'AI秘書機能',
                'price': 1500,
                'description': '24時間対応のAI秘書',
                'usage': 'LINEで直接メッセージを送るだけで、予定管理、メール作成、リマインダー設定などができます。',
                'url': 'https://lp-production-9e2c.up.railway.app/secretary'
            },
            '2': {
                'name': '会計管理ツール',
                'price': 1500,
                'description': '自動会計・経費管理',
                'usage': 'レシートを撮影するだけで自動で経費を記録し、月次レポートを自動生成します。',
                'url': 'https://lp-production-9e2c.up.railway.app/accounting'
            },
            '3': {
                'name': 'スケジュール管理',
                'price': 1500,
                'description': 'AIによる最適スケジュール',
                'usage': '予定を入力すると、AIが最適なスケジュールを提案し、効率的な時間管理をサポートします。',
                'url': 'https://lp-production-9e2c.up.railway.app/schedule'
            },
            '4': {
                'name': 'タスク管理',
                'price': 1500,
                'description': 'プロジェクト管理・進捗追跡',
                'usage': 'プロジェクトのタスクを管理し、進捗状況を自動で追跡・報告します。',
                'url': 'https://lp-production-9e2c.up.railway.app/task'
            }
        }
        if content_number not in content_info:
            send_line_message(reply_token, [{"type": "text", "text": "❌ 無効な選択です。1-4の数字で選択してください。"}])
            return
        content = content_info[content_number]
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM usage_logs WHERE user_id = %s', (user_id_db,))
        usage_count = c.fetchone()[0]
        conn.close()
        is_free = usage_count == 0
        price_message = "🎉 **1個目は無料です！**" if is_free else f"💰 料金：{content['price']:,}円"
        confirm_message = f"""📋 選択内容の確認

📚 コンテンツ：{content['name']}
📝 内容：{content['description']}
{price_message}

このコンテンツを追加しますか？

✅ 追加する場合は「はい」と入力
❌ キャンセルする場合は「いいえ」と入力"""
        send_line_message(reply_token, [{"type": "text", "text": confirm_message}])
        
    except Exception as e:
        print(f'コンテンツ選択エラー: {e}')
        send_line_message(reply_token, [{"type": "text", "text": "❌ エラーが発生しました。しばらく時間をおいて再度お試しください。"}])

def handle_content_confirmation(reply_token, user_id_db, stripe_subscription_id, content_number, confirmed):
    try:
        if not confirmed:
            send_line_message(reply_token, [{"type": "text", "text": "❌ キャンセルしました。\n\n何か他にお手伝いできることはありますか？"}])
            return
        content_info = {
            '1': {
                'name': 'AI秘書機能',
                'price': 1500,
                'description': '24時間対応のAI秘書',
                'usage': 'LINEで直接メッセージを送るだけで、予定管理、メール作成、リマインダー設定などができます。',
                'url': 'https://lp-production-9e2c.up.railway.app/secretary'
            },
            '2': {
                'name': '会計管理ツール',
                'price': 1500,
                'description': '自動会計・経費管理',
                'usage': 'レシートを撮影するだけで自動で経費を記録し、月次レポートを自動生成します。',
                'url': 'https://lp-production-9e2c.up.railway.app/accounting'
            },
            '3': {
                'name': 'スケジュール管理',
                'price': 1500,
                'description': 'AIによる最適スケジュール',
                'usage': '予定を入力すると、AIが最適なスケジュールを提案し、効率的な時間管理をサポートします。',
                'url': 'https://lp-production-9e2c.up.railway.app/schedule'
            },
            '4': {
                'name': 'タスク管理',
                'price': 1500,
                'description': 'プロジェクト管理・進捗追跡',
                'usage': 'プロジェクトのタスクを管理し、進捗状況を自動で追跡・報告します。',
                'url': 'https://lp-production-9e2c.up.railway.app/task'
            }
        }
        content = content_info[content_number]
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM usage_logs WHERE user_id = %s', (user_id_db,))
        usage_count = c.fetchone()[0]
        conn.close()
        is_free = usage_count == 0
        usage_record = None
        if not is_free:
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            usage_item = None
            for item in subscription['items']['data']:
                if item['price']['id'] == os.getenv('STRIPE_USAGE_PRICE_ID'):
                    usage_item = item
                    break
            if not usage_item:
                send_line_message(reply_token, [{"type": "text", "text": f"❌ 従量課金アイテムが見つかりません。\n\n設定されている価格ID: {os.getenv('STRIPE_USAGE_PRICE_ID')}\n\nサポートにお問い合わせください。"}])
                return
            subscription_item_id = usage_item['id']
            try:
                # 新しいStripe APIを使用して使用量レコードを作成
                import requests
                import os
                import time
                
                stripe_secret_key = os.getenv('STRIPE_SECRET_KEY')
                headers = {
                    'Authorization': f'Bearer {stripe_secret_key}',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
                
                response = requests.post(
                    f'https://api.stripe.com/v1/subscription_items/{subscription_item_id}/usage_records',
                    headers=headers,
                    data={
                        'quantity': 1,
                        'timestamp': int(time.time()),
                        'action': 'increment'
                    }
                )
                
                if response.status_code == 200:
                    usage_record = response.json()
                    print(f'使用量レコード作成成功: {usage_record}')
                else:
                    print(f'使用量レコード作成エラー: {response.status_code} - {response.text}')
                    send_line_message(reply_token, [{"type": "text", "text": f"❌ 使用量記録の作成に失敗しました。\n\nエラー: {response.text}"}])
                    return
            except Exception as usage_error:
                print(f'使用量レコード作成エラー: {usage_error}')
                send_line_message(reply_token, [{"type": "text", "text": f"❌ 使用量記録の作成に失敗しました。\n\nエラー: {str(usage_error)}"}])
                return
        try:
            conn = get_db_connection()
            c = conn.cursor()
            
            # usage_record_idを初期化
            usage_record_id = None
            
            if is_free:
                c.execute('INSERT INTO usage_logs (user_id, usage_quantity, stripe_usage_record_id, is_free, content_type) VALUES (%s, %s, %s, %s, %s)',
                          (user_id_db, 1, None, True, content['name']))
            else:
                # usage_recordのidフィールドを安全に取得
                if usage_record and 'id' in usage_record:
                    usage_record_id = usage_record['id']
                elif usage_record and 'meter_event' in usage_record:
                    usage_record_id = usage_record['meter_event']['id']
                
                c.execute('INSERT INTO usage_logs (user_id, usage_quantity, stripe_usage_record_id, is_free, content_type) VALUES (%s, %s, %s, %s, %s)',
                          (user_id_db, 1, usage_record_id, False, content['name']))
            conn.commit()
            conn.close()
            print(f'DB登録成功: user_id={user_id_db}, is_free={is_free}, usage_record_id={usage_record_id}')
        except Exception as db_error:
            print(f'DB登録エラー: {db_error}')
            import traceback
            print(traceback.format_exc())
            send_line_message(reply_token, [{"type": "text", "text": f"❌ データベース登録に失敗しました。\n\nエラー: {str(db_error)}"}])
            return
        if is_free:
            success_message = f"""🎉 コンテンツ追加完了！

📚 追加内容：
• {content['name']} 1件追加

💰 料金：
• 🎉 **無料で追加されました！**

📖 使用方法：
{content['usage']}

🔗 アクセスURL：
{content['url']}

何か他にお手伝いできることはありますか？"""
        else:
            success_message = f"""✅ コンテンツ追加完了！

📚 追加内容：
• {content['name']} 1件追加

💰 料金：
• 追加料金：{content['price']:,}円（次回請求時に反映）

📖 使用方法：
{content['usage']}

🔗 アクセスURL：
{content['url']}

何か他にお手伝いできることはありますか？"""
        send_line_message(reply_token, [{"type": "text", "text": success_message}])
    except Exception as e:
        send_line_message(reply_token, [{"type": "text", "text": "❌ エラーが発生しました。しばらく時間をおいて再度お試しください。"}])

def handle_status_check(reply_token, user_id_db):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT content_type, is_free, created_at FROM usage_logs WHERE user_id = %s ORDER BY created_at DESC', (user_id_db,))
        usage_logs = c.fetchall()
        conn.close()
        if not usage_logs:
            status_message = """📊 利用状況

📈 今月の追加回数：0回
💰 追加料金：0円

💡 ヒント：
• 「追加」でコンテンツを追加
• 「メニュー」で機能一覧を確認"""
        else:
            total_cost = 0
            content_list = []
            for log in usage_logs:
                content_type = log[0] or "不明"
                is_free = log[1]
                created_at = log[2]
                if not is_free:
                    total_cost += 1500
                content_list.append(f"• {content_type} ({'無料' if is_free else '1,500円'}) - {created_at}")
            status_message = f"""📊 利用状況

📈 今月の追加回数：{len(usage_logs)}回
💰 追加料金：{total_cost:,}円

📚 追加済みコンテンツ：
{chr(10).join(content_list[:5])}  # 最新5件まで表示

💡 ヒント：
• 「追加」でコンテンツを追加
• 「メニュー」で機能一覧を確認"""
        send_line_message(reply_token, [{"type": "text", "text": status_message}])
    except Exception as e:
        send_line_message(reply_token, [{"type": "text", "text": "❌ 利用状況の取得に失敗しました。しばらく時間をおいて再度お試しください。"}])

def handle_cancel_request(reply_token, user_id_db, stripe_subscription_id):
    try:
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        items = subscription['items']['data']
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT content_type, is_free FROM usage_logs WHERE user_id = %s', (user_id_db,))
        usage_free_map = {}
        for row in c.fetchall():
            usage_free_map[row[0]] = usage_free_map.get(row[0], False) or row[1]
        conn.close()
        content_choices = []
        for idx, item in enumerate(items, 1):
            price = item['price']
            name = price.get('nickname') or price.get('id')
            if 'AI秘書' in name or 'secretary' in name or 'prod_SgSj7btk61lSNI' in price.get('product',''):
                jp_name = 'AI秘書機能'
            elif '会計' in name or 'accounting' in name or 'prod_SgSnVeUB5DAihu' in price.get('product',''):
                jp_name = '会計管理ツール'
            elif 'スケジュール' in name or 'schedule' in name:
                jp_name = 'スケジュール管理'
            elif 'タスク' in name or 'task' in name:
                jp_name = 'タスク管理'
            elif price.get('unit_amount',0) >= 500000:
                jp_name = '月額基本料金'
            else:
                jp_name = name
            amount = price.get('unit_amount', 0)
            amount_jpy = int(amount) // 100 if amount else 0
            is_free = usage_free_map.get(jp_name, False)
            display_price = '0円' if is_free else f'{amount_jpy:,}円'
            content_choices.append(f"{idx}. {jp_name}（{display_price}/月）")
        if not content_choices:
            send_line_message(reply_token, [{"type": "text", "text": "現在契約中のコンテンツはありません。"}])
            return
        choice_message = "\n".join(content_choices)
        send_line_message(reply_token, [{"type": "text", "text": f"解約したいコンテンツを選んでください（カンマ区切りで複数選択可）:\n{choice_message}\n\n例: 1,2"}])
    except Exception as e:
        send_line_message(reply_token, [{"type": "text", "text": "❌ 契約中コンテンツの取得に失敗しました。しばらく時間をおいて再度お試しください。"}])

def handle_cancel_selection(reply_token, user_id_db, stripe_subscription_id, selection_text):
    try:
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        items = subscription['items']['data']
        indices = [int(x.strip())-1 for x in selection_text.split(',') if x.strip().isdigit()]
        cancelled = []
        for idx in indices:
            if 0 <= idx < len(items):
                item = items[idx]
                stripe.SubscriptionItem.delete(item['id'], proration_behavior='none')
                price = item['price']
                name = price.get('nickname') or price.get('id')
                if 'AI秘書' in name or 'secretary' in name or 'prod_SgSj7btk61lSNI' in price.get('product',''):
                    jp_name = 'AI秘書機能'
                elif '会計' in name or 'accounting' in name or 'prod_SgSnVeUB5DAihu' in price.get('product',''):
                    jp_name = '会計管理ツール'
                elif 'スケジュール' in name or 'schedule' in name:
                    jp_name = 'スケジュール管理'
                elif 'タスク' in name or 'task' in name:
                    jp_name = 'タスク管理'
                elif price.get('unit_amount',0) >= 500000:
                    jp_name = '月額基本料金'
                else:
                    jp_name = name
                cancelled.append(jp_name)
        if cancelled:
            send_line_message(reply_token, [{"type": "text", "text": f"以下のコンテンツの解約を受け付けました（請求期間終了まで利用可能です）：\n" + "\n".join(cancelled)}])
        else:
            send_line_message(reply_token, [{"type": "text", "text": "有効な番号が選択されませんでした。もう一度お試しください。"}])
    except Exception as e:
        send_line_message(reply_token, [{"type": "text", "text": "❌ 解約処理に失敗しました。しばらく時間をおいて再度お試しください。"}])

def get_welcome_message():
    return "ようこそ！LINE連携が完了しました。"

def get_not_registered_message():
    return "ご登録情報が見つかりません。LPからご登録ください。" 