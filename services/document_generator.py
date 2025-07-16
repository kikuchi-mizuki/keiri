import logging
from datetime import datetime
from .auth_service import AuthService
from .google_sheets_service import GoogleSheetsService
from .session_manager import SessionManager
from .pdf_generator import PDFGenerator
import traceback
import io
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

class DocumentGenerator:
    """書類生成統合管理クラス"""
    
    def __init__(self):
        self.auth_service = AuthService()
        self.sheets_service = GoogleSheetsService()
        self.session_manager = SessionManager()
        self.pdf_generator = PDFGenerator()
    
    def create_document(self, session_data):
        """書類を作成してリンクを返す"""
        try:
            user_id = session_data.get('user_id')
            document_type = session_data.get('document_type', 'invoice')
            print(f"[DEBUG] create_document: user_id={user_id}, document_type={document_type}")
            print(f"[DEBUG] create_document: is_authenticated={self.auth_service.is_authenticated(user_id)}")
            credentials = self.auth_service.get_credentials(user_id)
            print(f"[DEBUG] create_document: credentials={credentials}")
            if not credentials:
                raise Exception("Google認証が必要です")
            spreadsheet_id = self.sheets_service.copy_template(
                credentials, user_id, document_type
            )
            print(f"[DEBUG] create_document: spreadsheet_id={spreadsheet_id}")
            document_data = self._prepare_document_data(session_data)
            print(f"[DEBUG] create_document: document_data={document_data}")
            self.sheets_service.update_values(credentials, spreadsheet_id, document_data)
            # フォーマットは一時的に無効化（エラー回避のため）
            # self.sheets_service.format_document(credentials, spreadsheet_id, document_type)
            shareable_link = self.sheets_service.get_shareable_link(credentials, spreadsheet_id)
            print(f"[DEBUG] create_document: shareable_link={shareable_link}")
            logger.info(f"Document created successfully: {spreadsheet_id}")
            return shareable_link
        except Exception as e:
            print(f"[ERROR] create_document: {e}")
            traceback.print_exc()
            logger.error(f"Document creation error: {e}")
            raise

    def upload_pdf_to_drive(self, credentials, pdf_path, user_id):
        """PDFファイルをGoogle Driveにアップロードし、ファイルIDを返す"""
        from googleapiclient.discovery import build
        drive_service = build('drive', 'v3', credentials=credentials)
        file_metadata = {
            'name': f'invoice_{user_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
            'mimeType': 'application/pdf',
            'parents': ['root']
        }
        media = MediaFileUpload(pdf_path, mimetype='application/pdf')
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        # 公開権限を付与
        drive_service.permissions().create(
            fileId=uploaded['id'],
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        return uploaded['id']

    def create_document_with_pdf(self, session_data):
        """書類を作成してリンクとPDFファイルパス・DriveファイルIDを返す"""
        try:
            user_id = session_data.get('user_id')
            document_type = session_data.get('document_type', 'invoice')
            creation_method = session_data.get('creation_method', 'new_sheet')
            selected_spreadsheet_id = session_data.get('selected_spreadsheet_id')
            
            print(f"[DEBUG] create_document_with_pdf: user_id={user_id}, document_type={document_type}, creation_method={creation_method}")
            credentials = self.auth_service.get_credentials(user_id)
            if not credentials:
                raise Exception("Google認証が必要です")

            # 作成方法に応じてスプレッドシートIDを決定
            if creation_method == 'existing_sheet' and selected_spreadsheet_id:
                # 既存シートに追加
                spreadsheet_id = selected_spreadsheet_id
                is_first = False
                print(f"[DEBUG] create_document_with_pdf: 既存シート使用 spreadsheet_id={spreadsheet_id}")
            else:
                # 新規作成または既存シートIDが指定されていない場合
                if document_type == 'estimate':
                    spreadsheet_id = self.session_manager.get_estimate_spreadsheet_id(user_id)
                else:
                    spreadsheet_id = self.session_manager.get_invoice_spreadsheet_id(user_id)
                
                is_first = False
                if not spreadsheet_id:
                    # 1回目：テンプレートから新規作成
                    spreadsheet_id = self.sheets_service.copy_template(
                        credentials, user_id, document_type
                    )
                    # 不要なタブを削除
                    if document_type == 'estimate':
                        self.sheets_service.delete_sheet_by_name(credentials, spreadsheet_id, '請求書')
                    elif document_type == 'invoice':
                        self.sheets_service.delete_sheet_by_name(credentials, spreadsheet_id, '見積書')
                    # document_typeに応じて適切なスプレッドシートIDを保存
                    if document_type == 'estimate':
                        self.session_manager.save_estimate_spreadsheet_id(user_id, spreadsheet_id)
                    else:
                        self.session_manager.save_invoice_spreadsheet_id(user_id, spreadsheet_id)
                    is_first = True
                    print(f"[DEBUG] create_document_with_pdf: 新規spreadsheet_id={spreadsheet_id}")
                else:
                    print(f"[DEBUG] create_document_with_pdf: 既存spreadsheet_id={spreadsheet_id}")

            # シート名決定
            if is_first:
                sheet_name = "見積書" if document_type == 'estimate' else "請求書"
                template_sheet_name = sheet_name
            else:
                # 2回目以降：新しいシート名を自動決定し、テンプレート内容をGASで完全コピー
                base_name = "見積書" if document_type == 'estimate' else "請求書"
                sheet_name = self.sheets_service.get_next_estimate_sheet_name(credentials, spreadsheet_id, base_name=base_name)
                template_sheet_name = base_name
                self.sheets_service.duplicate_sheet_via_gas(spreadsheet_id, template_sheet_name, sheet_name)

            # データを準備して更新
            document_data = self._prepare_document_data(session_data)
            print(f"[DEBUG] create_document_with_pdf: document_data={document_data}")
            self.sheets_service.update_values(credentials, spreadsheet_id, {**document_data, 'document_type': document_type}, sheet_name=sheet_name)

            # 共有リンクを取得
            shareable_link = self.sheets_service.get_shareable_link(credentials, spreadsheet_id)
            print(f"[DEBUG] create_document_with_pdf: shareable_link={shareable_link}")
            # PDFをエクスポート
            pdf_filename = self.sheets_service.export_to_pdf(credentials, spreadsheet_id, sheet_name=sheet_name)
            print(f"[DEBUG] create_document_with_pdf: pdf_filename={pdf_filename}")
            # PDFをGoogle Driveにアップロードし、ファイルIDを取得
            pdf_file_id = self.upload_pdf_to_drive(credentials, pdf_filename, user_id)
            print(f"[DEBUG] create_document_with_pdf: pdf_file_id={pdf_file_id}")
            logger.info(f"Document with PDF created successfully: {spreadsheet_id}, {pdf_filename}, {pdf_file_id}")
            return shareable_link, pdf_filename, pdf_file_id
        except Exception as e:
            print(f"[ERROR] create_document_with_pdf: {e}")
            traceback.print_exc()
            logger.error(f"Document with PDF creation error: {e}")
            raise
    
    def _prepare_document_data(self, session_data):
        """書類データを準備"""
        # ユーザー情報を取得
        user_id = session_data.get('user_id')
        user_info = self.session_manager.get_user_info(user_id) or {}
        
        # 品目の合計金額を計算
        items = session_data.get('items', [])
        total_amount = sum(item.get('amount', 0) for item in items)
        
        # 書類タイプを取得
        document_type = session_data.get('document_type', 'estimate')
        
        document_data = {
            'document_type': document_type,
            'issue_date': datetime.now().strftime('%Y-%m-%d'),
            'company_name': session_data.get('company_name', user_info.get('company_name', '')),
            'client_name': session_data.get('client_name', ''),
            'address': user_info.get('address', ''),
            'email': session_data.get('email', ''),
            'phone': session_data.get('phone', user_info.get('phone', '')),
            'fax': user_info.get('fax', ''),
            'website': user_info.get('website', ''),
            'representative': session_data.get('representative', user_info.get('representative', '')),
            'business_number': session_data.get('business_number', user_info.get('business_number', '')),
            'bank_account': user_info.get('bank_account', ''),
            'due_date': session_data.get('due_date', ''),
            'notes': session_data.get('notes', ''),
            'items': items,
            'total_amount': total_amount,
        }
        print(f"[DEBUG] _prepare_document_data: address={document_data['address']}, bank_account={document_data['bank_account']}")
        
        return document_data
    
    def create_pdf(self, session_data):
        """PDFファイルを作成"""
        try:
            user_id = session_data.get('user_id')
            document_type = session_data.get('document_type', 'invoice')
            
            # ユーザーの認証情報を取得
            credentials = self.auth_service.get_credentials(user_id)
            if not credentials:
                raise Exception("Google認証が必要です")
            
            # まずスプレッドシートを作成
            spreadsheet_id = self.sheets_service.copy_template(
                credentials, user_id, document_type
            )
            
            # データを準備して更新
            document_data = self._prepare_document_data(session_data)
            self.sheets_service.update_values(credentials, spreadsheet_id, document_data)
            # フォーマットは一時的に無効化（エラー回避のため）
            # self.sheets_service.format_document(credentials, spreadsheet_id, document_type)
            
            # 書類タイプに応じてPDFを生成
            pdf_filename = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            if document_type == 'estimate':
                self.pdf_generator.create_estimate_pdf(document_data, pdf_filename)
            else:
                self.pdf_generator.create_invoice_pdf(document_data, pdf_filename)
            
            logger.info(f"PDF created successfully: {pdf_filename}")
            return pdf_filename
            
        except Exception as e:
            logger.error(f"PDF creation error: {e}")
            raise
    
    def update_existing_document(self, spreadsheet_id, session_data):
        """既存のドキュメントを更新"""
        try:
            user_id = session_data.get('user_id')
            
            # ユーザーの認証情報を取得
            credentials = self.auth_service.get_credentials(user_id)
            if not credentials:
                raise Exception("Google認証が必要です")
            
            # データを準備
            document_data = self._prepare_document_data(session_data)
            
            # スプレッドシートを更新
            self.sheets_service.update_values(credentials, spreadsheet_id, document_data)
            
            logger.info(f"Document updated successfully: {spreadsheet_id}")
            return True
            
        except Exception as e:
            logger.error(f"Document update error: {e}")
            raise
    
    def create_edited_sheets_pdf(self, spreadsheet_id, user_id):
        """編集されたシートのみのPDFを作成（リトライ機能付き）"""
        try:
            # ユーザーの認証情報を取得
            credentials = self.auth_service.get_credentials(user_id)
            if not credentials:
                raise Exception("Google認証が必要です")
            
            # 編集されたシートのみのPDFを生成（リトライ機能付き）
            result = self.pdf_generator.create_edited_sheets_pdf(
                self.sheets_service, credentials, spreadsheet_id, max_retries=3, retry_delay=5
            )
            
            if not result:
                logger.warning("No edited sheets found for PDF generation")
                return None
            
            logger.info(f"Edited sheets PDF created successfully: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Edited sheets PDF creation error: {e}")
            raise 

    def get_latest_edited_sheet_name(self, spreadsheet_id, user_id):
        """最新の編集済みシート名を取得"""
        try:
            # ユーザーの認証情報を取得
            credentials = self.auth_service.get_credentials(user_id)
            if not credentials:
                raise Exception("Google認証が必要です")
            
            # 最新の編集済みシート名を取得
            sheet_name = self.sheets_service.get_latest_edited_sheet_name(credentials, spreadsheet_id)
            
            return sheet_name
            
        except Exception as e:
            logger.error(f"Get latest edited sheet name error: {e}")
            return None 