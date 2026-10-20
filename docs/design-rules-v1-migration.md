# 設計規範 v1：實作與漸進導入

## 目前交付範圍

附檔完整保留在 `docs/design-guidelines-master-v1.md`；`design-guidelines/`
恰好六份 Markdown 與附檔 FILE 區段逐字一致。51 條規則已整理為
`poster-rules.v1.json`，附 Draft 2020-12 Schema、DesignIntent Schema、來源及測試覆蓋紀錄。

新流程：

`DesignIntent → DesignRuleLoader → DesignTokenResolver → LayoutPlanner → LayoutValidator → CompositionAdapter / 既有 ImagePipeline → PNG + design_report`。

這次是可選的漸進整合。預設 `POSTER_DESIGN_RULES_V1=false`，沿用既有 vNext；
單次呼叫傳 `design_rules_v1=true` 可啟用，或以環境變數對全部請求啟用。
不會因此新增 Function、複製字型或改動上傳端點。

## 呼叫方式

`prepare_poster`、附件、Base64 和 Blob refs 維持原介面。以下是**自己的素材**示例；
`rightsConfirmed` 需有真實權利依據，不能由 intake 或外傳批准推定：

```json
{
  "design_rules_v1": true,
  "title": "把日常，留給美好。",
  "body": "A SIMPLE DAILY RITUAL",
  "primary_color": "#F5F1E8",
  "geometry_enabled": false,
  "design_intent": {
    "version": "1.0.0",
    "stylePreset": "editorial",
    "assetProvenance": {
      "subject": {
        "source": "user",
        "license": "user-owned",
        "rightsConfirmed": true,
        "posterTextFree": true
      }
    },
    "typography": [
      {
        "id": "headline",
        "role": "headline",
        "text": "把日常，\n留給美好。",
        "fontFamily": "sans",
        "fontSizeRelativeToShortSide": 0.10,
        "lineHeight": 1.10,
        "color": "#111111",
        "box": {"x": 0.08, "y": 0.08, "width": 0.80, "height": 0.24}
      }
    ]
  }
}
```

另傳 `subject_image` 或 `asset_refs.subjects`。`posterTextFree` 表示沒有新增海報文案
燒進主體，原有商品包裝字樣可保留。AI 圖使用 `subject_source=ai_generated`，
仍要在檢視圖片後宣告 `assetProvenance.subject.posterTextFree=true`。

新設計層使用 normalized bbox；字級相對短邊、lineHeight 相對 font em、字距使用 em。
既有 `text_layers` 像素介面由 Adapter 轉換，不要求舊客戶端改寫；不要把兩種單位混用。
同時提供時，`design_intent.typography` 優先。只有一段非空文字也合法。

`subjectPosition` 可指定 normalized 主體區域；既有 `subject_position` 仍用像素。
有明確位置時不改成置中；未指定時產生三個候選，依硬限制及可量測分數挑選。
沒有有效候選便失敗，不會宣告完成或無限重生。

四個 preset：`minimal`、`editorial`、`bold-commercial`、`tech`。
`referenceOverrides` / `userOverrides` 以 Rule ID 覆寫 soft tokens；
優先序 default < preset < reference < user，完整記錄來源與 before/after。
未知 ID、錯誤單位、非有限數、反轉範圍、硬規則覆寫都失敗。

`allowColorRepair` 預設 true，允許改文字色；`allowBackdrop` 預設 false。
照片背景需要底板時可明確設 true；底板只加在通過主體／文字碰撞檢查的區域，
對比在 alpha 合成後再次驗證。修復總預算以每個文字元素最多兩輪為界；
測量換行不改原文，縮字、改色與底板都有 diagnostics。

## 已實作的檢查

- 固定版本／Schema／全部 51 個 ID／六份文件與總檔一致性；字型 OFL 紀錄檢查。
- 真實字型 cmap coverage，逐 run fallback；實際 Pillow advance、字形與墨跡外框。
- 中英混排折行、基本標點禁則、文字完整性、不裁切、文字行彼此重疊檢查。
- 四種畫板的短邊比例、不同 x/y safe margin、欄寬與 gutter 換算。
- 固定三種候選，無隨機重生；同輸入 PNG bytes 一致。
- 可見主體 alpha／保護區與文字 glyph mask 碰撞；全透明主體不算有效主體。
- sRGB 線性化對比，取 glyph 核心像素的最差對比；同時考慮背景、幾何、主體與透明度。
- 沒有授權紀錄或缺字／無法測量／越界／不可修復低對比時阻止成功。
- 嚴格模式的署名也經相同字型、對比與碰撞驗證，置於安全區；
  舊模式仍保留原有右上署名行為。

字型、透明 PNG 幾何、圖庫、Blob refs、Public Blob 上傳授權與診斷沿用既有系統。
嚴格模式要求獨立背景與主體；legacy 完整 draft 可繼續用舊流程，但不假稱已驗證為分離圖層。

## 明確限制

- 這不是圖像 OCR 或法律判定。使用者素材的權利與「沒有燒入新增文案」以來源證據／明示聲明
  為依據；缺聲明時阻擋，不能由上傳、intake 或助理猜測補成授權。
- 原有 Pexels manifest／作者記錄及字型 license reference 繼續使用；未新增第三方圖片或字型。
- 選定字型與 fallback 僅限已部署的註冊字型；不支援的 cmap／字元會回傳 FONT_UNAVAILABLE。
- optical balance、salience、語意斷詞、reference similarity、精準光學間距等仍是 experimental；
  不參與「客觀美感」評分。現有分數只使用可量測的對比與碰撞，保留人工 visual-review hook。
- 有些 soft tokens 僅保留為藝術指導資料，未自動執行；`rule-coverage.json` 與規則本身明列原因。
- 對比採保守最差取樣，可能拒絕視覺上可接受的攝影排版；不擅自放寬硬限制。
- 這次沒有驗證線上部署、ChatGPT 真實附件宿主流程或 Vercel 實際 bundle 大小。

## 示範與驗證

`examples/design-rules-v1/` 有產品、文字主導、照片背景、無幾何四張 PNG；
每張都有 request、成功 diagnostics 與失敗 diagnostics。產品圖是專案程式繪製的固定 fixture；
照片沿用 `pexels-167699`，作者 Lum3n，成品保留署名；不另外分發原始照片。

```bash
PYTHONPATH=src python scripts/validate_design_rules.py
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python scripts/design_rule_fixtures.py
PYTHONPATH=src python scripts/verify_blob_manifest.py
```

CI workflow：`.github/workflows/design-rules.yml`。原本 175 項測試保留，另加 27 項規範測試；
包含實際渲染 1200×1500、1080×1080、1920×1080、2480×3508，而非只測縮小畫板。
環境開關及單次關閉的回退測試比較實際 PNG 雜湊。

依賴只增加 `jsonschema==4.23.0` 與其相依套件；cmap 解析使用標準函式庫，未引入 fontTools。
新增 JSON 規範會隨 Function 部署；Markdown、報告與示例 PNG 排除於 Function。

MCP server metadata 版本更新為 0.4.1；部署後需重新掃描工具並在新對話確認
`design_rules_v1` / `design_intent` 欄位。設定檔版本是 1.0.0，與 MCP 版本分開。
本次變更保留於本機功能分支，尚未推送 main。
