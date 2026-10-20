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
