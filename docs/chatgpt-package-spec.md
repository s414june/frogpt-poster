# OpenAI Tools 反 AI 感海報插件規格書（v0.3 草案）

## 1. 目標與背景
建立一個可給 GPT/Agent 直接呼叫的 OpenAI Tools 插件，改善「AI 感圖氾濫」問題。輸出海報時優先使用使用者提供的真實圖片（裁切 / 去背 / 構圖調整），只有在沒有可用真圖時才啟用 AI 生成圖片，並透過版面與字體策略讓整體視覺盡量接近一般設計海報美感。

## 2. 產品原則（強制）
1. **真圖優先**：只要有可用使用者圖片，不使用 AI 生圖取代主視覺。
2. **AI 僅備援**：僅在使用者未提供圖片或圖片不可用時才生成 AI 圖。
3. **設計一致性**：使用使用者提供的開源字型，統一字體階層、留白與色彩規範。
4. **可解釋決策**：每次輸出都需記錄圖像來源決策（user image / ai fallback）。

## 3. 範圍
### In Scope（v0.3）
- 建立套件骨架與核心模組邊界（圖片策略、版面排版、主流程）。
- 定義資料模型：輸入資產、版面設定、輸出結果、決策記錄。
- 建立「真圖優先、AI 備援」決策介面。
- 提供 OpenAI Tools function schema 與 tool handler。
- 支援文字檔（JSON）輸入與欄位驗證。
- 支援 inline JSON 請求、圖片 URL、圖片 base64（避免本機路徑依賴）。
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

## 6. 套件架構（目標）
- `gpt_package.types`：輸入輸出資料模型（海報請求、資產、結果）。
- `gpt_package.policy`：圖片來源決策（真圖優先邏輯）。
- `gpt_package.openai_tool`：OpenAI Tools schema 與 handler。
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
