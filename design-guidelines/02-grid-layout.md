# 02 — Grid & Layout / 網格與版面

## 目的與依據
參考 Carbon 2x Grid 的尺寸節奏／key lines 和 `dostevskii/grid-system` 的固定畫板、欄列、gutters、SVG/JSON 設定概念。**畫板是固定輸出尺寸，不使用 Carbon 網頁 breakpoints 作海報預設。**

## 規則
| Rule ID | 等級 | 初始值 / 條件 | 實作要求 |
|---|---|---|---|
| GRID-001 | hard | 座標規格 x/y/w/h 為 0–1 normalized | 必須可在不同畫板比例換算，負寬高或 NaN 拒絕 |
| GRID-002 | hard | 重要內容（文字／完整產品主體的保護區）不得超出 canvas | 藝術性 bleed 只針對明示可裁切的裝飾素材 |
| GRID-003 | soft | 四周 safe margin = 0.05–0.08 × 短邊，預設 0.06 | 換算為畫布 x/y 軸分別不同的 normalized margin |
| GRID-004 | soft | 4、6 或 12 欄，預設 6 欄 | 依構圖密度選擇，非必須對齊每條格線 |
| GRID-005 | soft | gutter = 短邊 0.015–0.035，預設 0.025 | 可用風格 override |
| GRID-006 | soft | 內容群組共享 key lines；同組可有一致左緣／基線 | 以 offset/距離評分，不可強迫主體置中 |
| GRID-007 | soft | 區塊最小間距 = 短邊 0.02；初始 0.025 | 文字間距遵循實際 glyph box，不以看不見的容器框代替 |
| GRID-008 | advisory | 可使用非對稱、偏心及留白構圖 | 不應以 `center everything` 當 fallback |
| GRID-009 | hard | 輸出像素座標必須 deterministic | 相同尺寸、字型、素材及 seed 的結果一致 |

## 計算
`shortSidePx = min(width,height)`；`safePx = shortSidePx * safeMarginRatio`；`safeX = safePx / width`；`safeY = safePx / height`。欄寬在像素域計算：`(width - 2*safePx - (n-1)*gutterPx)/n`，再轉 normalized。不得把 6% 短邊直接當 x/y 兩軸的相同百分比。

## 配置策略
先產生 2–4 個候選：左文右圖、上文下圖、斜對角、不對稱編輯風；依內容長度與主體長寬比淘汰無效版面。不應把候選都限制成相同模板；reference 可決定特別的 key lines。

## 測試
1200×1500、1080×1080、1920×1080、2480×3508；測試安全邊界像素換算、欄寬加總、不同 seed 穩定性與 reference layout。
