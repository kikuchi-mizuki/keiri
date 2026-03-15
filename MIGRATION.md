# データベースマイグレーション手順

## 概要
会社情報に以下の3つのフィールドを追加するマイグレーションです：
- `name` - 代表者名/担当者名
- `phone_number` - 電話番号
- `bank_account_holder` - 口座名義

## 実行方法

### 方法1: Railway CLIを使用（推奨）

1. **Railwayプロジェクトにリンク（初回のみ）**
   ```bash
   railway link
   ```
   プロンプトに従ってプロジェクトを選択してください。

2. **マイグレーション実行**
   ```bash
   railway run python run_migration.py
   ```

3. **実行結果の確認**
   成功すると以下のように表示されます：
   ```
   ✅ すべてのマイグレーションが正常に完了しました

   📋 現在のusersテーブルのカラム:
      - user_id: character varying
      - company_name: text
      - name: text
      - address: text
      - phone_number: text
      - bank_account: text
      - bank_account_holder: text
      ...
   ```

### 方法2: RailwayダッシュボードでSQL直接実行

1. [Railway Dashboard](https://railway.app/) にアクセス
2. プロジェクトを選択
3. PostgreSQLデータベースを選択
4. "Query" タブまたは "Connect" をクリック
5. 以下のSQLを実行：

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS bank_account_holder TEXT;
```

6. カラムが追加されたことを確認：

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
```

### 方法3: ローカル環境から実行

1. **DATABASE_URLを設定**
   ```bash
   export DATABASE_URL='postgresql://user:password@host:port/database'
   ```

2. **マイグレーション実行**
   ```bash
   python run_migration.py
   ```

## トラブルシューティング

### エラー: "DATABASE_URL環境変数が設定されていません"
- Railway CLIを使用する場合: `railway run` を使用してください
- ローカルから実行する場合: `export DATABASE_URL='...'` で環境変数を設定してください

### エラー: "No linked project found"
```bash
railway link
```
を実行してRailwayプロジェクトにリンクしてください。

### カラムが既に存在する場合
`ADD COLUMN IF NOT EXISTS` を使用しているため、既にカラムが存在する場合はエラーにならず、スキップされます。

## マイグレーション後の動作確認

1. LINEボットを開く
2. 「会社情報を編集」を選択
3. すべてのフィールド（会社名、代表者名、住所、電話番号、銀行口座、口座名義）を入力
4. 見積書または請求書を作成
5. Google Sheetsで会社情報が正しく反映されているか確認

## 既存ユーザーへの影響

既存のユーザーは、新しいフィールド（name, phone_number, bank_account_holder）がNULLの状態になります。次回「会社情報を編集」を選択すると、すべてのフィールドを再入力することで最新の情報が登録されます。
