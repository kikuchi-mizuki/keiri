import os
import logging
import time
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests
from google.auth.transport.requests import AuthorizedSession

GAS_URL = "https://script.google.com/macros/s/AKfycbwG8PGqL0L-LgPf-9c622OVDfj6gPgA2QW9q14K4xHheIltgdTyoqGS-UF08n8ukKf2Wg/exec"

logger = logging.getLogger(__name__)

class GoogleSheetsService:
    """Google Sheets API操作クラス"""
    
    def __init__(self):
        # テンプレートIDを自動設定
        self.template_spreadsheet_id = "1FK9MDpEoHCySVgz83yjmZWOuyjrTaCDjRBEEWzafqgE"
        self.invoice_spreadsheet_id = "1XpxU_4eOmdhZ_pXMaec8ribVw0_J0IhRNI0IzVTiM4Y"
        self.service = None
    
    def _get_service(self, credentials):
        """Google Sheets APIサービスを取得"""
        if not self.service:
            self.service = build('sheets', 'v4', credentials=credentials)
        return self.service
    
    def copy_template(self, credentials, user_id, document_type):
        """テンプレートをコピー"""
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            # テンプレートIDを切り替え
            if document_type == 'invoice':
                template_id = self.invoice_spreadsheet_id
            else:
                template_id = self.template_spreadsheet_id
            copy_metadata = {
                'name': f"{document_type}_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'parents': ['root']  # ユーザーのルートフォルダに保存
            }
            copied_file = drive_service.files().copy(
                fileId=template_id,
                body=copy_metadata
            ).execute()
            spreadsheet_id = copied_file['id']
            logger.info(f"Template copied: {spreadsheet_id}")
            return spreadsheet_id
        except HttpError as error:
            logger.error(f"Template copy error: {error}")
            raise
    
    def update_values(self, credentials, spreadsheet_id, data, sheet_name=None):
        """スプレッドシートに値を更新（セルごとに埋め込み）"""
        try:
            service = self._get_service(credentials)
            # シート名を自動で切り替え（指定がなければ）
            if not sheet_name:
                sheet_name = "見積書" if data.get('document_type') == 'estimate' else "請求書"
            
            # 基本情報のセルマッピング（見積書・請求書で異なる）
            if data.get('document_type') == 'estimate':
                # 見積書の場合
                basic_updates = [
                    ('E8', data.get('company_name', '')),  # 会社名
                    ('E10', data.get('address', '')),    # 住所
                    ('A7', data.get('client_name', '')),  # 宛名
                    ('A16', data.get('item_name', '')),  # 品名
                    ('D16', data.get('quantity', '')),  # 数量
                    ('E16', int(data.get('unit_price', 0)) if str(data.get('unit_price', '')).replace('.', '', 1).isdigit() else ''),  # 単価
                ]
            else:
                # 請求書の場合
                basic_updates = [
                    ('E8', data.get('company_name', '')),  # 会社名
                    ('E10', data.get('address', '')),    # 住所
                    ('A7', data.get('client_name', '')),  # 宛名
                    ('A16', data.get('transaction_date', '')),  # 取引日
                    ('B16', data.get('item_name', '')),  # 品名
                    ('E16', data.get('quantity', '')),  # 数量
                    ('F16', int(data.get('unit_price', 0)) if str(data.get('unit_price', '')).replace('.', '', 1).isdigit() else ''),  # 単価
                    ('G3', data.get('due_date', '')),  # 支払い期日
                    ('C34', data.get('bank_account', '')),  # 振込先
                ]
            
            # 基本情報を更新
            for cell, value in basic_updates:
                if value:  # 値がある場合のみ更新
                    service.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f'{sheet_name}!{cell}',
                        valueInputOption='RAW',
                        body={'values': [[value]]}
                    ).execute()
            
            # 品目テーブルの更新（見積書・請求書で異なる）
            items = data.get('items', [])
            if items:
                if data.get('document_type') == 'estimate':
                    # 見積書の場合：A16〜E27（最大12行）
                    max_items = 12
                    for i in range(max_items):
                        row = 16 + i
                        if i < len(items):
                            item = items[i]
                            # 品名
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f'{sheet_name}!A{row}',
                                valueInputOption='RAW',
                                body={'values': [[item.get('name', '')]]}
                            ).execute()
                            # 数量
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f'{sheet_name}!D{row}',
                                valueInputOption='RAW',
                                body={'values': [[item.get('quantity', '')]]}
                            ).execute()
                            # 単価
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f'{sheet_name}!E{row}',
                                valueInputOption='RAW',
                                body={'values': [[item.get('price', 0) if item.get('price', 0) not in ['', None] else '']]}
                            ).execute()
                            # B列・C列はテンプレートのフォーマットを保持（書き込みしない）
                        # データがない行もテンプレートのフォーマットを保持（書き込みしない）
                else:
                    # 請求書の場合：A16、B16、E16、F16
                    for i, item in enumerate(items):
                        row = 16 + i
                        # 取引日（発行日を使用）
                        service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f'{sheet_name}!A{row}',
                            valueInputOption='RAW',
                            body={'values': [[data.get('issue_date', '')]]}
                        ).execute()
                        # 品名
                        service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f'{sheet_name}!B{row}',
                            valueInputOption='RAW',
                            body={'values': [[item.get('name', '')]]}
                        ).execute()
                        # 数量
                        service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f'{sheet_name}!E{row}',
                            valueInputOption='RAW',
                            body={'values': [[item.get('quantity', '')]]}
                        ).execute()
                        # 単価
                        service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f'{sheet_name}!F{row}',
                            valueInputOption='RAW',
                            body={'values': [[item.get('price', 0)]]}
                        ).execute()
            
            # 合計金額の更新（見積書・請求書で異なる）
            # total_amount = data.get('total_amount', 0)
            # if total_amount:
            #     if data.get('document_type') == 'estimate':
            #         # 見積書の場合は合計金額を出力しない
            #         pass
            #     else:
            #         # 請求書の場合：合計金額の位置を調整
            #         total_row = 16 + len(items) + 1
            #         service.spreadsheets().values().update(
            #             spreadsheetId=spreadsheet_id,
            #             range=f'{sheet_name}!F{total_row}',
            #             valueInputOption='RAW',
            #             body={'values': [[f"¥{total_amount:,}"]]}
            #         ).execute()
            
            logger.info(f"Values updated successfully for {sheet_name}")
            return True
            
        except Exception as error:
            logger.error(f"Values update error: {error}")
            raise
    
    def get_sheet_id_by_name(self, service, spreadsheet_id, sheet_name):
        """シート名からシートIDを取得"""
        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            for sheet in spreadsheet['sheets']:
                if sheet['properties']['title'] == sheet_name:
                    return sheet['properties']['sheetId']
            raise Exception(f"シート名「{sheet_name}」が見つかりません")
        except Exception as error:
            logger.error(f"Sheet ID lookup error: {error}")
            raise

    def format_document(self, credentials, spreadsheet_id, document_type):
        """ドキュメントのフォーマットを適用"""
        try:
            service = self._get_service(credentials)
            
            # シート名を決定
            sheet_name = "見積書" if document_type == 'estimate' else "請求書"
            
            # シート名からシートIDを取得
            sheet_id = self.get_sheet_id_by_name(service, spreadsheet_id, sheet_name)
            
            # タイトル行のフォーマット
            title_format = {
                'requests': [
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': 1
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 0.2,
                                        'green': 0.6,
                                        'blue': 0.8
                                    },
                                    'textFormat': {
                                        'bold': True,
                                        'fontSize': 16
                                    },
                                    'horizontalAlignment': 'CENTER'
                                }
                            },
                            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
                        }
                    }
                ]
            }
            
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=title_format
            ).execute()
            
            logger.info(f"Document formatted: {sheet_name}")
            return True
            
        except HttpError as error:
            logger.error(f"Document formatting error: {error}")
            raise
    
    def get_shareable_link(self, credentials, spreadsheet_id):
        """共有可能なリンクを取得"""
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # ファイルの権限を設定（編集可能）
            permission = {
                'type': 'anyone',
                'role': 'writer'
            }
            
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body=permission
            ).execute()
            
            # 共有リンクを取得
            file_info = drive_service.files().get(
                fileId=spreadsheet_id,
                fields='webViewLink'
            ).execute()
            
            shareable_link = file_info.get('webViewLink')
            logger.info(f"Shareable link created: {shareable_link}")
            
            return shareable_link
            
        except HttpError as error:
            logger.error(f"Shareable link creation error: {error}")
            raise
    
    def export_to_pdf(self, credentials, spreadsheet_id, sheet_name=None):
        """PDFとしてエクスポート（フォールバック用）"""
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # 現在の制限により、特定のシートのみのエクスポートは困難
            # 一時的に全体をエクスポートして、後で改善を検討
            request = drive_service.files().export_media(
                fileId=spreadsheet_id,
                mimeType='application/pdf'
            )
            
            # PDFファイルを保存
            pdf_filename = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            with open(pdf_filename, 'wb') as f:
                f.write(request.execute())
            
            logger.info(f"PDF exported (fallback): {pdf_filename}")
            return pdf_filename
            
        except HttpError as error:
            logger.error(f"PDF export error: {error}")
            raise 

    def list_invoice_sheets(self, credentials, max_results=10):
        """Google Drive上の請求書スプレッドシート一覧を取得"""
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            query = "mimeType='application/vnd.google-apps.spreadsheet' and name contains '請求書' and trashed = false"
            results = drive_service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, createdTime)"
            ).execute()
            files = results.get('files', [])
            return files
        except Exception as e:
            logger.error(f"list_invoice_sheets error: {e}")
            return [] 

    def add_sheet_from_template(self, credentials, spreadsheet_id, template_sheet_name, new_sheet_name):
        """既存スプレッドシートにテンプレートシートの内容をコピーした新しいシートを追加"""
        service = self._get_service(credentials)
        # 1. テンプレートシートIDを取得
        template_sheet_id = self.get_sheet_id_by_name(service, spreadsheet_id, template_sheet_name)
        # 2. 新しいシートを追加
        add_sheet_request = {
            'requests': [
                {
                    'addSheet': {
                        'properties': {
                            'title': new_sheet_name
                        }
                    }
                }
            ]
        }
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=add_sheet_request
        ).execute()
        new_sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
        # 3. テンプレート内容（値・書式）を新シートにコピー
        # 値と書式をcopyPasteでコピー
        copy_paste_request = {
            'requests': [
                {
                    'copyPaste': {
                        'source': {
                            'sheetId': template_sheet_id
                        },
                        'destination': {
                            'sheetId': new_sheet_id
                        },
                        'pasteType': 'PASTE_NORMAL',
                        'pasteOrientation': 'NORMAL'
                    }
                },
                {
                    'copyPaste': {
                        'source': {
                            'sheetId': template_sheet_id
                        },
                        'destination': {
                            'sheetId': new_sheet_id
                        },
                        'pasteType': 'PASTE_FORMAT',
                        'pasteOrientation': 'NORMAL'
                    }
                }
            ]
        }
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=copy_paste_request
        ).execute()
        return new_sheet_name

    def duplicate_sheet_via_gas(self, spreadsheet_id, template_sheet_name, new_sheet_name):
        params = {
            "spreadsheetId": spreadsheet_id,
            "templateSheetName": template_sheet_name,
            "newSheetName": new_sheet_name
        }
        response = requests.get(GAS_URL, params=params)
        if response.text.strip() != "OK":
            raise Exception(f"GAS duplicate failed: {response.text}")
        return True

    def get_next_estimate_sheet_name(self, credentials, spreadsheet_id, base_name="見積書"):
        """既存の見積書シート名から次の番号のシート名を決定"""
        service = self._get_service(credentials)
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_names = [sheet['properties']['title'] for sheet in spreadsheet['sheets']]
        max_num = 1
        for name in sheet_names:
            if name == base_name:
                max_num = max(max_num, 1)
            elif name.startswith(base_name):
                try:
                    num = int(name.replace(base_name, ""))
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        if max_num == 1 and base_name not in sheet_names:
            return base_name
        else:
            return f"{base_name}{max_num+1}" 

    def get_edited_sheets(self, credentials, spreadsheet_id):
        """編集されたシートのリストを取得"""
        try:
            service = self._get_service(credentials)
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            
            edited_sheets = []
            for sheet in spreadsheet['sheets']:
                sheet_name = sheet['properties']['title']
                sheet_id = sheet['properties']['sheetId']
                
                # シートの内容を取得して、テンプレートと比較
                if self._is_sheet_edited(service, spreadsheet_id, sheet_name):
                    edited_sheets.append({
                        'name': sheet_name,
                        'id': sheet_id
                    })
            
            logger.info(f"Edited sheets found: {[s['name'] for s in edited_sheets]}")
            return edited_sheets
            
        except Exception as error:
            logger.error(f"Get edited sheets error: {error}")
            raise
    
    def _is_sheet_edited(self, service, spreadsheet_id, sheet_name):
        """シートが編集されているかどうかを判定"""
        try:
            # シートの内容を取得
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A1:Z100'  # 十分な範囲を取得
            ).execute()
            
            values = result.get('values', [])
            
            # 空のシートやテンプレートのままのシートを除外
            if not values or len(values) < 5:  # 最小限の内容がない場合
                return False
            
            # 重要なセルが編集されているかチェック
            # 見積書・請求書の場合は、会社名、品目、金額などの重要な情報が入力されているかチェック
            has_content = False
            
            for row_idx, row in enumerate(values):
                for col_idx, cell in enumerate(row):
                    if cell and str(cell).strip():  # 空でないセルがある
                        # テンプレートの固定テキスト以外の内容があるかチェック
                        if not self._is_template_text(cell):
                            has_content = True
                            break
                if has_content:
                    break
            
            return has_content
            
        except Exception as error:
            logger.error(f"Check sheet edited error: {error}")
            return False
    
    def _is_template_text(self, text):
        """テンプレートの固定テキストかどうかを判定"""
        template_texts = [
            '見積書', '請求書', '会社名', '住所', '電話番号', 'FAX', 'メールアドレス',
            '品目', '数量', '単価', '金額', '合計', '備考', '発行日', '支払期限',
            '振込先', '取引日', '宛名', '様'
        ]
        
        text_str = str(text).strip()
        return any(template in text_str for template in template_texts)
    
    def export_edited_sheets_to_pdf(self, credentials, spreadsheet_id, sheet_names=None):
        """編集されたシートのみをPDFにエクスポート（1シートのみ）"""
        try:
            if sheet_names is None:
                # 編集されたシートを自動検出
                edited_sheets = self.get_edited_sheets(credentials, spreadsheet_id)
                if not edited_sheets:
                    logger.warning("No edited sheets found")
                    return None
                # 最新の1シートだけに絞る（リストの最後）
                latest_sheet = edited_sheets[-1]
                logger.info(f"Selected latest edited sheet: {latest_sheet['name']}")
                sheet_names = [latest_sheet['name']]
            
            # 1シートのみをPDF化（結合処理は不要）
            pdf_content = self._export_single_sheet_to_pdf(credentials, spreadsheet_id, sheet_names[0])
            
            return pdf_content
            
        except Exception as error:
            logger.error(f"Export edited sheets to PDF error: {error}")
            raise
    
    def _combine_sheets_to_pdf(self, credentials, spreadsheet_id, sheet_names):
        """複数のシートを1つのPDFに結合"""
        try:
            # 各シートを個別にPDF化して結合
            combined_pdf_content = None
            
            for sheet_name in sheet_names:
                # シートをPDF化
                sheet_pdf = self._export_single_sheet_to_pdf(credentials, spreadsheet_id, sheet_name)
                
                if combined_pdf_content is None:
                    combined_pdf_content = sheet_pdf
                else:
                    # PDFを結合（簡易的な実装）
                    # 実際の実装では、PyPDF2などのライブラリを使用してPDFを結合
                    combined_pdf_content += sheet_pdf
            
            return combined_pdf_content
            
        except Exception as error:
            logger.error(f"Combine sheets to PDF error: {error}")
            raise
    
    def _export_single_sheet_to_pdf(self, credentials, spreadsheet_id, sheet_name, max_retries=3, retry_delay=5):
        """単一シートをPDFにエクスポート（リトライ機能付き）"""
        for attempt in range(max_retries):
            try:
                # シートIDを取得
                service = self._get_service(credentials)
                sheet_id = self.get_sheet_id_by_name(service, spreadsheet_id, sheet_name)
                
                # Google Sheets export URL
                export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=pdf&gid={sheet_id}&single=true&portrait=true&size=A4&fitw=true&top_margin=0.5&bottom_margin=0.5&left_margin=0.5&right_margin=0.5"
                
                # 認証付きでPDF取得
                authed_session = AuthorizedSession(credentials)
                response = authed_session.get(export_url)
                
                if response.status_code == 200:
                    logger.info(f"PDF export successful for sheet: {sheet_name}")
                    return response.content
                elif response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # 指数バックオフ
                        logger.warning(f"Rate limit hit (429), retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PDF export failed after {max_retries} attempts due to rate limiting")
                        raise Exception(f"PDF export failed with status 429 after {max_retries} retries")
                else:
                    logger.error(f"PDF export failed with status {response.status_code}")
                    raise Exception(f"PDF export failed with status {response.status_code}")
                    
            except Exception as error:
                if attempt < max_retries - 1:
                    logger.warning(f"PDF export attempt {attempt + 1} failed: {error}, retrying...")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Export single sheet to PDF error: {error}")
                    raise
        
        raise Exception("PDF export failed after all retry attempts") 

    def get_latest_edited_sheet_name(self, credentials, spreadsheet_id):
        """最新の編集済みシート名を取得"""
        try:
            edited_sheets = self.get_edited_sheets(credentials, spreadsheet_id)
            if not edited_sheets:
                return None
            # 最新の1シート（リストの最後）の名前を返す
            return edited_sheets[-1]['name']
        except Exception as error:
            logger.error(f"Get latest edited sheet name error: {error}")
            return None 

    def delete_sheet_by_name(self, credentials, spreadsheet_id, sheet_name):
        """指定したシート名のタブを削除"""
        service = self._get_service(credentials)
        try:
            sheet_id = self.get_sheet_id_by_name(service, spreadsheet_id, sheet_name)
        except Exception:
            # シートが存在しない場合は何もしない
            return False
        requests = [{
            'deleteSheet': {
                'sheetId': sheet_id
            }
        }]
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        logger.info(f"Deleted sheet: {sheet_name} (ID: {sheet_id}) from {spreadsheet_id}")
        return True 