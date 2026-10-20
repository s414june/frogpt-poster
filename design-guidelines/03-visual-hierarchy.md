# 03 — Visual Hierarchy / 視覺層級與留白

## 目的
讓觀看者快速識別主視覺、主標及輔助資訊。層級是設計偏好，不是永遠由產品或標題獨占焦點。

## 規則
| Rule ID | 等級 | 初始值 / 條件 | 實作要求 |
|---|---|---|---|
| HIER-001 | soft | 必須指定 `primaryFocus` = subject/headline | GPT 根據目的、文字量、reference 選擇；不強制哪個較大 |
| HIER-002 | soft | 畫面中明顯競爭的主要焦點預設不超過 2 個 | 可由實驗型 style preset 覆蓋 |
| HIER-003 | soft | subordinate text 與 primary focus 區分大小、權重或對比 | 不要求一定用不同字級，允許粗細與色彩實現 |
| HIER-004 | soft | 最小可見負空間偏好：10–30% 的非主要內容區域 | 只做密度診斷；不是強制空白面積，背景紋理不算前景佔用 |
| HIER-005 | soft | `opticalBalanceTolerance` 預設 0.12 | 以視覺質量估計（面積×對比×顯著性），分數僅做排序，不能宣稱客觀美學 |
| HIER-006 | advisory | 留白可以不均勻、主體可偏移 | 不應以完全幾何對稱代替視覺平衡 |

## 評估
`visualWeight ≈ relativeArea × contrastFactor × salienceFactor`；僅作可調整啟發式；須允許 visual QA/人工評閱推翻。視覺密度計算不得把整張背景算作密集前景，也不得用單一「空白百分比」判斷海報好壞。

## 策略
GPT 至少能選：subject-led, type-led, balanced, editorial-asymmetric；各策略僅修改 soft tokens。判定畫面擁擠時先減少可選幾何，其次調整資訊群組與留白，再重新安排文字；不得直接刪除文案。

## 測試
極簡無幾何、文字主導、產品主導、非置中、長標題、參考圖片故意偏重一側；不得全部被修正成中心對稱。
