# FroGPT Poster — Design Guidelines Master Implementation Spec v1.0

> 本檔案是一份可直接貼給 ChatGPT Work / GitHub Copilot 的實作任務書。請依據 `FILE START` / `FILE END` 邊界，建立六份獨立的 Markdown 規範；再由其建立機器可讀 JSON、JSON Schema 與程式模組。**不得將本總檔視為最終程式執行規則，也不得僅把 Markdown 原文交給模型當 prompt。**
>
> 狀態：Proposed / 待專案驗證；規範版本 1.0.0；日期 2026-10-20。

## A. 給實作代理的總指令

1. 先讀取既有 FroGPT Poster repo、`prepare_poster`、資料模型、Renderer、現有幾何／字型／素材接口及測試。以現有實際語言和工具鏈實作，**保留既有 MCP entry、API 契約、素材上傳與原流程相容性**，除非有測試證明需變更。不得僅為套用本規範而重寫所有程式。
2. 建立 `design-guidelines/` 下的 **恰好六份規範 Markdown**，內容取自下列六段 FILE 區塊。可以新增機器可讀規範檔、schema、source registry、測試、程式模組與 README；但不要將六份合成單一檔案。
3. 把六份 Markdown 的 `Rule ID` 整理為 `design-guidelines/poster-rules.v1.json`，再建立 `design-guidelines/poster-rules.schema.json`（JSON Schema Draft 2020-12）。每條規則必須有 `id`, `category`, `severity` (`hard`/`soft`/`advisory`), `enabled`, `appliesTo`, `default`, `range`（若適用）, `unit`, `source`, `rationale`, `overridePolicy` (`never`/`reference`/`user`/`style`/`conditional`)；JSON 只能有可序列化的資料，不含程式碼、函數或註解。非數值規則允許省略 `range`，但要定義 `operator` / `choices` 或 `config`。所有 JSON 值必須與文件的規則表一致。
4. 建立 `DesignRuleLoader`（版本與 schema 驗證）、`DesignTokenResolver`（融合 preset / reference / user）、`LayoutPlanner`（候選版面）、`LayoutValidator`（硬限制與軟警告）、`LayoutScorer`（初版可僅保留可測量項目）、`CompositionAdapter`（輸出既有 renderer 可接受的模型）。實際路徑依專案架構調整，避免與既有模組功能重複。
5. 繪圖模型：Poster = Background（必須；solid/gradient/image） + Subject（必須；user/AI） + Typography（必須；有有效文字內容） + Geometry（可選，預設空陣列）。**Geometry 在 Subject 下層、Background 上層**，除非既有系統能明確管理不同 z-index；不得讓幾何遮蔽重要文字。
6. GPT 做藝術指導與生成候選設計；API 做文字精確測量、座標換算、素材合成、禁區判斷與渲染。不可把 GPT 猜測的文字 bounding box 當作真實字型測量。
7. 所有比例類參數以 normalized coordinates (0–1) 表示，x/y 的原點左上，bbox 為 `{x,y,width,height}`；字級使用 `fontSizeRelativeToShortSide`，字距／行高另有專用單位；輸出前換算至實際 canvas px。**不要假設正方形海報**。
8. 約束優先序：資料正確性／素材授權／必填圖層／不可裁切／必要可讀性 > 使用者明示的安全需求 > 使用者指定風格及參考設計 > 風格 preset > 預設 soft rules。參考設計不可繞過硬性限制；藝術性越界只允許非重要幾何與明示的裝飾性文字，且需留下診斷。
9. 禁止 silent mutation：修正字級、換行、坐標、色彩時回傳 `diagnostics`，含 `ruleId`, `level`, `elementId`, `original`, `resolved`, `reason`。若無法遵守硬規則，回傳可判別錯誤，不得輸出聲稱成功的錯誤海報。
10. 測試需至少涵蓋：直式 4:5、方形 1:1、橫式 16:9、A4；中文繁體、英文混排；極長標題；低對比背景；透明主體／不透明主體；無幾何；有／無參考設計；無法量測字型；風格覆蓋不應跳過硬限制。保留原有端到端測試並提供 migration guide。
11. 先提交單一 Master Spec + 六 Markdown + JSON + Schema + 測試範本／實作；若專案現有程式碼不適合在同次變更內安全改造，先提供 feature flag 與漸進整合，切勿破壞 `prepare_poster`。
12. 交付時列出新建與變更的路徑、測試結果、尚未解決風險、授權紀錄及實際使用方式。不要在沒有授權的情況下複製品牌視覺素材、設計圖或字體。

## B. 核心資料契約（必須採納或建立相容 Adapter）

設計層資料與可渲染層資料必須分開：`DesignIntent`（偏好／參考）→ `ResolvedDesignTokens`（已確認規則）→ `LayoutCandidate`（元素區塊）→ `ValidatedComposition`（含精確量測）→ `PosterRenderOutput`。`LayoutCandidate` 不應混同最後成品。

建議最小結構（示意；實作者需提供正式型別與 schema）：

```json
{
  "version": "1.0.0",
  "canvas": {"width": 1200, "height": 1500, "unit": "px"},
  "background": {"type": "solid", "color": "#F5F1E8"},
  "subject": {"source": "user", "assetRef": "opaque-asset-ref", "fit": "contain"},
  "geometry": [],
  "typography": [
    {"id": "title", "role": "headline", "text": "厚切三明治", "fontFamily": "resolved-font-id", "fontSizeRelativeToShortSide": 0.10, "box": {"x": 0.07, "y": 0.07, "width": 0.78, "height": 0.18}}
  ],
  "stylePreset": "editorial",
  "reference": null
}
```

- `assetRef` 為既有上傳流程回傳的 opaque identifier，非使用者本機路徑；只使用可驗證的授權圖片。文字不得預先燒進主體素材。
- 各參數必須標示 hard/soft；設計意圖參數可由 GPT 決定，安全限制由 API 決定。
- `Typography` 必要是指至少一段非空字串且能成功量測與渲染，不是一定有四個固定欄位。
- 設定檔遵循 SemVer；未知 ruleId、單位混用、負 bbox、非有限數、無效 HEX、range 反轉必須驗證失敗。

## C. 六份文件的生成邊界

<!-- FILE START: design-guidelines/01-typography.md -->
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
<!-- FILE END -->

<!-- FILE START: design-guidelines/02-grid-layout.md -->
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
<!-- FILE END -->

<!-- FILE START: design-guidelines/03-visual-hierarchy.md -->
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
<!-- FILE END -->

<!-- FILE START: design-guidelines/04-color-theory.md -->
# 04 — Color Theory / 配色與可讀性

## 目的與依據
結合 Carbon 的色彩 token 方法及 WCAG 2.2 對一般文字 4.5:1、大型文字 3:1 的網頁可讀性參考。這不是聲稱印刷品必須符合 WCAG；海報核心資訊採可讀性保護。

## 規則
| Rule ID | 等級 | 初始值 / 條件 | 實作要求 |
|---|---|---|---|
| COLOR-001 | hard | 所有輸入色碼可解析且在有效色域 | 支援標準 HEX 或既有 renderer 的色彩格式，無效值拒絕 |
| COLOR-002 | hard | 重要文字與實際背後區域有可讀性 | 預設一般文字 ≥4.5:1、大字 ≥3:1；在非均勻背景按文字占用區採樣，必要時加底板／陰影／改位置 |
| COLOR-003 | soft | 初始 1 主色 + 1 輔色 + 1 強調色 + 中性色 | 不強制所有海報都剛好三色；單色／多彩風格可覆蓋 |
| COLOR-004 | soft | 強調色覆蓋率初始 ≤0.20 | 只計前景重點色，不對照片像素做簡單面積禁令 |
| COLOR-005 | soft | 可從主體或參考萃取 palette | 設計模型可調 hue / lightness / saturation，避免照抄整張參考圖 |
| COLOR-006 | advisory | 記錄 palette 的來源及色彩角色 | `background`, `foreground`, `accent`, `support` 等語意 token |
| COLOR-007 | hard | alpha compositing 後驗證對比 | 透明材質、陰影或文字底色須以實際 composited pixel 計算 |

## 演算法
1. 在 sRGB 合成背景與遮罩，再線性化色彩計算相對亮度；contrast `(Llighter+0.05)/(Ldarker+0.05)`。
2. 漸層／相片底圖採取 glyph box 取樣（可加 padding），評估最差對比及低對比覆蓋比例。設定保守閾值，與單色背景算法區分。
3. 若不合格，依序嘗試移位、局部半透明底板、改文字顏色；若使用者禁止底板或改色，回報 validator error 而不是隱藏問題。
4. 禁止僅用 RGB 數值直接相減當對比率；不可把主體鮮明等同文字可讀。

## 測試
白底黑字、藍底白字、低對比同色相、透明覆蓋、攝影背景高亮點、局部暗區、漸層、參考主色覆蓋。
<!-- FILE END -->

<!-- FILE START: design-guidelines/05-composition.md -->
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
<!-- FILE END -->

<!-- FILE START: design-guidelines/06-validation.md -->
# 06 — Validation / 合規、碰撞、評分與修復

## 目的
將主觀美感與必須滿足的渲染安全性分開。**所有 hard rules 應在正式輸出前驗證**；soft 不合格可排序候選或提出 warning，不應直接抹平設計特色。

## 規則
| Rule ID | 等級 | 初始值 / 條件 | 實作要求 |
|---|---|---|---|
| VAL-001 | hard | 檢查全部啟用的 hard rules | 任一不可修正錯誤阻止成功輸出 |
| VAL-002 | hard | 重要文字與禁止遮蔽區無碰撞 | 用 glyph/alpha mask + protection zones，非光看 bbox |
| VAL-003 | hard | 渲染後對文字完整性比對 | 輸入文字與渲染文字一致，斷行不改原意、不可少字 |
| VAL-004 | hard | 素材授權、來源、字型可用及可解碼已驗證 | 無法證實時產生具體錯誤 |
| VAL-005 | soft | 候選方案使用可解釋分數 | 權重：hierarchy 25 / whitespace 20 / interaction 20 / alignment 15 / color 10 / reference 10，合計 100，屬實驗初始值 |
| VAL-006 | soft | 生成候選 2–4 個並選有效方案 | 先過 hard gate 再計 soft score；不是嘗試無上限重生 |
| VAL-007 | hard | correction loop 最多 2 輪 | 明確終止，避免過度消耗模型／API；必要回傳失敗與診斷 |
| VAL-008 | hard | diagnostics 可追溯 | 至少輸出 ruleId, severity, elementId, before, after, reason |
| VAL-009 | advisory | 保留 visual-review hook | 允許人工或視覺模型提出建議，但不得偽稱分數為設計品質真值 |

## Validator 執行次序
1. JSON Schema／版本／必填欄位與素材來源。
2. 畫板、字型載入、文字 glyph metrics、語言和 fallback。
3. canvas 安全邊界、文本完整性、碰撞、實際 composited 文字對比。
4. 若 hard violation 可修復，依可解釋策略執行最多 2 輪（挪動 → 換行 → 調整字級／色彩／文字底板）；再次驗證。
5. 只對合格 candidate 做 soft scoring；若分數相近則偏好改動較少且參考意圖保留較多者。
6. 回傳 `{ok, designVersion, result?, scores?, diagnostics[], errors[]}`。失敗時 `ok:false`，保留可測量的原因。

## 錯誤碼示例
`POSTER_MISSING_LAYER`, `ASSET_UNREADABLE`, `ASSET_LICENSE_UNKNOWN`, `FONT_UNAVAILABLE`, `TYPO_TEXT_OVERFLOW`, `LAYOUT_OUT_OF_BOUNDS`, `TEXT_SUBJECT_COLLISION`, `TEXT_CONTRAST_LOW`, `RULESET_INVALID`。

## 測試／驗收
- hard rule violation 不得回傳 `ok:true`；soft rule violation 可回傳 warning。
- A4/方形/橫直式場景不同畫布均通過；同輸入 deterministic。
- 無 geometry 海報合法；reference 不可繞過 hard gate；長字串不丟字。
- 每條 rule ID 至少有單元測試或明確 `notAutomaticallyTestable` 記錄。
- 文檔、JSON、Schema、程式使用的規則 ID 完全一致；CI 偵測 drift。
<!-- FILE END -->

## D. JSON 產出規範與範例

請建立 `poster-rules.v1.json`，完整包含上列六個文件中的 **全部 rule IDs**，不要只挑示例。以下僅示範資料格式：

```json
{
  "schemaVersion": "1.0.0",
  "coordinateSystem": "normalized-top-left",
  "units": {"relativeToShortSide": "min(canvas.width,canvas.height)", "normalized": "fraction-of-axis"},
  "rules": [
    {
      "id": "GRID-003", "category": "grid-layout", "severity": "soft",
      "enabled": true, "appliesTo": ["poster"], "default": 0.06,
      "range": {"min": 0.05, "max": 0.08}, "unit": "relativeToShortSide",
      "source": "FroGPT adaptation inspired by Carbon grid",
      "rationale": "Leave breathing room around important content",
      "overridePolicy": "style"
    },
    {
      "id": "COMP-002", "category": "composition", "severity": "hard",
      "enabled": true, "appliesTo": ["poster"], "default": true,
      "operator": "geometryMayBeAbsent", "unit": "boolean",
      "source": "FroGPT product requirement", "rationale": "Geometry is optional",
      "overridePolicy": "never"
    }
  ]
}
```

非標準值統一集中在 JSON `presets` 裡，建議初版 `minimal`, `editorial`, `bold-commercial`, `tech` 四個 presets。每種 preset 只能覆寫 soft rule 的合法 token；不能停用 hard rules。使用者／reference 覆寫要明確記錄來源，並在最終 `ResolvedDesignTokens` 中有來源優先序／合併歷程。

### 必需一致性檢查
- `node scripts/validate-design-rules.*` 或同等現有工具鏈：解析 JSON schema、確定 6 份 Markdown 的 Rule IDs 和 JSON 完全一致、不重複、severity/範圍相符、sources 有 URL 或 `FroGPT original`。
- JSON schema、rules JSON、TypeScript/Python 型別需從單一來源產生或用 CI 保證一致；不要有兩份可獨立漂移的 hardcoded 設定。
- renderer 使用傳入 `resolvedDesignTokens`，避免在程式碼其他地方再散落固定 `0.06`, `0.10`、`4.5` 等魔術數字。

## E. 接口與漸進改造

- `prepare_poster` 對外契約不得因新增規範破壞；若要調整型別，以 optional 欄位／adapter 過渡。
- `DesignResolver` 使用 JSON 中的 style presets 及 source provenance；`TypographyResolver` 只決定候選文字風格，精確文字測量由實際 renderer 或共享字型測量器進行。
- 可將 `LayoutValidator` 安排在渲染前與渲染後各執行一次：前者檢查邏輯／預估碰撞，後者檢查最終像素／glyph bounds，避免錯誤被輸出。
- 增加 feature flag（例如 `POSTER_DESIGN_RULES_V1`），可以回滾至既有流程，但停用新規範時也不能違反產品必要圖層／資料正確性。
- 繪圖素材生成不必被這個 task 自動觸發；本任務主要是設計規範與整合程式碼，測試使用可重現 fixtures。

## F. 驗收條件 (Definition of Done)

1. 存在六份指定 Markdown，逐段完整保留規則、公式、範例及測試規範。
2. `poster-rules.v1.json` **涵蓋六份文件所有 rule IDs**，`poster-rules.schema.json` 驗證通過。
3. 具備 rule loader、token resolver、layout validator（至少所有 hard rules 有可執行實作或標示清楚的阻擋狀態），以及 renderer adapter。
4. 測試可重現、CI 通過，且同一張正常海報在 feature flag 開關下未產生意外回歸。
5. 示範 4 張 fixtures（產品、純文字導向、照片背景、無幾何），附正常及失敗診斷 JSON。
6. 文檔列出 derived rule / 原創 rule 來源、依據與授權範圍；不打包第三方手冊或受限圖片。
7. 任何尚未實作的美感啟發式（如 optical balance / salience scoring）只能標示 `experimental` 或回傳未啟用，不可當成已驗證精準演算法。

## G. 參考閱讀與授權邊界（2026-10-20 查閱）

1. IBM Carbon — Typography: https://www.carbondesignsystem.com/building-blocks/foundations/typography/overview ；字級、字重、expressive type 與 token 結構作為概念參考。
2. IBM Carbon — 2x Grid: https://www.carbondesignsystem.com/building-blocks/foundations/2x-grid/overview ；網格、key lines、spacing 節奏作為概念參考。
3. IBM Carbon code: https://github.com/carbon-design-system/carbon ；程式碼 Apache-2.0，若直接使用應履行 license/notice 要求；網站文件、商標、字型與視覺素材應分別確認授權。
4. Grid System: https://github.com/dostevskii/grid-system ；專案標示 MIT；參考固定畫板、模組網格與 JSON 輸出方法，若直接複製程式碼需保留授權聲明。
5. USWDS Typography: https://designsystem.digital.gov/components/typography/ ；可讀性原則參考；個別素材/資源授權應另核對。
6. W3C WCAG 2.2 Contrast Minimum: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html ；一般文字 4.5:1、大字 3:1 係網頁參考值，**不是海報印刷法規**。

**來源標註策略**：上文具體海報百分比、評分權重、候選數、修復回合上限等均為 FroGPT v1 實驗性設計建議，不要在下游文件寫成 Carbon / USWDS / W3C 的官方數值。全部可在實作測試與視覺 review 後調整。
