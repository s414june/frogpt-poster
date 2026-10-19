# OpenAI Tools 反 AI 感海報插件規格書（v0.3 草案）

## 1. 目標與背景
建立一個可給 GPT/Agent 直接呼叫的 OpenAI Tools 插件，改善「AI 感圖氾濫」問題。輸出海報時優先使用使用者提供的真實圖片（裁切 / 去背 / 構圖調整），只有在沒有可用真圖時才啟用 AI 生成圖片，並透過版面與字體策略讓整體視覺盡量接近一般設計海報美感。

## 2. 產品原則（強制）
1. **真圖優先**：只要有可用使用者圖片，不使用 AI 生圖取代主視覺。
2. **AI 僅備援**：僅在使用者未提供圖片或圖片不可用時才生成 AI 圖。
3. **設計一致性**：使用使用者提供的開源字型，統一字體階層、留白與色彩規範。
4. **可解釋決策**：每次輸出都需記錄圖像來源決策（user image / ai fallback）。
5. **首輪強制問卷**：首次海報請求必須先走 intake 問卷；問卷完成後同一輪工作不重複提問。
   - 透過 `intake_session_token` 記錄會話狀態，避免 client 反覆手動維護旗標。
6. **簡報感視覺預設**：優先純色/柔和漸層背景，幾何元素最小化，主體置前。
7. **文字版面規則**：標題與副標置中為主，且盡量靠近視覺中心；內文/宣傳語置於主體下方並置中，不使用文字底色框。
8. **字型策略**：黑體/無襯線優先；標題可使用較粗字重（regular/bold 以上），內文維持一致字型與字重，進階調整優先改字重再改字體家族。
9. **色彩來源策略**：可由使用者或 GPT 提供的圖片自動吸色；若使用者顯式指定色碼，優先採用顯式設定。
10. **可讀性對比**：標題與內文需對背景保持足夠明度對比，文字色需自動在深/淺方案中選擇以確保可讀。
11. **主體遮罩樣式**：主體優先維持原比例，不做變形；遮罩效果採「單選一」策略（`rounded` 或 `feather`）。邊框預設關閉，僅在使用者要求時啟用，建議 8px~20px。
12. **幾何裝飾策略**：在「單色或漸層背景 + 單一主體」情境下，除非使用者關閉，預設加入幾何裝飾，並在「主體附近」或「海報邊緣」二擇一策略。幾何不沿主體背景邊緣生長，而是獨立生成；可擴展到較寬分布，但仍需以主體或邊緣為主要出發點，避免完全隨機散佈。
13. **不透明度規則**：幾何元素不得使用半透明（禁止 1%~99% 透明度）；主體遮罩採單一樣式，不疊加多種效果。
14. **幾何色彩規則**：幾何色彩優先從主體吸色，明度應與背景接近（同向偏深或偏淺，但避免極端）；文字明度則與背景/幾何採反向策略以確保可讀性。
15. **幾何色相與彩度規則**：幾何色相種類上限為 3，且所有幾何共用同一套色彩邏輯；預設需與背景協調（色相接近或彩度接近）。僅當使用者明確要求跳色/撞色/對比色時，才允許補入對比色系。
16. **幾何形狀限制**：禁止橢圓形（oval/ellipse）幾何；圓形元素僅允許正圓。  
17. **幾何可見性下限**：即使需與背景呼應，幾何色仍須保留最小色差，不可與背景過於接近而失去辨識度。

## 3. 範圍
### In Scope（v0.3）
- 建立套件骨架與核心模組邊界（圖片策略、版面排版、主流程）。
- 定義資料模型：輸入資產、版面設定、輸出結果、決策記錄。
- 建立「真圖優先、AI 備援」決策介面。
- 提供 OpenAI Tools function schema 與 tool handler。
- 支援文字檔（JSON）輸入與欄位驗證。
- 支援 inline JSON 請求、圖片 URL、圖片 base64（避免本機路徑依賴）。
- 支援參考圖流程（reference image URLs、Pexels API query），並可在必要時直接作為 fallback 主視覺。
- 支援「GPT 先生成背景草稿」作為參考圖（base64），再套開源字型完成海報。
- 預設繞過自動 Pexels 抓圖，改走手動圖庫流程；保留 `PEXELS_API_KEY` 與 `auto_pexels_fallback` 開關供後續啟用。
- 未指定字型路徑時，自動掃描專案 `assets/fonts` 字型資料夾。
- 預留去背、裁切、字型注入與美感調教的擴充點。

### Out of Scope（v0.2）
- 完整影像模型訓練與美學自動評分模型。
- GUI 編輯器與雲端部署。
- 供應商綁定（特定 AI provider 的完整串接）。

## 4. 主要使用者情境
1. 使用者提供活動文案 + 真實照片 + 開源字型，系統輸出海報。
2. 使用者只提供文案與字型，系統在缺圖時自動啟用 AI 備援圖。
3. 團隊可追蹤每張海報是否使用 AI 圖與其原因。

## 5. 核心流程（技術流程）
1. **輸入驗證**：檢查文案、圖片、字型與尺寸設定。
2. **文字檔載入**：可由 tool 參數指定 JSON 文字檔，再用直接參數覆寫。
3. **字型來源決策**：若未提供 `open_source_font_paths`，自動掃描 `assets/fonts`。
4. **素材決策**：執行 `PosterPolicy`，判斷 `USER_IMAGE` 或 `AI_FALLBACK`。
5. **圖片前處理**：若為真圖，執行裁切/去背/比例調整。
6. **版面合成**：套用字型、文字階層、留白規則、色彩策略輸出海報。
7. **決策落地**：回傳輸出檔案與來源決策資訊，利於稽核與調教。
8. **跨端輸出**：回傳 `output_image_base64` 供 Web/行動端直接顯示。
9. **參考圖合規**：第三方圖源優先走官方 API，回傳來源 credit 與合規提醒。
10. **圖片優先序**：使用者圖片 > GPT 背景參考圖 > Pexels 參考圖 > 內建 fallback。
11. **無圖雙階段**：先回傳 `needs_background_generation` 與無字背景提示詞，再以 `generated_background_base64` 重試排版。
12. **無字背景確認**：使用 `generated_background_base64` 重試時需附 `generated_background_text_free_confirmed=true`，否則維持 `needs_background_generation`，避免把含文字/Logo/浮水印背景誤當可排版底圖。
15. **引用標註**：若背景採用參考圖（含 Pexels/本地圖庫），海報角落需加上簡短來源標註（如 `Name/Pexels`）。
16. **主體合成**：可額外傳入去背主體圖（`subject_image_*`）疊加到背景前景區，保留背景引用不重造。
17. **背景模式**：支援 `auto|solid|gradient|reference`，並在首輪 intake 問卷蒐集偏好。
18. **配色自動化**：未顯式指定配色時，從可用圖片（使用者圖、主體圖、參考圖、GPT 背景草稿）抽取主/輔/強調色。
19. **背景色偏好映射**：可透過 `background_color_hint`（例如 `blue light`、`暖橘`、`深綠`）指定背景色語意；系統優先從圖片中挑近似色，若無同色系則以圖片色做彩度/明度調整。

## 6. 套件架構（目標）
- `gpt_package.types`：輸入輸出資料模型（海報請求、資產、結果）。
- `gpt_package.policy`：圖片來源決策（真圖優先邏輯）。
- `gpt_package.openai_tool`：OpenAI Tools schema 與 handler。
- `gpt_package.reference_images`：參考圖下載、Pexels API 查詢、色盤抽取。
- `gpt_package.text_input`：文字檔（JSON）載入。
- `gpt_package.font_discovery`：本地字型自動掃描（`assets/fonts`）。
- `gpt_package.validation`：請求欄位與路徑驗證。
- `gpt_package.image_pipeline`：裁切、去背與前處理擴充介面。
- `gpt_package.typography`：開源字型與排版策略擴充介面。
- `gpt_package.client`：高階入口 `PosterGenerator`。
- `gpt_package.errors`：驗證錯誤、資產錯誤、產生流程錯誤。

## 7. Tool API 草案（v0.3）
```python
from gpt_package import build_tool_definition, handle_tool_call

schema = build_tool_definition()
result = handle_tool_call({"poster_text_file": "examples\\uat\\poster-input.json"})
print(result["ok"], result["decision"]["image_source"])
```

> 註：v0.3 已完成「插件可呼叫 + 驗證 + 基本海報渲染」，後續版本持續優化美學與 AI 備援品質。

## 8. 非功能需求
- **可維護性**：模組職責清楚，流程與策略可替換。
- **可測試性**：決策邏輯獨立可單元測試。
- **可擴充性**：影像與排版引擎可插拔。
- **可追蹤性**：每次輸出保留決策紀錄與原因。
- **合規性**：第三方圖源記錄來源與攝影師資訊，避免 standalone 再散布。

## 11. 第三方圖源法規備註（Pexels）
- 應使用官方 API 取圖，避免 scraping/data extraction 方式抓站。
- 不得以 Standalone 形式轉售或再散布來源圖。
- 建議保留顯著來源連結與攝影師 credit。
- 參考：  
  - https://www.pexels.com/license/  
  - https://www.pexels.com/terms-of-service/  
  - https://www.pexels.com/api/documentation/

## 9. 驗收標準（v0.3）
- 專案可安裝，且可 `import gpt_package`。
- OpenAI function schema 可輸出，tool handler 可執行。
- 文字檔 JSON 載入可用，且欄位驗證會阻擋不合法輸入。
- `PosterPolicy` 對「有圖 / 無圖」可回傳正確來源決策。
- 文件明確描述真圖優先與 AI 備援規則。

## 10. 里程碑
1. **M1：插件骨架與規格**（本次）  
   建立 OpenAI Tools 介面、資料模型、文字檔與驗證。
2. **M2：圖片前處理實作**  
   接入裁切、去背、尺寸適配。
3. **M3：排版美感調教**  
   完成字體階層、留白、配色規則與模板系統。
4. **M4：AI 備援與品質迭代**  
   接入 AI 生成備援與風格一致性優化。
