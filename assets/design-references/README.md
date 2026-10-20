# 設計參考庫

這裡的圖只供設計靈感，不作為成品背景。Pexels 照片背景仍由 `reference_library_id` 選擇。

- `attributed/`：需要署名的設計稿。
- `original/`：我自己畫的設計稿，不需署名。

需要時會掃描對應資料夾中的 PNG/JPG/WebP，不啟動背景輪詢。
原創圖可直接放入，未寫 JSON 時自動以檔名產生 ID；需署名圖請加入該資料夾的 `manifest.json`：

```json
{
  "version": 1,
  "items": [
    {
      "id": "minimal-01",
      "file": "minimal-01.jpg",
      "title": "簡約海報",
      "tags": ["極簡", "深色"],
      "author": "作者名稱",
      "credit_label": "作者名稱／來源",
      "source_url": "https://example.com/design"
    }
  ]
}
```

`id` 與 `file` 必填；`attributed` 的 `author` 必填且不可為 Unknown。
`credit_label` 可省略，預設為作者；`original` 不會輸出署名。
圖片路徑相對於該分類目錄，不接受目錄以外的檔案。
目錄每次呼叫重新讀取，不使用記憶體快取；部署環境新增檔案仍需提交並部署。

呼叫 `list_design_references=true` 取得 ID、作者、標籤和預覽，
檢視後傳 `design_reference_ids=["attributed/minimal-01"]`。
也可以把欄位放入 `poster_request`。目錄維持空白時會回傳空陣列。
助理負責分析風格；API 只依 ID 管理來源與署名，不宣稱自動辨識設計風格。
必要署名與 Pexels 作者合併為一排，以「 · 」分隔、去重，
不標示哪個是設計參考、哪個是直接用圖。
署名框為半透明灰色（alpha=150/255），貼齊右上邊緣，無額外 padding 或外距；過長時縮小到能一排完整顯示，不截字。
