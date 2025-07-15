from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
import os
import stripe
from dotenv import load_dotenv
import hashlib
import hmac
import base64
import json
import requests
import sqlite3
import psycopg2
from urllib.parse import urlparse

load_dotenv()

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

MONTHLY_PRICE_ID = os.getenv('STRIPE_MONTHLY_PRICE_ID')
USAGE_PRICE_ID = os.getenv('STRIPE_USAGE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

DATABASE_URL = os.getenv('DATABASE_URL', 'database.db')

def get_db_connection():
    """データベース接続を取得（SQLiteまたはPostgreSQL）"""
    if DATABASE_URL.startswith('postgresql://'):
        # PostgreSQL接続
        return psycopg2.connect(DATABASE_URL)
    else:
        # SQLite接続（開発環境）
        return sqlite3.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # PostgreSQLとSQLiteの違いを吸収
    if DATABASE_URL.startswith('postgresql://'):
        # PostgreSQL用のテーブル作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                stripe_customer_id VARCHAR(255) UNIQUE NOT NULL,
                stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL,
                line_user_id VARCHAR(255) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                usage_quantity INTEGER DEFAULT 1,
                stripe_usage_record_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
    else:
        # SQLite用のテーブル作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255) UNIQUE NOT NULL,
                stripe_customer_id VARCHAR(255) UNIQUE NOT NULL,
                stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL,
                line_user_id VARCHAR(255) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                usage_quantity INTEGER DEFAULT 1,
                stripe_usage_record_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
    
    conn.commit()
    conn.close()

init_db()

app = Flask(__name__, static_folder='static', static_url_path='/static')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/thanks')
def thanks():
    return render_template('thanks.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return app.send_static_file(filename)

@app.route('/line/status')
def line_status():
    """LINE Bot設定状況を確認"""
    status = {
        'line_channel_secret_set': bool(LINE_CHANNEL_SECRET),
        'line_channel_access_token_set': bool(LINE_CHANNEL_ACCESS_TOKEN),
        'stripe_monthly_price_id_set': bool(MONTHLY_PRICE_ID),
        'stripe_usage_price_id_set': bool(USAGE_PRICE_ID),
        'stripe_webhook_secret_set': bool(STRIPE_WEBHOOK_SECRET),
        'database_url_set': bool(DATABASE_URL),
    }
    return jsonify(status)

@app.route('/debug/users')
def debug_users():
    """データベース内のユーザー情報を確認"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT id, email, stripe_customer_id, stripe_subscription_id, line_user_id, created_at FROM users ORDER BY created_at DESC')
        users = c.fetchall()
        conn.close()
        
        user_list = []
        for user in users:
            user_list.append({
                'id': user[0],
                'email': user[1],
                'stripe_customer_id': user[2],
                'stripe_subscription_id': user[3],
                'line_user_id': user[4],
                'created_at': user[5]
            })
        
        return jsonify({
            'total_users': len(user_list),
            'users': user_list
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/subscription/<subscription_id>')
def debug_subscription(subscription_id):
    """サブスクリプションの詳細を確認"""
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        usage_items = []
        
        for item in subscription['items']['data']:
            usage_items.append({
                'id': item['id'],
                'price_id': item['price']['id'],
                'price_nickname': item['price'].get('nickname', 'No nickname'),
                'usage_type': item['price'].get('usage_type', 'Unknown'),
                'billing_scheme': item['price'].get('billing_scheme', 'Unknown')
            })
        
        return jsonify({
            'subscription_id': subscription_id,
            'status': subscription['status'],
            'usage_price_id': USAGE_PRICE_ID,
            'items': usage_items,
            'total_items': len(usage_items)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/update_subscription/<new_subscription_id>')
def update_subscription_id(new_subscription_id):
    """サブスクリプションIDを更新"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 現在のサブスクリプションIDを確認
        c.execute('SELECT stripe_subscription_id FROM users WHERE line_user_id = ?', ('U1b9d0d75b0c770dc1107dde349d572f7',))
        current_subscription = c.fetchone()
        
        if current_subscription:
            old_subscription_id = current_subscription[0]
            print(f"現在のサブスクリプションID: {old_subscription_id}")
            
            # サブスクリプションIDを更新
            c.execute('UPDATE users SET stripe_subscription_id = ? WHERE line_user_id = ?', (new_subscription_id, 'U1b9d0d75b0c770dc1107dde349d572f7'))
            conn.commit()
            
            print(f"サブスクリプションIDを更新: {old_subscription_id} -> {new_subscription_id}")
            
            conn.close()
            
            return jsonify({
                'success': True,
                'old_subscription_id': old_subscription_id,
                'new_subscription_id': new_subscription_id,
                'message': f'サブスクリプションIDを更新しました: {old_subscription_id} -> {new_subscription_id}'
            })
        else:
            conn.close()
            return jsonify({'error': 'ユーザーが見つかりません'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form.get('email')
    if not email:
        return redirect(url_for('index'))

    # Stripe Checkoutセッション作成
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        mode='subscription',
        customer_email=email,
        line_items=[
            {
                'price': MONTHLY_PRICE_ID,
                'quantity': 1,
            },
        ],
        success_url=url_for('thanks', _external=True),
        cancel_url=url_for('index', _external=True),
    )
    return redirect(session.url, code=303)

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return 'Invalid signature', 400

    # イベント種別ごとに処理
    if event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        customer_id = invoice['customer']
        print(f'Stripe Webhook受信: invoice.payment_succeeded - {invoice["id"]}')
        print(f'Invoice詳細: {invoice}')
        
        # subscriptionキーが存在する場合のみ処理
        if 'subscription' in invoice:
            subscription_id = invoice['subscription']
            email = invoice['customer_email'] if 'customer_email' in invoice else None
            print(f'サブスクリプション情報: subscription_id={subscription_id}, email={email}')
            
            # DBに保存（既存ならスキップ）
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE stripe_customer_id = ?', (customer_id,))
            existing_user = c.fetchone()
            print(f'既存ユーザー確認: {existing_user}')
            
            if not existing_user:
                c.execute('INSERT INTO users (email, stripe_customer_id, stripe_subscription_id) VALUES (?, ?, ?)',
                          (email, customer_id, subscription_id))
                conn.commit()
                print(f'ユーザー登録完了: customer_id={customer_id}, subscription_id={subscription_id}')
            else:
                print(f'既存ユーザーが存在: {existing_user[0]}')
            conn.close()
            print('支払い成功（サブスクリプション）:', invoice['id'])
        else:
            print('支払い成功（サブスクリプション以外）:', invoice['id'])
            print('subscriptionキーが存在しないため、ユーザー登録をスキップ')
        # ここでLINE通知やDB更新などを今後追加
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        print('支払い失敗:', invoice['id'])
    elif event['type'] == 'customer.subscription.created':
        subscription = event['data']['object']
        customer_id = subscription['customer']
        subscription_id = subscription['id']
        print(f'サブスクリプション作成: {subscription_id}')
        print(f'Subscription詳細: {subscription}')
        
        # 顧客情報を取得
        try:
            customer = stripe.Customer.retrieve(customer_id)
            email = customer.get('email')
            print(f'顧客情報: customer_id={customer_id}, email={email}')
            
            # DBに保存（既存ならスキップ）
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE stripe_customer_id = ?', (customer_id,))
            existing_user = c.fetchone()
            print(f'既存ユーザー確認: {existing_user}')
            
            if not existing_user:
                c.execute('INSERT INTO users (email, stripe_customer_id, stripe_subscription_id) VALUES (?, ?, ?)',
                          (email, customer_id, subscription_id))
                conn.commit()
                print(f'ユーザー登録完了: customer_id={customer_id}, subscription_id={subscription_id}')
            else:
                print(f'既存ユーザーが存在: {existing_user[0]}')
            conn.close()
        except Exception as e:
            print(f'サブスクリプション作成処理エラー: {e}')
    # 他のイベントも必要に応じて追加

    return jsonify({'status': 'success'})

@app.route('/line/webhook', methods=['POST'])
def line_webhook():
    print("=== LINE Webhook受信 ===")
    print(f"Headers: {dict(request.headers)}")
    
    signature = request.headers.get('X-Line-Signature', '')
    body = request.data.decode('utf-8')
    print(f"Body: {body}")
    
    # 署名検証
    if LINE_CHANNEL_SECRET:
        try:
            hash = hmac.new(LINE_CHANNEL_SECRET.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).digest()
            expected_signature = base64.b64encode(hash).decode('utf-8')
            if not hmac.compare_digest(signature, expected_signature):
                print(f"署名検証失敗: {signature} != {expected_signature}")
                abort(400, 'Invalid signature')
        except Exception as e:
            print(f"署名検証エラー: {e}")
            abort(400, 'Signature verification error')
    else:
        print("LINE_CHANNEL_SECRETが設定されていません")
    
    # イベント処理
    try:
        events = json.loads(body).get('events', [])
        print(f"イベント数: {len(events)}")
        
        for event in events:
            print(f"イベント: {event}")
            
            if event.get('type') == 'message' and event['message'].get('type') == 'text':
                user_id = event['source']['userId']
                text = event['message']['text']
                print(f"ユーザーID: {user_id}, テキスト: {text}")
                
                # ユーザー情報を取得
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('SELECT id, stripe_subscription_id, line_user_id FROM users WHERE line_user_id = ?', (user_id,))
                user = c.fetchone()
                print(f"DB検索結果: {user}")
                
                if not user:
                    # line_user_id未登録なら最新ユーザーを取得し、紐付け
                    c.execute('SELECT id, stripe_subscription_id FROM users WHERE line_user_id IS NULL ORDER BY created_at DESC LIMIT 1')
                    user = c.fetchone()
                    print(f"未紐付けユーザー検索結果: {user}")
                    
                    # 全ユーザー数を確認
                    c.execute('SELECT COUNT(*) FROM users')
                    total_users = c.fetchone()[0]
                    print(f"データベース内の総ユーザー数: {total_users}")
                    
                    if user:
                        c.execute('UPDATE users SET line_user_id = ? WHERE id = ?', (user_id, user[0]))
                        conn.commit()
                        print(f"ユーザー紐付け完了: {user_id} -> {user[0]}")
                        # 歓迎メッセージを送信
                        send_line_message(event['replyToken'], get_welcome_message())
                    else:
                        # ユーザー未登録
                        print("ユーザー未登録")
                        send_line_message(event['replyToken'], get_not_registered_message())
                    conn.close()
                    continue
                
                # 登録済みユーザーの処理
                user_id_db = user[0]
                stripe_subscription_id = user[1]
                print(f"登録済みユーザー処理: user_id={user_id_db}, subscription_id={stripe_subscription_id}")
                
                # コマンド処理
                if text == '追加':
                    print("「追加」コマンド処理開始")
                    handle_add_content(event['replyToken'], user_id_db, stripe_subscription_id)
                elif text == 'メニュー':
                    print("「メニュー」コマンド処理")
                    send_line_message(event['replyToken'], get_menu_message())
                elif text == 'ヘルプ':
                    print("「ヘルプ」コマンド処理")
                    send_line_message(event['replyToken'], get_help_message())
                elif text == '状態':
                    print("「状態」コマンド処理")
                    handle_status_check(event['replyToken'], user_id_db)
                else:
                    print(f"デフォルトメッセージ送信: {text}")
                    send_line_message(event['replyToken'], get_default_message())
                
                conn.close()
    except Exception as e:
        print(f"LINE Webhook処理エラー: {e}")
        import traceback
        traceback.print_exc()
    
    return jsonify({'status': 'ok'})

def send_line_message(reply_token, message):
    """LINEメッセージを送信"""
    headers = {
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        'replyToken': reply_token,
        'messages': [{'type': 'text', 'text': message}]
    }
    try:
        response = requests.post('https://api.line.me/v2/bot/message/reply', headers=headers, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f'LINEメッセージ送信エラー: {e}')

def get_welcome_message():
    """歓迎メッセージ"""
    return """🎉 AIコレクションズへようこそ！

あなたのAI秘書が準備できました。

📋 利用可能なコマンド：
• 「追加」- コンテンツを追加
• 「メニュー」- メニューを表示
• 「状態」- 利用状況を確認
• 「ヘルプ」- ヘルプを表示

何かご質問がございましたら、お気軽にお声かけください！"""

def get_menu_message():
    """メニューメッセージ"""
    return """📋 AIコレクションズ メニュー

🤖 利用可能なAI秘書：
1. AI予定秘書 - スケジュール管理
2. AI経理秘書 - 見積書・請求書作成
3. AIタスクコンシェルジュ - タスク最適配置

💡 コマンド：
• 「追加」- コンテンツを追加
• 「状態」- 利用状況を確認
• 「ヘルプ」- ヘルプを表示

何かご質問がございましたら、お気軽にお声かけください！"""

def get_help_message():
    """ヘルプメッセージ"""
    return """❓ AIコレクションズ ヘルプ

📝 基本的な使い方：
1. 「追加」と送信してコンテンツを追加
2. 「状態」で利用状況を確認
3. 「メニュー」で利用可能な機能を確認

🔧 サポート：
ご不明な点がございましたら、以下のコマンドをお試しください：
• 「メニュー」- 機能一覧
• 「状態」- 現在の利用状況

お困りの際は、いつでもお声かけください！"""

def get_not_registered_message():
    """未登録ユーザーメッセージ"""
    return """⚠️ ご登録情報が見つかりません

AIコレクションズをご利用いただくには、先にLPからご登録が必要です。

🌐 登録はこちらから：
https://lp-production-xxxx.up.railway.app

ご登録後、再度お声かけください！"""

def get_default_message():
    """デフォルトメッセージ"""
    return """💬 何かお手伝いできることはありますか？

📋 利用可能なコマンド：
• 「追加」- コンテンツを追加
• 「メニュー」- メニューを表示
• 「状態」- 利用状況を確認
• 「ヘルプ」- ヘルプを表示

お気軽にお声かけください！"""

def handle_add_content(reply_token, user_id_db, stripe_subscription_id):
    """コンテンツ追加処理"""
    try:
        print(f"コンテンツ追加処理開始: subscription_id={stripe_subscription_id}, usage_price_id={USAGE_PRICE_ID}")
        
        # Stripeからsubscription_item_id取得
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        print(f"サブスクリプション詳細: {subscription}")
        
        usage_item = None
        for item in subscription['items']['data']:
            print(f"アイテム確認: price_id={item['price']['id']}, usage_price_id={USAGE_PRICE_ID}")
            if item['price']['id'] == USAGE_PRICE_ID:
                usage_item = item
                print(f"従量課金アイテム発見: {item}")
                break
        
        if not usage_item:
            print(f"従量課金アイテムが見つかりません: usage_price_id={USAGE_PRICE_ID}")
            print(f"利用可能なアイテム: {[item['price']['id'] for item in subscription['items']['data']]}")
            send_line_message(reply_token, f"❌ 従量課金アイテムが見つかりません。\n\n設定されている価格ID: {USAGE_PRICE_ID}\n\nサポートにお問い合わせください。")
            return
        
        subscription_item_id = usage_item['id']
        
        # Usage Record作成
        usage_record = stripe.UsageRecord.create(
            subscription_item=subscription_item_id,
            quantity=1,
            timestamp=int(__import__('time').time()),
            action='increment',
        )
        
        # DBに記録
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('INSERT INTO usage_logs (user_id, usage_quantity, stripe_usage_record_id) VALUES (?, ?, ?)',
                  (user_id_db, 1, usage_record.id))
        conn.commit()
        conn.close()
        
        # 成功メッセージ
        success_message = """✅ コンテンツ追加を受け付けました！

📊 追加内容：
• AI秘書機能 1件追加

💰 料金：
• 追加料金：1,500円（次回請求時に反映）

何か他にお手伝いできることはありますか？"""
        
        send_line_message(reply_token, success_message)
        
    except Exception as e:
        print(f'コンテンツ追加エラー: {e}')
        send_line_message(reply_token, "❌ エラーが発生しました。しばらく時間をおいて再度お試しください。")

def handle_status_check(reply_token, user_id_db):
    """利用状況確認"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM usage_logs WHERE user_id = ?', (user_id_db,))
        usage_count = c.fetchone()[0]
        conn.close()
        
        status_message = f"""📊 利用状況

📈 今月の追加回数：{usage_count}回
💰 追加料金：{usage_count * 1500}円

💡 ヒント：
• 「追加」でコンテンツを追加
• 「メニュー」で機能一覧を確認"""
        
        send_line_message(reply_token, status_message)
        
    except Exception as e:
        print(f'利用状況確認エラー: {e}')
        send_line_message(reply_token, "❌ 利用状況の取得に失敗しました。しばらく時間をおいて再度お試しください。")

if __name__ == '__main__':
    app.run(debug=True)
