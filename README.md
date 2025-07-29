# AI経理秘書 LINE Bot

## 概要
LINE Botを使用して、Google Sheetsで見積書・請求書を自動生成するAI経理秘書サービスです。

## 主な機能
- LINEから見積書・請求書の作成
- Google Sheetsとの連携
- PDF出力機能
- 既存シートからの選択機能（ページネーション対応）
- 会社名を含むシート名の自動生成
- **AI経理秘書 解約制限システム**（契約期間ベース）

## AI経理秘書 解約制限システム

### 概要
契約期間を管理し、解約したユーザーの利用を制限するシステムです。

### 特徴
- **契約期間ベースの制限**: `usage_logs`の存在チェックではなく、実際の契約期間で判定
- **後方互換性**: 既存の`usage_logs`データも考慮（移行期間30日）
- **柔軟な契約管理**: 契約の作成・延長・キャンセルが可能

### データベース構造

#### subscriptions テーブル
```sql
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    content_type VARCHAR(100) NOT NULL,
    start_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_date TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active', 'cancelled', 'expired'
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 制限チェックロジック
1. **アクティブな契約がある場合**: 利用可能
2. **契約がない場合**: `usage_logs`の最新記録をチェック
3. **30日以内の使用記録がある場合**: 一時的に利用可能（移行期間）
4. **それ以外**: 利用制限

### 契約管理機能
- `create_subscription()`: 新しい契約を作成
- `extend_subscription()`: 既存契約を延長
- `cancel_subscription()`: 契約をキャンセル
- `get_user_subscriptions()`: ユーザーの契約一覧取得

## 環境変数
```
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
DATABASE_URL=your_postgresql_database_url
AI_COLLECTIONS_BASE_URL=https://lp-production-9e2c.up.railway.app/
```

## セットアップ
1. 必要なパッケージをインストール
```bash
pip install -r requirements.txt
```

2. 環境変数を設定
```bash
cp env_example.txt .env
# .envファイルを編集して実際の値を設定
```

3. データベースのマイグレーションを実行
```bash
# PostgreSQLに接続してdatabase_migration.sqlを実行
```

4. アプリケーションを起動
```bash
python app.py
```

## テストエンドポイント

### 制限チェック
- `GET /test/restriction/<line_user_id>?email=<email>`: 制限チェックテスト
- `GET /health/restriction`: 制限システムのヘルスチェック

### 契約管理
- `POST /test/subscription/create`: 契約作成テスト
- `GET /test/subscription/<user_id>`: ユーザーの契約一覧取得
- `POST /test/subscription/<subscription_id>/extend`: 契約延長テスト
- `POST /test/subscription/<subscription_id>/cancel`: 契約キャンセルテスト

### 契約作成の例
```bash
curl -X POST http://localhost:5000/test/subscription/create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "content_type": "AI経理秘書",
    "duration_days": 30
  }'
```

## デプロイ
Railwayを使用してデプロイします。

```bash
# Railway CLIでログイン
railway login

# プロジェクトにリンク
railway link

# デプロイ
railway up
```

## 注意事項
- 契約期間ベースの制限システムは、既存の`usage_logs`ベースのシステムから移行されます
- 移行期間中（30日）は、`usage_logs`の最新記録も考慮されます
- 本格運用前に、既存データの移行戦略を慎重に検討してください 