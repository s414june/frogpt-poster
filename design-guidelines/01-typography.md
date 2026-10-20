# 01 — Typography / 字體與文字排版

## 目的與依據
參考 IBM Carbon 的 productive / expressive type sets、type tokens（大小、字重、行高）與 USWDS 的可讀性建議。**移植原則，非複製 UI 的 px 尺度為印刷海報尺寸**。FroGPT 自訂值須可由 style preset 覆蓋。

## 規則
| Rule ID | 等級 | 初始值 / 條件 | 實作要求 |
|---|---|---|---|
| TYPO-001 | hard | 至少 1 個有效文字元素 | 空白、只有空格、字型不支援且無 fallback 均不得成功渲染 |
| TYPO-002 | hard | 保留原文與標點 | 不可自動刪字、改字、截斷；自動換行可以，必須可回報 |
| TYPO-003 | hard | glyph bounding box 在文字安全區內 | 以實際字型 metrics、換行結果判斷；非單靠 fontSize |
| TYPO-004 | soft | headline size 0.07–0.14 × 短邊；初始 0.10 | 由字數與空間自動縮放，允許風格覆蓋 |
| TYPO-005 | soft | secondary/title 0.30–0.50 × headline；body 0.18–0.34 | 僅做比例初始範圍；可超出但需記錄 |
| TYPO-006 | soft | headline lineHeight 0.90–1.15、body 1.15–1.60，倍率 | 以字體實際 metrics 校驗；繁體中文避免過度擠壓 |
| TYPO-007 | soft | 同張海報字族預設最多 2 組，字重最多 3 種 | 參考設計可覆蓋，顯示 warning |
| TYPO-008 | soft | 優先使用 2–4 層文字層級 | 少字海報僅有 headline 也合法；不是強制四種層級 |
| TYPO-009 | hard | font glyph coverage + fallback | 對中英文混排逐 run 量測，fallback 必須實際可用，不能靠瀏覽器未知替換 |
| TYPO-010 | advisory | 兩行中文標題考慮語意斷行 | 不在標點前產生孤行、不隨意拆固定詞組；可允許刻意設計 |

## 量測與折行流程
1. 由渲染端實際載入字型，取得 glyph advance、ascender/descender、tracking 與字距。
2. 根據指定 bbox 寬度進行多語言段落分行；依標點禁則及語意選擇候選斷行。
3. 試算每個候選的寬度、高度、墨跡範圍；必要時先調整換行、再調整字級、最後建議移動文字區塊。
4. 若無解，回傳 `TYPO_TEXT_OVERFLOW`，附上最大可接受字級／需要的 bbox；不可默默截字。
5. 記錄 `requestedFont`, `resolvedFont`, `measuredLines`, `bbox`, `changes`。

## 設計意圖與美感
允許標題極大、非置中、不對稱與中英混排；禁止因套用字級比例而使各層文字一律等大。標題可以有較緊的行距，但不能讓重要字元相互遮擋；API 應以字形外框驗證。

## 測試
繁中 2/4/12/40 字標題、英數混排、CJK 字體 fallback、手寫字型、極粗明體、不同字距、換行前後文字完整一致。
