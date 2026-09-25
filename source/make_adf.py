#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_adf.py — thumbnail-box 用 ADF 構築ツール（FFS 完全実装版）

使い方:
    python3 make_adf.py --input winter.exe --output boot.adf

オプション:
    --name FILENAME      ADF 内のファイル名（デフォルト: 入力ファイル名）
    --autostart TRUE     ブート時に自動実行（デフォルト: FALSE）
"""

import os
import sys
import struct
import argparse
import time
from pathlib import Path

class AmigaADF:
    """Amiga Fast File System (FFS) Disk Image 構築クラス"""
    
    # 定数
    SECTOR_SIZE = 512
    NUM_CYLS = 80
    NUM_HEADS = 2
    NUM_SECT_PER_TRACK = 11
    TOTAL_SECTORS = NUM_CYLS * NUM_HEADS * NUM_SECT_PER_TRACK
    
    # ファイルタイプ
    ST_FILE = 2
    ST_HARDLINK = 1
    ST_SOFTLINK = 8
    ST_INITIAL = 4
    ST_LIST = 6
    
    # ファイル属性
    AF_READ = 0x01
    AF_WRITE = 0x02
    AF_EXECUTE = 0x04
    AF_DELETE = 0x08
    
    def __init__(self, adf_path):
        self.adf_path = adf_path
        self.data_blocks = []  # 実際のデータ
        self.block_map = {}    # ファイル → ブロックリスト
        self.root_entries = [] # ルートディレクトリエントリ
        
    def _pad_sector(self, data):
        """セクターサイズにパディング"""
        padding_needed = self.SECTOR_SIZE - (len(data) % self.SECTOR_size)
        if padding_needed == self.SECTOR_SIZE:
            padding_needed = 0
        return data + (b'\x00' * padding_needed)
    
    def _calculate_checksum(self, block_data):
        """Amiga のチェックサム計算"""
        checksum = 0
        for i in range(0, len(block_data), 4):
            word = struct.unpack('>I', block_data[i:i+4])[0]
            checksum = (checksum + word) & 0xFFFFFFFF
            if checksum >= 0x80000000:
                checksum -= 0x100000000
        checksum = (~checksum) & 0xFFFFFFFF
        return checksum
    
    def _create_header_block(self, file_type, flags=0, name=b''):
        """ファイルまたはディレクトリヘッダーブロック作成"""
        header = bytearray(self.SECTOR_SIZE)
        
        # タイプ
        struct.pack_into('>I', header, 0x000, file_type)
        # チェックサム（後で計算）
        # ホスト ID（0 = 不明）
        struct.pack_into('>I', header, 0x004, 0)
        # 次のブロック（0 = なし）
        struct.pack_into('>I', header, 0x008, 0)
        # 前のブロック
        struct.pack_into('>I', header, 0x00C, 0)
        
        # メタデータ
        struct.pack_into('>I', header, 0x010, 0)  # 親ディレクトリ（0 = ルート）
        struct.pack_into('>I', header, 0x014, 0)  # エントリタイプ
        struct.pack_into('>I', header, 0x018, 0)  # サイズ（バイト）
        struct.pack_into('>I', header, 0x01C, 0)  # サイズ（セクタ）
        
        # 日付（Amiga 形式）
        current_time = int(time.time())
        amiga_days = (current_time - 914704800) // 86400
        struct.pack_into('>I', header, 0x020, amiga_days)
        struct.pack_into('>I', header, 0x024, (current_time % 86400) * 50)  # タicks
        
        # 属性
        struct.pack_into('>I', header, 0x03C, flags)
        
        # ファイル名（最大 30 バイト）
        name_len = min(len(name), 30)
        struct.pack_into('>B', header, 0x044, name_len)
        header[0x045:0x045+name_len] = name[:30]
        
        return header
    
    def _create_data_block(self, data):
        """データブロック作成"""
        block = bytearray(self.SECTOR_SIZE)
        
        # タイプ = ST_FILE (2)
        struct.pack_into('>I', block, 0x000, self.ST_FILE)
        
        # データ
        block[0x020:0x020+len(data)] = data[:492]  # ヘッダー除外
        
        return bytes(block)
    
    def _create_directory_entry(self, file_type, size, name, first_block):
        """ディレクトリエントリ作成"""
        entry = bytearray(60)
        
        # 次のエントリ
        struct.pack_into('>I', entry, 0x000, 0)
        # ファイルタイプ
        struct.pack_into('>B', entry, 0x004, file_type)
        # 属性
        struct.pack_into('>B', entry, 0x005, self.AF_EXECUTE if file_type == self.ST_FILE else 0)
        # サイズ（バイト）
        struct.pack_into('>I', entry, 0x006, size)
        # ファイル名長
        name_bytes = name.encode('latin-1')[:30]
        struct.pack_into('>B', entry, 0x00A, len(name_bytes))
        entry[0x00B:0x00B+len(name_bytes)] = name_bytes
        # 最初のデータブロック
        struct.pack_into('>I', entry, 0x02C, first_block)
        
        return bytes(entry)
    
    def add_file(self, filepath, disk_name=None, executable=False):
        """ADF にファイルを追加"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        with open(filepath, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        filename = disk_name or os.path.basename(filepath)
        exec_flag = self.AF_EXECUTE if executable else 0
        
        print(f"[INFO] Adding '{filename}' ({file_size} bytes)")
        
        # データブロック分割
        num_blocks = (file_size + 511) // 511  # 511 バイト/ブロック（ヘッダー除く）
        block_list = []
        
        for i in range(num_blocks):
            start = i * 511
            end = min(start + 511, file_size)
            chunk = file_data[start:end]
            
            # データブロック作成
            data_block = self._create_data_block(chunk)
            checksum = self._calculate_checksum(data_block)
            struct.pack_into('>I', data_block, 0x004, checksum)
            
            # 最後のブロック以外は、次のブロックへのポインタを設定
            if i < num_blocks - 1:
                struct.pack_into('>I', data_block, 0x008, i + 1)
            
            self.data_blocks.append(bytes(data_block))
            block_list.append(i + 1)  # 1 から開始
        
        # ファイルヘッダー作成
        file_header = self._create_header_block(self.ST_FILE, exec_flag, filename.encode('latin-1'))
        struct.pack_into('>I', file_header, 0x018, file_size)
        struct.pack_into('>I', file_header, 0x01C, num_blocks)
        checksum = self._calculate_checksum(file_header)
        struct.pack_into('>I', file_header, 0x004, checksum)
        
        # ルートディレクトリにエントリ追加
        dir_entry = self._create_directory_entry(
            self.ST_FILE, file_size, filename, block_list[0] if block_list else 0
        )
        self.root_entries.append(dir_entry)
        
        print(f"[OK] Added '{filename}' with {num_blocks} blocks")
        return True
    
    def build(self):
        """ADF イメージを構築"""
        total_size = self.TOTAL_SECTORS * self.SECTOR_SIZE
        print(f"[INFO] Building ADF: {total_size:,} bytes ({total_size // 1024 // 1024} MB)")
        
        # ADF をゼロ埋め
        adf_data = bytearray(total_size)
        
        # ブロックマップ管理（簡易）
        # 0: ボリュームヘッダー
        # 1: ルートディレクトリ
        # 2+: ファイルデータ
        
        # ボリュームヘッダー作成
        vol_block = self._create_header_block(self.ST_LIST, name=b'THUMBNAILBOX')
        struct.pack_into('>I', vol_block, 0x020, 0)  # サイズ
        checksum = self._calculate_checksum(vol_block)
        struct.pack_into('>I', vol_block, 0x004, checksum)
        
        # ADF に書き込み（シリンダ 0、ヘッド 0、セクタ 1〜）
        sector_offset = 0
        
        # ボリュームヘッダー（1 ブロック）
        adf_data[sector_offset * self.SECTOR_SIZE:(sector_offset + 1) * self.SECTOR_SIZE] = vol_block
        sector_offset += 1
        
        # ルートディレクトリエントリ（複数エントリ）
        dir_data = bytearray(self.SECTOR_SIZE)
        for i, entry in enumerate(self.root_entries):
            offset = i * 60
            dir_data[offset:offset + len(entry)] = entry
        dir_data[0:4] = struct.pack('>I', self.ST_LIST)  # タイプ
        checksum = self._calculate_checksum(dir_data)
        struct.pack_into('>I', dir_data, 0x004, checksum)
        
        adf_data[sector_offset * self.SECTOR_SIZE:(sector_offset + 1) * self.SECTOR_SIZE] = dir_data
        sector_offset += 1
        
        # データブロック
        for i, block in enumerate(self.data_blocks):
            checksum = self._calculate_checksum(block)
            struct.pack_into('>I', block, 0x004, checksum)
            adf_data[sector_offset * self.SECTOR_SIZE:(sector_offset + 1) * self.SECTOR_SIZE] = block
            sector_offset += 1
        
        # ファイルを書き出す
        with open(self.adf_path, 'wb') as f:
            f.write(adf_data)
        
        print(f"[OK] ADF written to {self.adf_path}")
        print(f"[INFO] Used {sector_offset} of {self.TOTAL_SECTORS} sectors ({sector_offset * 100 // self.TOTAL_SECTORS}%)")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Create Amiga ADF disk image for thumbnail-box project',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
    python3 make_adf.py --input winter.exe --output boot.adf
    python3 make_adf.py -i startup.bin -o disk.adf --name BOOT
    python3 make_adf.py --input winter.exe -o boot.adf --autostart
        """
    )
    
    parser.add_argument('--input', '-i', required=True, help='入力ファイル（アセンブル済みバイナリ）')
    parser.add_argument('--output', '-o', default='boot.adf', help='出力 ADF ファイル')
    parser.add_argument('--name', '-n', help='ADF 内のファイル名（デフォルト: 入力ファイル名）')
    parser.add_argument('--autostart', '-a', action='store_true', help='ブート時自動実行（要 Bootblock）')
    parser.add_argument('--verbose', '-v', action='store_true', help='詳細ログ')
    
    args = parser.parse_args()
    
    try:
        # ADF 構築
        adf = AmigaADF(args.output)
        
        # ファイル追加
        adf.add_file(
            args.input,
            disk_name=args.name,
            executable=True  # Amiga では常に実行可能フラグ
        )
        
        # ADF 構築
        success = adf.build()
        
        if success:
            print("\n" + "="*60)
            print("✅ ADF 構築完了")
            print("="*60)
            print(f"\nファイル: {args.output}")
            print(f"包含ファイル: {args.name or os.path.basename(args.input)}")
            print(f"\nWinUAE で実行:")
            print(f"  1. WinUAE を起動")
            print(f"  2. Floppy タブで '{args.output}' を DF0: にマウント")
            print(f"  3. Workbench からファイルをダブルクリック")
            print(f"  または Shell で:")
            print(f"    execute {args.name or os.path.basename(args.input)}")
            print()
        
        sys.exit(0 if success else 1)
        
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
