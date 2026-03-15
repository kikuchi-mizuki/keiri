#!/bin/bash

echo "============================================================"
echo "  データベースマイグレーション実行スクリプト"
echo "============================================================"
echo ""

# Railway CLIでマイグレーションを実行
echo "🔄 Railwayプロジェクトに接続してマイグレーションを実行します..."
echo ""

# Railway linkの確認
if ! railway status &> /dev/null; then
    echo "⚠️  Railwayプロジェクトにリンクされていません"
    echo ""
    echo "以下のコマンドを実行してください："
    echo "  1. railway link"
    echo "  2. ./execute_migration.sh"
    echo ""
    exit 1
fi

echo "✅ Railwayプロジェクトに接続されています"
echo ""

# マイグレーション実行
echo "🚀 マイグレーションを実行中..."
railway run python run_migration.py

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "  ✅ マイグレーション完了!"
    echo "============================================================"
    echo ""
    echo "次のステップ："
    echo "  1. LINEボットを開く"
    echo "  2. 「会社情報を編集」を選択"
    echo "  3. すべての情報を再入力"
    echo ""
else
    echo ""
    echo "============================================================"
    echo "  ❌ マイグレーション失敗"
    echo "============================================================"
    echo ""
    echo "エラーが発生しました。MIGRATION.mdを参照してください。"
    echo ""
    exit 1
fi
