# 05 — Composition / 主體、背景、文字及幾何

## 目的
統一所有素材來源，使海報只有一套可預測的組合及渲染流程。參考風格是引導，不是像素級複製。

## 規則
| Rule ID | 等級 | 初始值 / 條件 | 實作要求 |
|---|---|---|---|
| COMP-001 | hard | Background / Subject / Typography 三者必須有效 | Background = solid/gradient/image；Subject = user/AI；Typography = 有效文字 |
| COMP-002 | hard | Geometry 可完全沒有 | 不得因 geometry 缺席而要求補圖或報錯 |
| COMP-003 | hard | 預設圖層序：background < geometry < subject < typography | 使用明確 `zIndex`，不可由輸入上傳先後決定 |
| COMP-004 | hard | 不得把文字當成主體圖片的一部分渲染 | 除非明確要求保留使用者原圖中的既有文字；新增文字一定用 Typography |
| COMP-005 | soft | Subject 寬度初始 0.35–0.70 × canvasWidth | 不是硬限制；更高或更窄的產品可突破，保護主體重要部分 |
| COMP-006 | soft | 主體與文字的最小光學間距 = 短邊 0.025 | 使用可見 alpha mask／非透明輪廓計算，不僅看影像矩形 bbox |
| COMP-007 | soft | geometry group 預設 0–3 組 | 若遮擋主體／搶奪焦點，優先移除；純黑幾何、粗細可由 style 指定 |
| COMP-008 | hard | asset 必須能由遠端渲染器取得且可解碼 | 僅接受實際 bytes / 已儲存 assetRef / 允許的 URL 來源，不傳本機 sandbox 路徑 |
| COMP-009 | advisory | reference 只抽取 abstract tokens | 擷取結構、配色策略、留白、字級關係；避免重製商標／獨特設計元素 |
| COMP-010 | hard | 不得未授權使用第三方受限素材 | 記錄來源、授權、作者要求之署名；授權不明應拒用或換素材 |

## Composition pipeline
`PosterRequestResolver → BackgroundResolver / SubjectResolver / DesignResolver / TypographyResolver → LayoutPlanner → LayoutValidator → CompositionRenderer → QualityDiagnostics`。
各 Resolver 只負責解析來源／意圖，不在分支中獨立輸出最終海報。透明主體圖片若要搭配底圖，必須保留 alpha；不能先自動烘焙白色背景。

## Reference workflow
使用者提供設計參考時：先解析高層 `designSignature`（alignment, hierarchy, palette roles, density, geometric language），再產生可選變體；必須允許主配色或區塊相對位置與原參考不同。無參考時由 GPT 選擇 style preset，並由硬性規則校驗。

## 測試
純色底／漸層底／圖片底；使用者上傳／AI 生成主體；無幾何／有幾何；透明邊緣；長條形產品；參考海報配色變體；重複渲染一致。
