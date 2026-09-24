# 冬の窓 — 最初のコッパー俳句

## 季語と走査線

この作品は、コッパーの `WAIT`命令を「間」として、
パレットレジスタの変更を「筆致」として読みます。

## ソースコード

```assembly
; Copper Haiku: Winter Window
CopperHaiku:
        dc.w $8018,$0141      ; 句の始まり
        dc.w $0030,$0FE0      ; 沈黙（余白）
        dc.w $DFF180,$0999    ; 灰白の空
        ...
