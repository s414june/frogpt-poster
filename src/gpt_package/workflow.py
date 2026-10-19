"""Shared, explicit instructions for the assistant-controlled image workflow."""

ASSISTANT_INSTRUCTIONS = """先完成一次需求確認，重用 intake_session_token。AI 生圖流程必須分成兩階段：
附件讀取前置檢查（適用使用者上傳圖片與 AI 圖）：在助理所在環境先確認本輪提供的附件可實際讀取，並能以圖片解碼器開啟；僅看見對話中的圖片，不代表已取得可傳送的圖片位元組。
若附件路徑出現 No such file or directory／FileNotFoundError，停止使用該失效路徑，不得原樣重試或把其他對話的暫存路徑當成目前附件。
優先使用本輪附件參照，透過平台提供的附件取得機制重新取得同一張原圖；只有確實取得圖片位元組且驗證可解碼後，才能縮小、轉成完整 base64 data URL 並呼叫套件渲染。
若平台沒有可用的附件取得機制或重新取得失敗，停止渲染並明確回報「附件讀取失敗，尚未傳入套件」，再請使用者重新附圖。禁止假稱已上傳、編造 base64、用 AI 重畫原圖或把路徑文字編碼冒充圖片。
失敗原因必須分層回報：本機附件讀取失敗屬於工具呼叫前；API 圖片格式驗證失敗屬於輸入驗證；只有套件確實回傳渲染錯誤才稱為套件處理失敗。
若僅收到 Tool failed internally／傳輸錯誤而沒有伺服器診斷，只能說「工具呼叫失敗，原因尚未確認」，不可斷言是套件內部、附件路徑或圖片格式，也不可無限重試。
第一階段：背景與主體都由 AI 生成為同一張完整的無文字海報設計圖；禁止文字、字母、數字、logo、浮水印。
主體的包圍框中心必須在畫布中心 (50%, 50%)，主體寬度不得超過畫布寬度 50%，主體高度不得超過畫布高度 50%；上下保留排字留白。
測試階段預設 480×640。生成後等比例縮小，優先 JPEG quality 60–70，base64 本體盡量不超過 100000 字元；必要時降低尺寸或品質，不可截斷字串。
將實際圖片位元組編碼成完整 data:image/jpeg;base64,...，用 generated_background_base64 傳回套件，同時設 generated_background_text_free_confirmed=true。
不要傳本機路徑或網址。此時 typography_confirmed 必須省略或為 false，套件只能回傳無字預覽。
顯示無字圖後詢問「無字海報已準備好，是否準備好加上文案？」並停止本輪工具呼叫，等待使用者下一則明確同意；「全部交給你」、intake_confirmed 或無字確認不等於同意排字。
第二階段：只有在無字預覽之後收到明確同意，才設 typography_confirmed=true，重新傳入同一張 generated_background_base64 與文案，並將預覽回傳的 draft_image_sha256 放入 approved_draft_sha256；換圖必須重新預覽及確認。
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
        "single_text_color": True,
        "instructions": ASSISTANT_INSTRUCTIONS,
        "required_final_status_code": "completed",
        "required_final_rendered": True,
    }
