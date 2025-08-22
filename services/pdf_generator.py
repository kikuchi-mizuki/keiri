import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import tempfile
import io
import pypdf
import time

logger = logging.getLogger(__name__)

class PDFGenerator:
    """PDF生成クラス"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_fonts()
    
    def _setup_fonts(self):
        """日本語フォントの設定"""
        try:
            # macOS用の日本語フォント
            font_path = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Hiragino', font_path))
            else:
                # 代替フォント
                font_path = "/System/Library/Fonts/Arial Unicode MS.ttf"
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('ArialUnicode', font_path))
        except Exception as e:
            logger.warning(f"Font setup failed: {e}")
    
    def create_edited_sheets_pdf(self, sheets_service, credentials, spreadsheet_id, max_retries=3, retry_delay=5):
        """編集されたシートのみのPDFを作成（リトライ機能付き）"""
        for attempt in range(max_retries):
            try:
                # 編集されたシートを取得
                edited_sheets = sheets_service.get_edited_sheets(credentials, spreadsheet_id)
                if not edited_sheets:
                    logger.warning("No edited sheets found")
                    return None
                
                # 最新の1シートだけに絞る（リストの最後）
                latest_sheet = edited_sheets[-1]
                sheet_name = latest_sheet['name']
                logger.info(f"Selected latest edited sheet: {sheet_name}")
                
                # 1シートのみをPDF化
                pdf_content = sheets_service._export_single_sheet_to_pdf(
                    credentials, spreadsheet_id, sheet_name, max_retries, retry_delay
                )
                
                if pdf_content:
                    # 一時ファイルに保存
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                    temp_file.write(pdf_content)
                    temp_file.close()
                    
                    logger.info(f"Edited sheets PDF created: {temp_file.name}")
                    return temp_file.name
                else:
                    logger.error("PDF content is empty")
                    return None
                    
            except Exception as error:
                if attempt < max_retries - 1:
                    logger.warning(f"Edited sheets PDF creation attempt {attempt + 1} failed: {error}, retrying...")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Edited sheets PDF creation error: {error}")
                    raise
        
        raise Exception("Edited sheets PDF creation failed after all retry attempts")
    
    def _combine_pdf_parts(self, pdf_parts, filename):
        """複数のPDFパーツを結合"""
        try:
            if not pdf_parts:
                return None
            
            # pypdfを使用してPDFを結合
            merger = pypdf.PdfMerger()
            
            for pdf_content in pdf_parts:
                # バイトデータをファイルオブジェクトに変換
                pdf_stream = io.BytesIO(pdf_content)
                merger.append(pdf_stream)
            
            # 結合したPDFを保存
            with open(filename, 'wb') as output_file:
                merger.write(output_file)
            
            merger.close()
            return filename
            
        except Exception as e:
            logger.error(f"PDF combine error: {e}")
            # フォールバック：最初のPDFを使用
            if pdf_parts:
                with open(filename, 'wb') as f:
                    f.write(pdf_parts[0])
                return filename
            return None
    
    def create_estimate_pdf(self, data, filename):
        """見積書PDFを作成"""
        try:
            doc = SimpleDocTemplate(filename, pagesize=A4)
            story = []
            
            # タイトル
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=self.styles['Heading1'],
                fontSize=18,
                spaceAfter=20,
                alignment=1,  # 中央揃え
                fontName='Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
            )
            title = Paragraph("見積書", title_style)
            story.append(title)
            story.append(Spacer(1, 20))
            
            # 基本情報テーブル
            basic_info = [
                ['発行日', data.get('issue_date', '')],
                ['会社名', data.get('company_name', '')],
                ['住所', data.get('address', '')],
            ]
            
            basic_table = Table(basic_info, colWidths=[80*mm, 100*mm])
            basic_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 0), (0, -1), colors.grey),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            story.append(basic_table)
            story.append(Spacer(1, 20))
            
            # 品目テーブル
            items = data.get('items', [])
            if items:
                # ヘッダー
                item_data = [['品目', '数量', '単価', '金額']]
                
                # 品目データ
                for item in items:
                    item_data.append([
                        item.get('name', ''),
                        str(item.get('quantity', '')),
                        f"¥{item.get('price', 0):,}",
                        f"¥{item.get('amount', 0):,}"
                    ])
                
                # 合計行
                total_amount = data.get('total_amount', 0)
                item_data.append(['', '', '合計', f"¥{total_amount:,}"])
                
                item_table = Table(item_data, colWidths=[80*mm, 30*mm, 35*mm, 35*mm])
                item_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.lightgrey]),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.lightblue),
                    ('FONTNAME', (0, -1), (-1, -1), 'Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'),
                ]))
                story.append(item_table)
                story.append(Spacer(1, 20))
            
            # 備考
            notes = data.get('notes', '')
            if notes:
                notes_style = ParagraphStyle(
                    'Notes',
                    parent=self.styles['Normal'],
                    fontSize=10,
                    fontName='Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
                )
                notes_para = Paragraph(f"備考: {notes}", notes_style)
                story.append(notes_para)
            
            # PDF生成
            doc.build(story)
            logger.info(f"Estimate PDF created: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Estimate PDF creation error: {e}")
            raise
    
    def create_invoice_pdf(self, data, filename):
        """請求書PDFを作成"""
        try:
            doc = SimpleDocTemplate(filename, pagesize=A4)
            story = []
            
            # タイトル
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=self.styles['Heading1'],
                fontSize=18,
                spaceAfter=20,
                alignment=1,  # 中央揃え
                fontName='Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
            )
            title = Paragraph("請求書", title_style)
            story.append(title)
            story.append(Spacer(1, 20))
            
            # 基本情報テーブル
            basic_info = [
                ['発行日', data.get('issue_date', '')],
                ['会社名', data.get('company_name', '')],
                ['住所', data.get('address', '')],
                ['支払期限', data.get('due_date', '')],
                ['銀行口座', data.get('bank_account', '')],
            ]
            
            basic_table = Table(basic_info, colWidths=[80*mm, 100*mm])
            basic_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 0), (0, -1), colors.grey),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            story.append(basic_table)
            story.append(Spacer(1, 20))
            
            # 品目テーブル
            items = data.get('items', [])
            if items:
                # ヘッダー
                item_data = [['品目', '数量', '単価', '金額']]
                
                # 品目データ
                for item in items:
                    item_data.append([
                        item.get('name', ''),
                        str(item.get('quantity', '')),
                        f"¥{item.get('price', 0):,}",
                        f"¥{item.get('amount', 0):,}"
                    ])
                
                # 合計行
                total_amount = data.get('total_amount', 0)
                item_data.append(['', '', '合計', f"¥{total_amount:,}"])
                
                item_table = Table(item_data, colWidths=[80*mm, 30*mm, 35*mm, 35*mm])
                item_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.lightgrey]),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.lightblue),
                    ('FONTNAME', (0, -1), (-1, -1), 'Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'),
                ]))
                story.append(item_table)
                story.append(Spacer(1, 20))
            
            # 備考
            notes = data.get('notes', '')
            if notes:
                notes_style = ParagraphStyle(
                    'Notes',
                    parent=self.styles['Normal'],
                    fontSize=10,
                    fontName='Hiragino' if 'Hiragino' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
                )
                notes_para = Paragraph(f"備考: {notes}", notes_style)
                story.append(notes_para)
            
            # PDF生成
            doc.build(story)
            logger.info(f"Invoice PDF created: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Invoice PDF creation error: {e}")
            raise 