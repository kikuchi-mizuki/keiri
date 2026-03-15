#!/bin/bash

echo "============================================================"
echo "  🚀 Railway CLIで自動マイグレーション"
echo "============================================================"
echo ""

# Step 1: Railway再認証
echo "📝 Step 1: Railway認証を確認中..."
if ! railway whoami &> /dev/null; then
    echo "⚠️  認証が必要です。以下のコマンドを実行してください："
    echo ""
    echo "    railway login"
    echo ""
    echo "認証後、このスクリプトを再実行してください。"
    exit 1
fi

echo "✅ 認証済み"
echo ""

# Step 2: プロジェクトにリンク
echo "📝 Step 2: Railwayプロジェクトにリンク中..."
if ! railway status &> /dev/null; then
    echo "🔗 プロジェクトをリンクします..."
    railway link
    if [ $? -ne 0 ]; then
        echo "❌ リンクに失敗しました"
        exit 1
    fi
fi

echo "✅ プロジェクトにリンク済み"
echo ""

# Step 3: マイグレーション実行
echo "📝 Step 3: マイグレーション実行中..."
echo ""
railway run python run_migration.py

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "  ✅ マイグレーション完了！"
    echo "============================================================"
    echo ""
    echo "次のステップ："
    echo "  1. LINEボットで「会社情報を編集」を選択"
    echo "  2. すべての情報を入力（会社名、名前、住所、電話、口座、口座名義）"
    echo "  3. 見積書/請求書を作成して確認"
    echo ""
else
    echo ""
    echo "============================================================"
    echo "  ❌ マイグレーション失敗"
    echo "============================================================"
    exit 1
fi
