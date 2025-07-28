# AI経理秘書 - LINE見積書・請求書自動生成Bot

LINE上で会社情報と請求内容を入力することで、自動でGoogle Sheetsテンプレートに記入された見積書・請求書を生成し、編集リンクとPDFを取得できるBotシステムです。

**解約制限システム対応**: 解約済みユーザーはサービス利用を制限され、AIコレクションズ公式LINEへの誘導が行われます。

## 機能概要

### 主要機能
- **ユーザー初期登録**: 会社名、住所、銀行口座情報の登録
- **Google認証**: Google Driveアクセス権限の取得
- **見積書作成**: 品目、単価、数量を入力して見積書を生成
- **請求書作成**: 見積書と同様のフローで請求書を生成
- **Google Sheets連携**: テンプレートの複製とデータの自動入力
- **編集リンク送信**: 生成されたスプレッドシートの編集リンクをLINEで送信

### 技術スタック
- **バックエンド**: Python (Flask)
- **LINE Bot**: LINE Messaging API
- **Google API**: Google Sheets API, Google Drive API, Google OAuth 2.0
- **データベース**: SQLite (セッション管理), PostgreSQL (解約制限システム)
- **認証**: Google OAuth 2.0

## セットアップ手順

### 1. 必要な環境
- Python 3.8以上
- LINE Developers アカウント
- Google Cloud Platform アカウント

### 2. 依存関係のインストール
```bash
pip install -r requirements.txt
```

### 3. LINE Bot設定
1. [LINE Developers Console](https://developers.line.biz/)でチャネルを作成
2. Messaging APIチャネルを選択
3. チャネルアクセストークンとチャネルシークレットを取得

### 4. Google API設定
1. [Google Cloud Console](https://console.cloud.google.com/)でプロジェクトを作成
2. Google Sheets APIとGoogle Drive APIを有効化
3. OAuth 2.0クライアントIDを作成
4. `client_secrets.json`ファイルをダウンロードしてプロジェクトルートに配置

### 5. Google Sheetsテンプレート作成
1. Google Sheetsで見積書・請求書のテンプレートを作成
2. テンプレートのスプレッドシートIDを取得
3. テンプレートを共有設定で「リンクを知っている全員が編集可能」に設定

### 6. 環境変数設定
`env_example.txt`を参考に`.env`ファイルを作成し、必要な値を設定：

```bash
# LINE Bot設定
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret

# Google OAuth設定
GOOGLE_CLIENT_SECRETS_JSON={"web":{"client_id":"your_client_id","project_id":"your_project_id","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_secret":"your_client_secret","redirect_uris":["your_redirect_uri"]}}

# 共有PostgreSQLデータベース設定（解約制限システム用）
DATABASE_URL=postgresql://username:password@host:port/database_name

# AIコレクションズ設定
AI_COLLECTIONS_BASE_URL=https://ai-collections.herokuapp.com
```

### 7. アプリケーション起動
```bash
python app.py
```

### 8. LINE Webhook設定
LINE Developers ConsoleでWebhook URLを設定：
```
http://your-domain.com/callback
```

## 使用方法

### 初期登録フロー
1. LINEでBotを友達追加
2. 会社名を入力
3. 住所を入力
4. 振込先銀行口座を入力
5. Google認証リンクからDriveアクセスを許可

### 書類作成フロー
1. メインメニューから「見積書を作る」または「請求書を作る」を選択
2. 会社名の確認・編集
3. 品目を入力（形式：品目名,単価,数量）
4. 振込期日を入力（形式：YYYY-MM-DD）
5. 備考を入力（任意）
6. 送付先メールアドレスを入力（任意）
7. 自動でGoogle Sheetsが生成され、編集リンクが送信される

## プロジェクト構造

```
keiri/
├── app.py                          # メインアプリケーションファイル
├── requirements.txt                # Python依存関係
├── env_example.txt                 # 環境変数設定例
├── README.md                       # プロジェクト説明
├── services/                       # サービス層
│   ├── __init__.py
│   ├── session_manager.py          # セッション管理
│   ├── auth_service.py             # Google認証管理
│   ├── google_sheets_service.py    # Google Sheets操作
│   ├── document_generator.py       # 書類生成統合管理
│   └── restriction_checker.py      # 解約制限チェック機能
├── sessions.db                     # SQLiteデータベース（自動生成）
└── client_secrets.json             # Google OAuth設定（要配置）
```

## 解約制限システム

### 概要
解約済みユーザーがサービスを利用できないように制限し、AIコレクションズ公式LINEへの誘導を行うシステムです。

### 機能
- **リアルタイム利用制限チェック**: メッセージ受信時に解約履歴をチェック
- **制限メッセージ送信**: 解約済みユーザーに専用メッセージを送信
- **AIコレクションズ誘導**: 公式LINEとサービス詳細ページへの誘導

### データベース要件
共有PostgreSQLデータベースに以下のテーブルが必要です：

```sql
-- ユーザーテーブル
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    line_user_id VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 解約履歴テーブル
CREATE TABLE cancellation_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    content_type VARCHAR(100) NOT NULL,
    cancelled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### テストエンドポイント
- `/test/restriction/<line_user_id>`: 制限チェック機能のテスト
- `/health/restriction`: 制限チェック機能のヘルスチェック

## セキュリティ考慮事項

- Google OAuthはofflineスコープ付きでリフレッシュトークンを保持
- ユーザーの入力内容・テンプレート生成ログは必要最小限に保管
- LINEユーザーIDを一意な識別子としてGoogle認証と紐づけ
- 環境変数で機密情報を管理

## 今後の拡張予定

- 見積書から請求書への自動変換（ステータス管理）
- 複数アカウント対応（法人・個人切り替え）
- 定期請求・繰り返し請求への対応
- 会話形式の自然言語処理の導入
- PDF出力機能の強化

## トラブルシューティング

### よくある問題

1. **Google認証エラー**
   - `client_secrets.json`が正しく配置されているか確認
   - OAuth 2.0クライアントIDの設定を確認

2. **LINE Webhookエラー**
   - Webhook URLが正しく設定されているか確認
   - チャネルアクセストークンとシークレットが正しいか確認

3. **Google Sheets APIエラー**
   - APIが有効化されているか確認
   - テンプレートのスプレッドシートIDが正しいか確認

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。 