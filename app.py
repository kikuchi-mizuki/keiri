import os
import json
import logging
from datetime import datetime
from flask import Flask, request, abort, redirect, url_for, send_file, after_this_request
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient, ReplyMessageRequest, PushMessageRequest, TextMessage, TemplateMessage, ButtonsTemplate, PostbackAction, QuickReply, QuickReplyItem, MessageAction, ApiException, ErrorResponse, FlexMessage
)
from linebot.v3.webhooks.models import MessageEvent, PostbackEvent
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from dotenv import load_dotenv
import traceback
import tempfile
import re

from services.session_manager import SessionManager
from services.google_sheets_service import GoogleSheetsService
from services.document_generator import DocumentGenerator
from services.auth_service import AuthService
from services.pdf_generator import PDFGenerator

# 環境変数の読み込み
load_dotenv()

# Google OAuth認証情報の設定
# 環境変数からJSON文字列を取得してファイルとして保存
client_secrets_env = os.getenv('GOOGLE_CLIENT_SECRETS_JSON')
if client_secrets_env:
    try:
        # JSON文字列をファイルとして保存
        with open('client_secrets.json', 'w') as f:
            f.write(client_secrets_env)
        print("[DEBUG] client_secrets.json created from environment variable")
    except Exception as e:
        print(f"[ERROR] Failed to create client_secrets.json: {e}")

app = Flask(__name__)

# LINE Bot設定
configuration = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# MessagingApiの初期化はwith ApiClientで行う
with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)

# サービスの初期化
session_manager = SessionManager()
google_sheets_service = GoogleSheetsService()
document_generator = DocumentGenerator()
auth_service = AuthService()
pdf_generator = PDFGenerator()

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/callback", methods=['POST'])
def callback():
    """LINE Webhookからのコールバック処理"""
    print("[DEBUG] callback: 関数開始")
    try:
        print("[DEBUG] callback: signature取得前")
        signature = request.headers.get('X-Line-Signature')
        print(f"[DEBUG] callback: signature取得後: {signature}")
    except Exception as e:
        print(f"[ERROR] callback: signature取得で例外: {e}")
        import traceback
        traceback.print_exc()
        abort(400)
    
    try:
        print("[DEBUG] callback: body取得前")
        body = request.get_data(as_text=True)
        print(f"[DEBUG] callback: body取得後: {body[:100]}...")  # 最初の100文字のみ表示
    except Exception as e:
        print(f"[ERROR] callback: body取得で例外: {e}")
        import traceback
        traceback.print_exc()
        abort(400)
    
    print("=== LINE CALLBACK ===")
    print("Signature:", signature)
    print("Body:", body)
    
    try:
        print("[DEBUG] callback: handler.handle呼び出し前")
        handler.handle(body, signature)
        print("[DEBUG] callback: handler.handle呼び出し後")
    except InvalidSignatureError:
        print("InvalidSignatureError!")
        import traceback
        traceback.print_exc()
        abort(400)
    except Exception as e:
        print("Exception in handler.handle:", e)
        import traceback
        traceback.print_exc()
        abort(400)
    
    print("[DEBUG] callback: OK返却前")
    return 'OK'

@app.route("/auth/callback")
def auth_callback():
    """Google OAuth認証コールバック"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')  # ユーザーID
        print(f"[DEBUG] auth_callback: state={state}, code={code[:20] if code else 'None'}...")
        
        if auth_service.handle_callback(code, state):
            print(f"[DEBUG] auth_callback: 認証成功 user_id={state}")
            # 認証完了後にLINEにプッシュメッセージでメインメニューを表示
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    buttons_template = TemplateMessage(
                        altText='メインメニュー',
                        template=ButtonsTemplate(
                            title='✅ 登録完了',
                            text='何をお手伝いしますか？',
                            actions=[
                                PostbackAction(label='見積書を作る', data='create_estimate'),
                                PostbackAction(label='請求書を作る', data='create_invoice'),
                                PostbackAction(label='会社情報を編集', data='edit_company_info')
                            ]
                        )
                    )
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=state,
                            messages=[buttons_template]
                        )
                    )
            except Exception as e:
                print(f"[WARNING] Failed to send push message: {e}")
                # プッシュメッセージ送信に失敗しても認証自体は成功しているので続行
            return "認証が完了しました。LINEに戻って続行してください。"
        else:
            print(f"[DEBUG] auth_callback: 認証失敗 user_id={state}")
            # 認証失敗時は失敗メッセージのみ送信（メインメニューは送らない）
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=state,
                            messages=[TextMessage(text="❌ Google認証に失敗しました。\n\n再度お試しください。")]
                        )
                    )
            except Exception as e:
                print(f"[WARNING] Failed to send push message: {e}")
            return "認証に失敗しました。再度お試しください。"
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        print(f"[DEBUG] auth_callback: 例外発生 {e}")
        
        # 例外発生時もプッシュメッセージで通知
        try:
            if state:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=state,
                            messages=[TextMessage(text="❌ 認証エラーが発生しました。\n\nしばらく時間をおいて再度お試しください。")]
                        )
                    )
        except Exception as push_error:
            print(f"[WARNING] Failed to send push message: {push_error}")
        
        return "認証エラーが発生しました。"

@handler.add(MessageEvent)
def handle_message(event):
    """テキストメッセージの処理"""
    print("[DEBUG] handle_message: 開始")
    user_id = event.source.user_id
    # v3ではevent.messageはTextMessageContent型
    text = event.message.text if hasattr(event.message, 'text') else ''

    # キャンセル対応
    if text.strip() == "キャンセル":
        session_manager.update_session(user_id, {'state': 'menu', 'step': None})
        show_main_menu(event)
        return

    logger.info(f"Received message from {user_id}: {text}")
    print(f"[DEBUG] handle_message: reply_token={event.reply_token}, event={event}")
    
    # セッション情報の取得
    session = session_manager.get_session(user_id)
    step = session.get('step') if session else None

    # 最終確認ステップの返答処理
    if step == 'confirm':
        if text.strip() == 'はい':
            session_manager.update_session(user_id, {'step': 'generate'})
            doc_type = session.get('document_type', 'estimate')
            doc_label = '見積書' if doc_type == 'estimate' else '請求書'
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"{doc_label}を作成中です…")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_message: 書類作成中メッセージ送信時に例外発生: {e}")
            generate_document(event, session)
            return
        elif text.strip() == '修正する':
            session_manager.update_session(user_id, {'step': 'items'})
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="品目の修正を行います。続けて品目を入力してください。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000\n\n完了したら「完了」と入力してください。")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_message: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
            return
    
    if not session:
        # 新規ユーザー - 初期登録フロー開始
        session_manager.create_session(user_id, {'state': 'registration', 'step': 'company_name'})
        try:
            print(f"[DEBUG] handle_message: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="👩‍💼LINE見積書・請求書Botへようこそ！\n\nまずは会社情報を登録しましょう。\n会社名（法人・屋号含む）を教えてください。")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_message: reply_message送信時に例外発生: {e}")
        return
    
    # 既存ユーザーの処理
    handle_existing_user(event, session, text)

@handler.add(PostbackEvent)
def handle_postback(event):
    """Postbackイベントの処理"""
    user_id = event.source.user_id
    data = event.postback.data
    
    logger.info(f"Received postback from {user_id}: {data}")
    
    if data == 'create_estimate':
        session_manager.update_session(user_id, {
            'state': 'document_creation',
            'document_type': 'estimate',
            'step': 'company_name'
        })
        show_document_creation_menu(event, 'estimate')
    
    elif data == 'create_invoice':
        session_manager.update_session(user_id, {
            'state': 'document_creation',
            'document_type': 'invoice',
            'step': 'company_name'
        })
        show_document_creation_menu(event, 'invoice')
    
    elif data == 'edit_company_info':
        session_manager.update_session(user_id, {
            'state': 'registration',
            'step': 'company_name'
        })
        try:
            print(f"[DEBUG] handle_postback: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="会社情報の編集を開始します。\n\n会社名を教えてください。")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_postback: reply_message送信時に例外発生: {e}")
    
    elif data == 'confirm_generate':
        session = session_manager.get_session(user_id)
        session_manager.update_session(user_id, {'step': 'generate'})
        # 進行中メッセージをreplyで送信
        doc_type = session.get('document_type', 'estimate')
        doc_label = '見積書' if doc_type == 'estimate' else '請求書'
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"{doc_label}を作成中です…")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_postback: 書類作成中メッセージ送信時に例外発生: {e}")
        generate_document(event, session)
        return
    elif data == 'edit_items':
        session = session_manager.get_session(user_id)
        session_manager.update_session(user_id, {'step': 'items'})
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="品目の修正を行います。続けて品目を入力してください。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000\n\n完了したら「完了」と入力してください。")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_postback: reply_message送信時に例外発生: {e}")
            import traceback
            traceback.print_exc()
        return
    
    else:
        show_main_menu(event)

def handle_existing_user(event, session, text):
    """既存ユーザーのメッセージ処理"""
    user_id = event.source.user_id
    state = session.get('state', 'menu')
    
    if state == 'registration':
        handle_registration(event, session, text)
    elif state == 'menu':
        handle_menu(event, session, text)
    elif state == 'document_creation':
        handle_document_creation(event, session, text)
    else:
        # 不明な状態の場合はメニューに戻す
        session_manager.update_session(user_id, {'state': 'menu'})
        show_main_menu(event)

def handle_registration(event, session, text):
    """初期登録フローの処理"""
    print("[DEBUG] handle_registration: 開始")
    user_id = event.source.user_id
    step = session.get('step')
    
    if step == 'company_name':
        session_manager.update_session(user_id, {
            'company_name': text,
            'step': 'address'
        })
        try:
            print(f"[DEBUG] handle_registration: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"✅ 会社名を「{text}」に設定しました。\n\n次に住所を入力してください。\n例：東京都千代田区丸の内1-1-1")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_registration: reply_message送信時に例外発生: {e}")
    
    elif step == 'address':
        session_manager.update_session(user_id, {
            'address': text,
            'step': 'bank_account'
        })
        try:
            print(f"[DEBUG] handle_registration: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"✅ 住所を「{text}」に設定しました。\n\n次に振込先銀行口座を教えてください。\n（例：○○銀行 ○○支店 普通 1234567）")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_registration: reply_message送信時に例外発生: {e}")
    
    elif step == 'bank_account':
        session_manager.update_session(user_id, {
            'bank_account': text,
            'step': 'google_auth'
        })
        auth_url = auth_service.get_auth_url(user_id)
        print(f"[DEBUG] handle_registration: auth_url={auth_url}")
        try:
            print(f"[DEBUG] handle_registration: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                if auth_url:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="✅ 銀行口座を登録しました。\n\n最後にGoogle認証を行います。\n以下のリンクからGoogle Driveへのアクセスを許可してください：\n\n" + auth_url)]
                        )
                    )
                else:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="✅ 銀行口座を登録しました。\n\nGoogle認証URLの生成に失敗しました。")]
                        )
                    )
        except Exception as e:
            print(f"[ERROR] handle_registration: reply_message送信時に例外発生: {e}")
    
    elif step == 'google_auth':
        # Google認証の確認
        print(f"[DEBUG] handle_registration: user_id={user_id}")
        print(f"[DEBUG] handle_registration: is_authenticated={auth_service.is_authenticated(user_id)}")
        if auth_service.is_authenticated(user_id):
            print(f"[DEBUG] handle_registration: 認証完了。登録処理を続行。")
            # ユーザー情報を永続化
            user_info = {
                'company_name': session.get('company_name'),
                'address': session.get('address'),
                'bank_account': session.get('bank_account')
            }
            session_manager.save_user_info(user_id, user_info)

            # Google認証トークンが本当に存在する場合のみregistration_completeを付与
            if auth_service.is_authenticated(user_id):
                session_manager.update_session(user_id, {
                    'state': 'menu',
                    'registration_complete': True,
                    'step': None,
                    'items': [],
                    'notes': '',
                    'email': ''
                })
                # 登録完了メッセージとメインメニューを一緒に送信
                buttons_template = TemplateMessage(
                    altText='メインメニュー',
                    template=ButtonsTemplate(
                        title='✅ 登録完了',
                        text='何をお手伝いしますか？',
                        actions=[
                            PostbackAction(label='見積書を作る', data='create_estimate'),
                            PostbackAction(label='請求書を作る', data='create_invoice'),
                            PostbackAction(label='会社情報を編集', data='edit_company_info')
                        ]
                    )
                )
                try:
                    print(f"[DEBUG] handle_registration: reply_token={event.reply_token}, event={event}")
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[buttons_template]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_registration: reply_message送信時に例外発生: {e}")
            else:
                print(f"[ERROR] handle_registration: Google認証トークンが見つかりません。registration_completeを付与しません。")
                try:
                    print(f"[DEBUG] handle_registration: reply_token={event.reply_token}, event={event}")
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="❌ Google認証トークンが見つかりません。再度認証をお試しください。")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_registration: reply_message送信時に例外発生: {e}")
        else:
            print(f"[DEBUG] handle_registration: 認証未完了 user_id={user_id}")
            auth_url = auth_service.get_auth_url(user_id)
            print(f"[DEBUG] handle_registration: auth_url={auth_url}")
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    if auth_url:
                        print(f"[DEBUG] handle_registration: 認証URL送信前 reply_token={event.reply_token}, event={event}")
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="🔐 Google認証が完了していません。\n\n以下のリンクから認証を完了してください：\n\n" + auth_url)]
                            )
                        )
                        print(f"[DEBUG] handle_registration: 認証URL送信完了")
                    else:
                        print(f"[DEBUG] handle_registration: 認証URL生成失敗 reply_token={event.reply_token}, event={event}")
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="❌ Google認証URLの生成に失敗しました。")]
                            )
                        )
            except Exception as e:
                print(f"[ERROR] handle_registration: 認証URL送信時に例外発生: {e}")
            import traceback
            traceback.print_exc()

def handle_menu(event, session, text):
    """メインメニューの処理"""
    print("[DEBUG] handle_menu: 開始")
    if text == "見積書を作る":
        session_manager.update_session(event.source.user_id, {
            'state': 'document_creation',
            'document_type': 'estimate',
            'step': 'company_name'
        })
        show_document_creation_menu(event, 'estimate')
    
    elif text == "請求書を作る":
        session_manager.update_session(event.source.user_id, {
            'state': 'document_creation',
            'document_type': 'invoice',
            'step': 'company_name'
        })
        show_document_creation_menu(event, 'invoice')
    
    elif text == "会社情報を編集":
        session_manager.update_session(event.source.user_id, {
            'state': 'registration',
            'step': 'company_name'
        })
        try:
            print(f"[DEBUG] handle_menu: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="会社情報の編集を開始します。\n\n会社名を教えてください。")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_menu: reply_message送信時に例外発生: {e}")
    
    else:
        show_main_menu(event)

def show_main_menu(event):
    """メインメニューの表示"""
    print("[DEBUG] show_main_menu: 開始")
    buttons_template = TemplateMessage(
        altText='メインメニュー',
        template=ButtonsTemplate(
            title='LINE見積書・請求書Bot',
            text='何をお手伝いしますか？',
            actions=[
                PostbackAction(label='見積書を作る', data='create_estimate'),
                PostbackAction(label='請求書を作る', data='create_invoice'),
                PostbackAction(label='会社情報を編集', data='edit_company_info')
            ]
        )
    )
    
    try:
        print(f"[DEBUG] show_main_menu: reply_token={event.reply_token}, event={event}")
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[buttons_template]
                )
            )
    except Exception as e:
        print(f"[ERROR] show_main_menu: reply_message送信時に例外発生: {e}")

def show_document_creation_menu(event, doc_type):
    """書類作成メニューの表示"""
    print("[DEBUG] show_document_creation_menu: 開始")
    doc_name = "見積書" if doc_type == 'estimate' else "請求書"
    user_id = event.source.user_id
    session = session_manager.get_session(user_id)
    print(f"[DEBUG] show_document_creation_menu: user_id={user_id}, session={session}")

    if doc_type == 'estimate':
        # 見積書の場合は宛名から開始
        session_manager.update_session(user_id, {
            'state': 'document_creation',
            'document_type': doc_type,
            'step': 'client_name',
            'items': []
        })
        try:
            print(f"[DEBUG] show_document_creation_menu: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"📄{doc_name}の作成を開始します。\n\n宛名（クライアント名）を入力してください。\n例：株式会社○○ ○○様")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] show_document_creation_menu: reply_message送信時に例外発生: {e}")
    else:
        # 請求書の場合はシート選択から開始
        credentials = auth_service.get_credentials(user_id)
        invoice_sheets = google_sheets_service.list_invoice_sheets(credentials, max_results=5)
        if invoice_sheets:
            quick_reply_items = [
                QuickReplyItem(
                    action=MessageAction(
                        label=sheet['name'][:19] + '…' if len(sheet['name']) > 20 else sheet['name'],
                        text=f"シート選択:{sheet['id']}"
                    )
                )
                for sheet in invoice_sheets
            ]
            quick_reply = QuickReply(items=quick_reply_items)
            try:
                print(f"[DEBUG] show_document_creation_menu: reply_token={event.reply_token}, event={event}")
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    text_message = TextMessage(
                        text=f"{doc_name}の作成を開始します。\n\n使用する請求書シートを選択してください。",
                        quick_reply=quick_reply
                    )
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[text_message]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] show_document_creation_menu: reply_message送信時に例外発生: {e}")
            session_manager.update_session(user_id, {
                'state': 'document_creation',
                'document_type': doc_type,
                'step': 'select_invoice_sheet',
                'items': []
            })
        else:
            try:
                print(f"[DEBUG] show_document_creation_menu: reply_token={event.reply_token}, event={event}")
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"📄{doc_name}の作成を開始します。\n\n宛名（クライアント名）を入力してください。\n例：株式会社○○ ○○様")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] show_document_creation_menu: reply_message送信時に例外発生: {e}")
            session_manager.update_session(user_id, {
                'state': 'document_creation',
                'document_type': doc_type,
                'step': 'client_name',
                'items': []
            })

def handle_document_creation(event, session, text):
    print("[DEBUG] handle_document_creation: 開始")
    user_id = event.source.user_id
    # キャンセル対応
    if text.strip() == "キャンセル":
        session_manager.update_session(user_id, {'state': 'menu', 'step': None})
        show_main_menu(event)
        return
    step = session.get('step')
    doc_type = session.get('document_type')

    # build_rich_text_summaryを全体スコープで定義
    def build_rich_text_summary(session):
        company = session.get('company_name', '')
        client = session.get('client_name', '')
        items = session.get('items', [])
        total = sum(item['amount'] for item in items)
        due_date = session.get('due_date', '')
        item_lines = '\n'.join([
            f"・{item['name']}（{item['quantity']}個 × {item['price']:,}円 = {item['amount']:,}円）"
            for item in items
        ])
        summary = (
            "==========\n"
            + "【最終確認】\n"
            + "------------------------------\n"
            + f"■ 会社名\n{company}\n\n"
            + f"■ 宛名\n{client}\n\n"
            + f"■ 品目\n{item_lines if item_lines else '（なし）'}\n\n"
            + (f"■ 支払い期日\n{due_date}\n\n" if due_date else "")
            + "------------------------------\n"
            + f"■ 合計金額\n{total:,}円\n"
            + "==========\n\n"
            + "この内容で書類を生成してよろしいですか？\n"
            + "（「はい」または「修正する」と入力してください）"
        )
        return summary

    # registration_completeがTrueでもトークンが無い場合は認証フローに戻す
    if session.get('registration_complete') and not auth_service.is_authenticated(user_id):
        print(f"[ERROR] registration_completeはTrueだがGoogle認証トークンが無い。認証フローに戻します。")
        session_manager.update_session(user_id, {
            'state': 'registration',
            'step': 'google_auth',
            'registration_complete': False
        })
        auth_url = auth_service.get_auth_url(user_id)
        if auth_url:
            print(f"[DEBUG] handle_document_creation: 認証URL送信前 reply_token={event.reply_token}, event={event}")
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="🔐 Google認証が失われています。再度認証を完了してください：\n\n" + auth_url)]
                        )
                    )
                print(f"[DEBUG] handle_document_creation: 認証URL送信完了")
            except Exception as e:
                print(f"[ERROR] handle_document_creation: 認証URL送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[DEBUG] handle_document_creation: 認証URL生成失敗 reply_token={event.reply_token}, event={event}")
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="❌ Google認証URLの生成に失敗しました。")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_document_creation: 認証URL生成失敗時の送信で例外発生: {e}")
                import traceback
                traceback.print_exc()
        return

    # 認証チェック
    if not auth_service.is_authenticated(user_id):
        print(f"[DEBUG] handle_document_creation: 認証未完了。Google認証にリダイレクト。user_id={user_id}")
        session_manager.update_session(user_id, {
            'state': 'registration',
            'step': 'google_auth'
        })
        auth_url = auth_service.get_auth_url(user_id)
        print(f"[DEBUG] handle_document_creation: auth_url={auth_url}")
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                if auth_url:
                    print(f"[DEBUG] handle_document_creation: 認証URL送信前 reply_token={event.reply_token}, event={event}")
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="🔐 Google認証が完了していません。\n\n以下のリンクから認証を完了してください：\n\n" + auth_url)]
                        )
                    )
                    print(f"[DEBUG] handle_document_creation: 認証URL送信完了")
                else:
                    print(f"[DEBUG] handle_document_creation: 認証URL生成失敗 reply_token={event.reply_token}, event={event}")
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="❌ Google認証URLの生成に失敗しました。")]
                        )
                    )
        except Exception as e:
            print(f"[ERROR] handle_document_creation: 認証URL送信時に例外発生: {e}")
            import traceback
            traceback.print_exc()
        return
    
    # 認証チェックが完了したら、以降のステップでは認証チェックを行わない
    print(f"[DEBUG] handle_document_creation: 認証チェック完了。ステップ処理を続行。")

    # 請求書シート選択ステップ
    if step == 'select_invoice_sheet' and text.startswith('シート選択:'):
        selected_sheet_id = text.replace('シート選択:', '').strip()
        session_manager.update_session(user_id, {
            'selected_invoice_sheet_id': selected_sheet_id,
            'step': 'company_name'
        })
        try:
            print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="会社名を入力してください。")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
            import traceback
            traceback.print_exc()
        return

    if step == 'company_name':
        if text == "はい":
            session_manager.update_session(user_id, {'step': 'client_name'})
            try:
                print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="次に宛名（クライアント名）を入力してください。\n例：株式会社○○ ○○様")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
        elif text == "編集する":
            session_manager.update_session(user_id, {'step': 'edit_company_name'})
            try:
                print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="新しい会社名を入力してください。")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
        else:
            # デフォルト処理：入力されたテキストを会社名として保存
            session_manager.update_session(user_id, {
                'company_name': text,
                'step': 'client_name'
            })
            try:
                print(f"[DEBUG] handle_document_creation: 会社名保存後 reply_token={event.reply_token}, event={event}")
                print(f"[DEBUG] handle_document_creation: ApiClient作成前")
                with ApiClient(configuration) as api_client:
                    print(f"[DEBUG] handle_document_creation: ApiClient作成後")
                    print(f"[DEBUG] handle_document_creation: MessagingApi作成前")
                    line_bot_api = MessagingApi(api_client)
                    print(f"[DEBUG] handle_document_creation: MessagingApi作成後")
                    print(f"[DEBUG] handle_document_creation: reply_message呼び出し前")
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"✅ 会社名を「{text}」に設定しました。\n\n次に宛名（クライアント名）を入力してください。\n例：株式会社○○ ○○様")]
                        )
                    )
                    print(f"[DEBUG] handle_document_creation: reply_message呼び出し後")
            except Exception as e:
                print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()

    elif step == 'client_name':
        session_manager.update_session(user_id, {
            'client_name': text,
            'step': 'items'
        })
        try:
            print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"✅ 宛名を「{text}」に設定しました。\n\n次に品目を入力してください。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000\n\n最大10件まで入力できます。")]
                    )
                )
        except Exception as e:
            print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
            import traceback
            traceback.print_exc()

    elif step == 'items':
        items = session.get('items', [])
        doc_type = session.get('document_type')
        
        # --- 確認フロー追加 ---
        def build_summary(session):
            company = session.get('company_name', '')
            client = session.get('client_name', '')
            items = session.get('items', [])
            total = sum(item['amount'] for item in items)
            item_lines = '\n'.join([f"・{item['name']}（{item['quantity']}個 × {item['price']}円 = {item['amount']}円）" for item in items])
            summary = f"【会社名】{company}\n【宛名】{client}\n【品目】\n{item_lines}\n【合計金額】{total:,}円"
            return summary
        
        if len(items) >= 10 or text == "完了":
            if not items:
                try:
                    print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="品目が入力されていません。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
                return
            # --- 修正ここから ---
            if doc_type == 'estimate':
                # 見積書は従来通り最終確認
                flex_json = build_rich_text_summary(session)
                try:
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=flex_json)]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
                session_manager.update_session(user_id, {'step': 'confirm'})
                return
            else:
                # 請求書は支払い期日を質問
                try:
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="✅ 品目の入力が完了しました。\n\n次に支払い期日を入力してください。\n形式：YYYY-MM-DD\n例：2024-01-31")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
                session_manager.update_session(user_id, {'step': 'due_date'})
                return
        # --- 修正ここまで ---
                
        if text == "完了":
            print(f"[DEBUG] 完了入力時 items={items}")
            if not items:
                try:
                    print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="品目が入力されていません。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
                return
                
            if doc_type == 'estimate':
                try:
                    print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="✅ 品目の入力が完了しました。\n\n書類の生成を開始します...")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
                session_manager.update_session(user_id, {'step': 'generate'})
                generate_document(event, session)
                return
            else:
                try:
                    print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="✅ 品目の入力が完了しました。\n\n次に支払い期日を入力してください。\n形式：YYYY-MM-DD\n例：2024-01-31")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
                session_manager.update_session(user_id, {'step': 'due_date'})
                return
                
        try:
            normalized_text = normalize_item_input(text)
            parts = normalized_text.split(',')
            if len(parts) == 3:
                item_name = parts[0].strip()
                quantity = kanji_num_to_int(parts[1].strip())
                price = kanji_num_to_int(parts[2].strip())
                items.append({
                    'name': item_name,
                    'price': price,
                    'quantity': quantity,
                    'amount': price * quantity
                })
                session_manager.update_session(user_id, {'items': items})
                total = sum(item['amount'] for item in items)
                response_text = f"✅ 品目を追加しました：{item_name}\n\n現在の品目数：{len(items)}/10\n合計金額：{total:,}円\n\n続けて品目を入力するか、「完了」と入力してください。"
                print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                try:
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=response_text)]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
                try:
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text="形式が正しくありません。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000")]
                            )
                        )
                except Exception as e:
                    print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                    import traceback
                    traceback.print_exc()
        except ValueError:
            print(f"[DEBUG] handle_document_creation: reply_token={event.reply_token}, event={event}")
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="数量と単価は数字で入力してください。\n\n形式：品目名,数量,単価\n例：Webサイト制作,1,100000")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
            import traceback
            traceback.print_exc()

    # 請求書の場合の追加ステップ
    elif step == 'due_date':
        try:
            due_date = datetime.strptime(text, '%Y-%m-%d')
            session_manager.update_session(user_id, {
                'due_date': text
            })
            # --- ここから修正 ---
            # 支払い期日入力後、最終確認メッセージを表示
            flex_json = build_rich_text_summary(session_manager.get_session(user_id))
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=flex_json)]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
            session_manager.update_session(user_id, {'step': 'confirm'})
            return
            # --- ここまで修正 ---
        except ValueError:
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="日付の形式が正しくありません。\n\n形式：YYYY-MM-DD\n例：2024-01-31")]
                        )
                    )
            except Exception as e:
                print(f"[ERROR] handle_document_creation: reply_message送信時に例外発生: {e}")
                import traceback
                traceback.print_exc()
        return

    # 以降のnotes, email, phone, representative, business_numberのステップはスキップ（請求書の場合）

def generate_document(event, session):
    """書類の生成と送信"""
    print("[DEBUG] generate_document: 開始")
    user_id = event.source.user_id
    doc_type = session.get('document_type')
    try:
        print(f"[DEBUG] generate_document: user_id={user_id}, doc_type={doc_type}")
        print(f"[DEBUG] generate_document: session={session}")
        print(f"[DEBUG] generate_document: reply_token={event.reply_token}, event={event}")
        session['user_id'] = user_id
        print(f"[DEBUG] generate_document: session={session}")
        
        # Google SheetsとPDFの両方を生成
        sheet_url, pdf_path, pdf_file_id = document_generator.create_document_with_pdf(session)
        print(f"[DEBUG] generate_document: sheet_url={sheet_url}")
        print(f"[DEBUG] generate_document: pdf_path={pdf_path}")
        print(f"[DEBUG] generate_document: pdf_file_id={pdf_file_id}")
        
        # 編集リンクとPDFダウンロードリンクを1つのメッセージにまとめて送信
        import os
        pdf_filename = os.path.basename(pdf_path) if pdf_path else None
        server_url = os.getenv("SERVER_URL", "http://192.168.0.207:5001")
        
        # 編集されたシートのみのPDFダウンロードリンク
        doc_type = session.get('document_type')
        if doc_type == 'estimate':
            spreadsheet_id = session_manager.get_estimate_spreadsheet_id(user_id)
        else:
            spreadsheet_id = session_manager.get_invoice_spreadsheet_id(user_id)
        edited_sheets_pdf_url = f"{server_url}/download/edited-sheets/{spreadsheet_id}.pdf?user_id={user_id}" if spreadsheet_id else "(編集シートPDFリンク取得失敗)"
        
        # 最新の編集済みシートを直接開くリンク（gidも取得して正確なURLにする）
        latest_sheet_name = document_generator.get_latest_edited_sheet_name(spreadsheet_id, user_id) if spreadsheet_id else None
        sheet_url_with_tab = sheet_url
        if latest_sheet_name:
            # gid取得
            try:
                credentials = auth_service.get_credentials(user_id)
                service = google_sheets_service._get_service(credentials)
                spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                gid = None
                for sheet in spreadsheet['sheets']:
                    if sheet['properties']['title'] == latest_sheet_name:
                        gid = sheet['properties']['sheetId']
                        break
                import urllib.parse
                encoded_sheet_name = urllib.parse.quote(latest_sheet_name)
                if gid is not None:
                    sheet_url_with_tab = f"{sheet_url}#gid={gid}&range={encoded_sheet_name}!A1"
                else:
                    sheet_url_with_tab = f"{sheet_url}#range={encoded_sheet_name}!A1"
            except Exception as e:
                print(f"[WARNING] 最新シートgid取得失敗: {e}")
                import urllib.parse
                encoded_sheet_name = urllib.parse.quote(latest_sheet_name)
                sheet_url_with_tab = f"{sheet_url}#range={encoded_sheet_name}!A1"
        
        # メッセージテキスト生成（全体PDFダウンロードは削除）
        message_text = f"✅ {'見積書' if doc_type == 'estimate' else '請求書'}を作成しました！\n\n📝 編集リンク：\n{sheet_url_with_tab}\n\n📄 PDFダウンロード：\n{edited_sheets_pdf_url}"
        try:
            print(f"[DEBUG] generate_document: reply_token={event.reply_token}, event={event}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text=message_text)]
                    )
                )
        except Exception as e:
            print(f"[ERROR] generate_document: reply_message送信時に例外発生: {e}")
        
        # PDFファイルの一時ファイル削除
        # if pdf_path and os.path.exists(pdf_path):
        #     try:
        #         os.remove(pdf_path)
        #         print(f"[DEBUG] generate_document: PDFファイル削除完了: {pdf_path}")
        #     except Exception as e:
        #         print(f"[WARNING] generate_document: PDFファイル削除失敗: {e}")
        # else:
        #     print(f"[WARNING] generate_document: PDFファイルが見つかりません: {pdf_path}")
        
        session_manager.update_session(user_id, {'state': 'menu'})
    except Exception as e:
        print(f"[ERROR] generate_document: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"Document generation error: {e}")
        try:
            print(f"[DEBUG] generate_document: push_message error fallback user_id={user_id}")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="❌ 書類の作成中にエラーが発生しました。\n\nしばらく時間をおいて再度お試しください。")]
                    )
                )
        except Exception as push_e:
            print(f"[ERROR] generate_document: push_message送信時に例外発生: {push_e}")

def normalize_item_input(text):
    # 全角カンマ→半角カンマ
    text = text.replace('、', ',')
    # 全角数字→半角数字
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    # 全角スペース→半角スペース
    text = text.replace('　', ' ')
    # 区切り文字（カンマ、スペース、タブ）をカンマに統一
    text = re.sub(r'[\s,]+', ',', text.strip())
    return text

def kanji_num_to_int(s):
    s = s.strip()
    # 万・千の単位を数値化
    if s.endswith('万'):
        try:
            return int(float(s[:-1]) * 10000)
        except ValueError:
            pass
    if s.endswith('千'):
        try:
            return int(float(s[:-1]) * 1000)
        except ValueError:
            pass
    # カンマ区切りや全角数字も考慮
    s = s.replace(',', '')
    try:
        return int(s)
    except ValueError:
        return s

@app.route('/download/pdf/<filename>')
def download_pdf(filename):
    """PDFファイルを一時的に配信するエンドポイント"""
    import os
    pdf_path = os.path.join(os.getcwd(), filename)
    if not os.path.exists(pdf_path):
        return 'ファイルが見つかりません', 404

    @after_this_request
    def remove_file(response):
        try:
            os.remove(pdf_path)
        except Exception as e:
            print(f"[WARNING] PDFファイル削除失敗: {e}")
        return response

    return send_file(pdf_path, as_attachment=True, mimetype='application/pdf', download_name=filename)

@app.route('/download/edited-sheets/<spreadsheet_id>.pdf')
def download_edited_sheets_pdf(spreadsheet_id):
    """編集されたシートのみのPDFをダウンロード"""
    import os
    import tempfile
    
    # Google認証情報を取得
    user_id = request.args.get('user_id')
    if not user_id:
        return 'user_idが必要です', 400
    
    auth_service = AuthService()
    credentials = auth_service.get_credentials(user_id)
    if not credentials:
        return 'Google認証が必要です', 401

    try:
        # 編集されたシートのみのPDFを生成
        result = pdf_generator.create_edited_sheets_pdf(
            google_sheets_service, credentials, spreadsheet_id
        )
        
        if not result:
            return '編集されたシートが見つかりません', 404

        @after_this_request
        def remove_file(response):
            try:
                os.remove(result)
            except Exception as e:
                print(f"[WARNING] PDFファイル削除失敗: {e}")
            return response

        return send_file(result, as_attachment=True, mimetype='application/pdf', download_name=f'edited_sheets_{spreadsheet_id}.pdf')
        
    except Exception as e:
        logger.error(f"Edited sheets PDF download error: {e}")
        return 'PDF生成に失敗しました', 500

@app.route('/download/pdf/<spreadsheet_id>/<sheet_name>.pdf')
def download_pdf_sheet(spreadsheet_id, sheet_name):
    import os
    from services.google_sheets_service import GoogleSheetsService
    from services.auth_service import AuthService
    import requests

    # Google認証情報を取得
    user_id = request.args.get('user_id')
    if not user_id:
        return 'user_idが必要です', 400
    auth_service = AuthService()
    credentials = auth_service.get_credentials(user_id)
    if not credentials:
        return 'Google認証が必要です', 401

    # gid取得
    sheets_service = GoogleSheetsService()
    service = sheets_service._get_service(credentials)
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    gid = None
    for sheet in spreadsheet['sheets']:
        if sheet['properties']['title'] == sheet_name:
            gid = sheet['properties']['sheetId']
            break
    if gid is None:
        return '指定シートが見つかりません', 404

    # Google Sheets export URL組み立て
    export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=pdf&gid={gid}&single=true&portrait=true&size=A4&fitw=true&top_margin=0.5&bottom_margin=0.5&left_margin=0.5&right_margin=0.5"

    # 認証付きでPDF取得
    authed_session = requests.Session()
    authed_session.auth = credentials
    response = authed_session.get(export_url)
    if response.status_code != 200:
        return 'PDF取得に失敗しました', 500

    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    @after_this_request
    def remove_file(response):
        try:
            os.remove(tmp_path)
        except Exception as e:
            print(f"[WARNING] PDFファイル削除失敗: {e}")
        return response

    return send_file(tmp_path, as_attachment=True, mimetype='application/pdf', download_name=f'{sheet_name}.pdf')

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5001, use_reloader=False) 