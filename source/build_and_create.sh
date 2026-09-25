#!/bin/bash
# ============================================================================
# build_and_create.sh — thumbnail-box 完全ビルドスクリプト
# ============================================================================

set -e  # エラー発生時に終了

echo "=============================================="
echo " thumbnail-box Build Pipeline"
echo "=============================================="

# 1. ビルド前チェック
echo "[1/5] Checking tools..."
command -v vasm68k >/dev/null 2>&1 || { echo "ERROR: vasm68k not installed"; exit 1; }
command -v vlink >/dev/null 2>&1 || { echo "ERROR: vlink not installed"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not installed"; exit 1; }
echo "[OK] All tools ready"

# 2. winter.asm をアセンブル（データ）
echo "[2/5] Assembling winter.asm..."
vasm68k -Fhunkbin -o winter.o winter.asm
echo "[OK] winter.o created"

# 3. startup.asm をアセンブル（コード）
echo "[3/5] Assembling startup.asm..."
vasm68k -Fhunkbin -o startup.o startup.asm
echo "[OK] startup.o created"

# 4. リンク
echo "[4/5] Linking to winter.exe..."
vlink -F amiga -o winter.exe startup.o winter.o
echo "[OK] winter.exe created ($(stat -f%z winter.exe 2>/dev/null || stat -c%s winter.exe) bytes)"

# 5. ADF 作成
echo "[5/5] Creating boot.adf..."
python3 make_adf.py --input winter.exe --output boot.adf --name WINTER
echo "[OK] boot.adf created"

echo ""
echo "=============================================="
echo " ✅ BUILD SUCCESSFUL"
echo "=============================================="
echo ""
echo "生成ファイル:"
ls -lh winter.exe boot.adf
echo ""
echo "WinUAE で実行:"
echo "  1. WinUAE を起動"
echo "  2. Floppy → DF0: に boot.adf をセット"
echo "  3. Amiga Shell で 'execute WINTER'"
echo ""
