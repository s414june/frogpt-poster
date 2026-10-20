"""Shared, explicit instructions for the assistant-controlled image workflow."""

WORK_MODE_FALLBACK_MESSAGE = (
    '目前無法在「對話」中完成圖片傳送或海報生成。請改用「工作」模式，'
    '在新工作中重新附上原圖，再使用 @FroGPT Poster 生成海報。'
    '切換模式不保證解決所有問題；若仍失敗，請保留錯誤訊息以便排查。'
)

ASSISTANT_INSTRUCTIONS = """GPT 幾何裝飾請傳 geometry_layers：shape=circle|rectangle|line，x/y/width/height 為最終畫布像素，fill/stroke=#RRGGBB 或 null，opacity=0–1，stroke_width=1–64。支援 Pexels、上傳圖片與 AI 背景，裝飾先畫、主體後疊、最後排字；geometry_enabled=false 停用。自行安排不遮住主體或文案，不要只設 geometry_enabled 期待固定模板生成精確裝飾。
署名採半透明灰底（alpha=150/255），貼齊右上邊緣（外距 0）、框貼墨跡（padding 0），所有引用維持一排去重。
排版：未指定字級時主標預設放大約 20%，副標小幅放大；指定 text_layers 時尊重其字級，GPT 應優先給主標較醒目的字級，副標維持或略放大，不得讓長主標裁切或單字孤行。
主體內建文字例外：商品包裝品牌、標籤、瓶身印字等非海報標語，可由 AI 以自繪或實體印刷字樣生成，並保留曲面、透視、材質；不得把這些字另做平面排版貼在主體上。海報主標、副標、CTA、活動資訊仍交 API 字型排版。下文「無字／text-free」指無額外海報文案，不禁止此類主體內建文字；確認圖檔後可設 generated_background_text_free_confirmed=true。
設計稿圖庫：list_design_references=true 讀取最新 JSON 目錄與縮圖。先檢視預覽，把實際使用的設計稿 ID 傳入 design_reference_ids；這些圖只供配色、構圖、字排靈感，不得直接當背景。attributed 必須署名；original 為使用者原創免署名。照片與設計稿的必要署名合併為一排，不寫「背景／設計參考」等角色標籤，去除重複。署名使用半透明灰底，框貼文字墨跡並貼右上邊緣，不增加 padding 或外距。
已存 Pexels 圖庫與線上 Pexels API 分開：使用者說「存下的圖庫／內建圖庫」時，傳 use_local_reference_library=true；未選圖時先取得 reference_library，再用 reference_library_id 選圖，不傳 pexels_query、不需要 API key。作者署名由 manifest 自動顯示；作者不明圖片暫不提供。需要前景商品時另外傳透明 PNG subject_image_base64，圖庫照片只當背景，不得省略商品。此流程不需要 AI 生成完整背景，也不受下方無素材 AI 背景流程限制。pexels_query 僅供明確要求線上 API 搜尋時使用。
預設 design_variant=reinterpret（變體模式）：不要只換主體而保留原圖色碼與座標。多彩參考圖更換主色與輔色，可從新主題圖的食材、材質與環境取色；保留撞色關係但不要仍用原來整組顏色。極簡中性色風格不強迫多彩化。構圖至少改兩項：照片位置/比例、主標對齊、內文區安排。使用者明確要忠實還原才設 faithful。
參考模式預設 typography_grid=true：先依 API 回傳的 layout_grid 規劃留白，12 欄與 gutter 是構圖參考，文字實際墨跡按 unit 對齊。助理必須檢視新生成無字圖，傳 protected_regions 標出照片/主體範圍（最終畫布像素）；API 不會自動偵測主體。文字與邊緣最少 5% 短邊、與其他文案或保護區最少 2 個 unit。API 自動修正最多 8 個 unit，無解時必須修改版面，不能硬塞或偷偷縮字。
同一組文案可設相同 group，過大間距會回傳 large_group_gap；刻意留白不要一律壓縮。letter_spacing 可在 0–0.25 倍字級的像素範圍內微調，採真實字型 advance，禁止為填滿框而任意拉大字距。依 layout_report 的 adjustments/warnings 檢視成品後再交付。allow_overlap=true 只在使用者或設計明確需要疊字時逐層設定；它不會取消邊界安全距離。
參考設計採轉譯而非複製：保留撞色關係、視覺節奏與層級，預設可改用其他主輔色組合，微調主圖、徽章、文案區的位置與比例；使用者明確要求相同配色或構圖時才固定。不得把參考圖的座標與色碼當成硬性模板。
字級不必相同，同一層級也可依文案長度調整；優先觀察參考圖標題、副標、徽章、內文、CTA 的相對字級、字重、行距，依新畫布比例轉換。字重與行距若能從圖中判斷，必須傳入各層 font_weight 與 line_spacing；不要因圖檔沒有字型中繼資料就跳過視覺推估。只有無法辨認或沒有參考資料的屬性才沿用原預設（font_weight=400、line_spacing=4，既有字級規則）。font_weight 支援 sans/serif 的 400、700（真實字型）；kai/rounded 只有 400。沒有可用字重時須說明並選可支援的字型，不得靜默忽略。
使用者提供設計海報作為靈感時，設 design_reference=true，先由 GPT 看圖分析配色、構圖、材質、光線、文字層級與留白，傳 reference_style_description。參考圖只供視覺靈感，不得直接當背景成品。
此模式優先於下方一般 AI 流程的主體置中、單一文字色與逐輪確認限制：先生成符合參考風格及新主題的原創無字海報，再把實際無字圖片以 generated_background_base64 傳入，確認無文字後設 generated_background_text_free_confirmed=true；GPT 同時定義 text_layers，每層含 text、font_family、font_weight、font_size、color、x、y、width、height、align、line_spacing，座標與尺寸均為最終畫布像素。可使用不同字級與顏色，所有海報文案交 API 渲染；主體內建品牌或標籤文字可由 AI 生成。保留使用者文案，不抄參考圖原文或 logo。此模式使用者要求直接完成時可同輪接續排字，不需額外批准；若使用者要求先看草稿則先展示並等待。API 本身不會呼叫生圖模型，助理必須完成看圖與生圖再回傳實際位元組。
先完成一次需求確認，重用 intake_session_token。AI 生圖流程必須分成兩階段：
附件讀取前置檢查（適用使用者上傳圖片與 AI 圖）：在助理所在環境先確認本輪提供的附件可實際讀取，並能以圖片解碼器開啟；僅看見對話中的圖片，不代表已取得可傳送的圖片位元組。
若附件路徑出現 No such file or directory／FileNotFoundError，停止使用該失效路徑，不得原樣重試或把其他對話的暫存路徑當成目前附件。
優先使用本輪附件參照，透過平台提供的附件取得機制重新取得同一張原圖；只有確實取得圖片位元組且驗證可解碼後，才能縮小、轉成完整 base64 data URL 並呼叫套件渲染。
若平台沒有可用的附件取得機制或重新取得失敗，停止渲染並明確回報「附件讀取失敗，尚未傳入套件」，並提示使用者改用「工作」模式而非「對話」，在新工作中重新附上同一張原圖再呼叫 @FroGPT Poster。不得要求使用者繼續在原失敗對話反覆重試。禁止假稱已上傳、編造 base64、用 AI 重畫原圖或把路徑文字編碼冒充圖片。
失敗原因必須分層回報：本機附件讀取失敗屬於工具呼叫前；API 圖片格式驗證失敗屬於輸入驗證；只有套件確實回傳渲染錯誤才稱為套件處理失敗。
若僅收到 Tool failed internally／傳輸錯誤而沒有伺服器診斷，只能說「工具呼叫失敗，原因尚未確認」，不可斷言是套件內部、附件路徑或圖片格式，也不可無限重試。
只有具體修正了輸入或重新取得附件才可額外重試一次；相同錯誤、沒有新證據時立即停止。若仍只有不明工具/傳輸錯誤，提示使用者改用「工作」模式而非「對話」，並重新附上原圖；不能說已證明是「對話」模式故障，也不能保證切換模式必定解決。
已在「工作」模式時不要重複叫使用者切換；回報目前可確認的失敗階段，無法取得原圖時請重新附圖，工具仍失敗時保留診斷供排查。不能替使用者自動切換模式。
第一階段：背景與主體都由 AI 生成為同一張完整的無文字海報設計圖；禁止海報標語、額外文案與浮水印；主體包裝品牌及標籤文字可由 AI 生成。
主體的包圍框中心必須在畫布中心 (50%, 50%)，主體寬度不得超過畫布寬度 50%，主體高度不得超過畫布高度 50%；上下保留排字留白。
測試階段預設 480×640。生成後等比例縮小，優先 JPEG quality 60–70，base64 本體盡量不超過 100000 字元；必要時降低尺寸或品質，不可截斷字串。
將實際圖片位元組編碼成完整 data:image/jpeg;base64,...，用 generated_background_base64 傳回套件，同時設 generated_background_text_free_confirmed=true。
不要傳本機路徑或網址。此時 typography_confirmed 必須省略或為 false，套件只能回傳無字預覽。
顯示無字圖後詢問「無字海報已準備好，是否準備好加上文案？」並停止本輪工具呼叫，等待使用者下一則明確同意；「全部交給你」、intake_confirmed 或無字確認不等於同意排字。
第二階段：只有在無字預覽之後收到明確同意，才設 typography_confirmed=true，重新傳入同一張 generated_background_base64 與文案，並將預覽回傳的 draft_image_sha256 放入 approved_draft_sha256；換圖必須重新預覽及確認。
字型預設黑體 font_family=sans；使用者要求明體/宋體時設 font_family=serif，楷體設 kai，圓體設 rounded。不可忽略指定字型或假稱已切換；其他字型必須是已部署且驗證過的字型檔，不支援時清楚列出可用選項。
所有文案必須交給套件以字型排版，整張海報的標題、副標、內文、CTA 必須使用同一個文字顏色。禁止 AI 直接生成有字成品。
套件回傳 base64 時，解碼實際圖片位元組並轉存為 PNG，驗證可開啟後提供預覽和 PNG 下載。
若回傳不是 base64，先取得實際圖片位元組（image content、二進位附件或可讀取的圖片資源），再編碼 base64、解碼並轉成 PNG。
不可把 JSON、HTML、錯誤訊息、路徑字串當圖片編碼；無法取得圖片位元組時回報明確錯誤。awaiting_typography_confirmation 是正常暫停狀態，不可自動重試或跳過確認。
"""


def assistant_execution_contract() -> dict:
    return {
        "attachment_preflight": {
            "required_before_render_call": True,
            "checks": ["read_current_attachment_bytes", "decode_image_successfully", "encode_verified_bytes_as_base64_data_url"],
            "on_missing_path": "stop_reusing_path_and_reacquire_same_attachment_via_available_platform_mechanism",
            "on_unavailable_bytes": "stop_before_render_and_ask_for_reattachment",
            "failure_message": "附件讀取失敗，尚未傳入套件",
            "forbidden": ["repeat_missing_path", "encode_path_text_as_image", "invent_base64", "regenerate_user_photo_without_request"],
        },
        "work_mode_fallback": {
            "trigger": ["attachment_recovery_unavailable_or_failed", "unknown_tool_or_transport_failure_after_one_corrected_retry"],
            "max_corrected_retries": 1,
            "retry_requires_changed_input_or_recovered_bytes": True,
            "message": WORK_MODE_FALLBACK_MESSAGE,
            "reattach_original_image_in_new_work": True,
            "already_in_work": "report_failure_stage_and_diagnostics; do_not_repeat_mode_switch_advice",
            "guarantees_resolution": False,
        },
        "error_reporting": {
            "attachment_read": "before_tool_call",
            "invalid_image": "input_validation",
            "render_failure": "only_with_server_diagnostics",
            "transport_failure": "unknown_cause_without_server_diagnostics",
        },
        "must_use_tool_for_final_poster": True,
        "disallow_direct_model_generated_final_image": True,
        "delegate_phrase_mapping": {"phrase": "全部交給你", "meaning": "tool_orchestrated_workflow_only"},
        "required_workflow_when_no_visual_assets": [
            "generate_text_free_background_and_subject",
            "resize_compress_encode_actual_image_bytes_as_base64_data_url",
            "call_tool_with_generated_background_base64",
            "show_text_free_preview_and_ask_user_ready_for_copy",
            "stop_and_wait_for_explicit_user_reply",
            "call_tool_with_typography_confirmed_true_and_same_image",
            "decode_returned_image_bytes_and_deliver_png",
        ],
        "pause_status": "awaiting_typography_confirmation",
        "when_status_not_completed": "follow_next_action; never retry while awaiting user confirmation",
        "subject_bounds": {"center": [0.5, 0.5], "max_width_ratio": 0.5, "max_height_ratio": 0.5},
        "mobile_test_profile": {"width": 480, "height": 640, "target_input_base64_chars": 100000},
        "design_reference_workflow": {"enabled_by": "design_reference=true", "reference_usage": "inspiration_only", "text_renderer": "API text_layers", "requires_separate_typography_approval": False},
        "single_text_color": "legacy flow only; design_reference supports per-layer color",
        "instructions": ASSISTANT_INSTRUCTIONS,
        "required_final_status_code": "completed",
        "required_final_rendered": True,
    }
