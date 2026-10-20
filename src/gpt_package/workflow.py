"""Shared, explicit instructions for the assistant-controlled image workflow."""

WORK_MODE_FALLBACK_MESSAGE = (
    '目前無法在「對話」中完成圖片傳送或海報生成。請改用「工作」模式，'
    '在新工作中重新附上原圖，再使用 @FroGPT Poster 生成海報。'
    '切換模式不保證解決所有問題；若仍失敗，請保留錯誤訊息以便排查。'
)

ASSISTANT_INSTRUCTIONS = """FroGPT Poster 自動完成流程：所有海報均包含獨立背景、主體、API 字型文字；幾何可省略。使用者說幫我做海報、全部交給你、直接完成時，接續工具 next_action 在同一需求中完成，不強制問卷或逐階段批准。
背景優先使用使用者提供的 background_image，其次由 GPT 從 use_local_reference_library 目錄選 reference_library_id，否則自行選 solid/gradient 及色彩。API 不會替 GPT 挑照片，也不能把背景當缺失主體。
主體使用 subject_image；缺少時 needs_subject_generation / generate_subject_then_retry 要求 GPT 生成獨立主體（優先透明 PNG），無海報文案或浮水印，包裝品牌標籤可保留。以 subject_image 附件傳回，或傳實際 bytes 的 subject_image_base64，並設 subject_source=ai_generated；沿用原需求與已回傳 asset_refs，不再要求使用者重述。
設計優先參考使用者 reference_image/描述，其次 GPT 可查 list_design_references 並選 design_reference_ids，否則 GPT 自行決定完整設計。參考圖只作靈感，不當背景。design_variant 預設 reinterpret，忠實還原才 faithful。可設定 subject_position、text_layers、配色和留白。文字各層可有不同字級、字重、顏色、行距；預設黑體 sans，可選 serif/kai/rounded。沒有參考或 text_layers 也有現有預設排版。
幾何裝飾完全可選；預設無幾何，geometry_enabled=false 完全停用。需要時優先傳同畫布尺寸的透明 geometry_image PNG，依背景→幾何→主體→文字順序合成；不得自行補回使用者移除的裝飾。保留 geometry_layers 相容輸入。
預設直接完成。只有使用者明確要求先看草稿才設 preview_only=true，使用 draft_image（完整無字底稿）取得預覽後停止等批准；批准時傳相同 draft ref、approved_draft_sha256 及 typography_confirmed=true。generated_background_base64 與 draft_image 是相容輸入，不能和獨立背景混用。
附件優先 openai/fileParams：subject_image/background_image/reference_image/draft_image/geometry_image，由宿主提供 download_url/file_id；不要求助理自行轉大型 Base64，也不要求先有本機 bytes。伺服器下載驗證，已存 Blob 後重用 asset_refs。store_poster_asset 可選，缺少此工具不阻止附件流程。不可傳 /mnt/data 或 /workspace 路徑；無平台附件參照且無實際 bytes 時停止並回報附件讀取失敗，尚未傳入套件，不得編造 Base64、把路徑編碼或重畫使用者照片。
外傳素材至 FroGPT Poster 並存 Public Blob（素材 24h、成品 72h，持 URL 者可讀，清理非秒級）。intake_confirmed 與自動完成均不是敏感素材外傳授權。保留宿主授權要求，審核拒絕時說明阻擋層，不得改 curl、端點、annotation 繞過。Production 保留上傳開關。
No such file or directory 屬於附件讀取錯誤；原因尚未確認時不可猜測。失敗分層：附件取得、輸入驗證、渲染、宿主傳輸。沒有伺服器診斷不能斷言原因；只有修正輸入或取得附件新證據才額外重試一次，禁止原樣無限重試。若「對話」無法取回附件，可建議「工作」模式重新附上原圖，但不能保證解決；已在「工作」時保留診斷，不反覆叫使用者切換。
只有 rendered=true 且 poster_status/status.code=completed 才能宣告完成。優先交付 image_url/download_url；若是 Base64，驗證實際圖片 bytes 後提供 PNG。不可把 JSON、HTML、錯誤或路徑當圖片。
"""


def assistant_execution_contract() -> dict:
    return {
        "attachment_preflight": {
            "preferred_transport": "openai/fileParams",
            "file_fields": ["subject_image", "background_image", "reference_image", "draft_image", "geometry_image"],
            "host_reference_does_not_require_local_bytes": True,
            "store_tool_required": False,
            "required_before_render_call": True,
            "checks": ["host_file_reference_or_verified_image_bytes"],
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
            "resolve_background_and_design", "generate_separate_subject",
            "retry_with_subject_image_and_original_request", "deliver_rendered_png"
        ],
        "pause_status": "awaiting_typography_confirmation",
        "when_status_not_completed": "follow_next_action; never retry while awaiting user confirmation",
        "subject_bounds": {"center": [0.5, 0.5], "max_width_ratio": 0.5, "max_height_ratio": 0.5},
        "mobile_test_profile": {"width": 480, "height": 640, "target_input_base64_chars": 100000},
        "design_reference_workflow": {"enabled_by": "design_reference=true", "reference_usage": "inspiration_only", "text_renderer": "API text_layers", "requires_separate_typography_approval": False},
        "single_text_color": False,
        "instructions": ASSISTANT_INSTRUCTIONS,
        "required_final_status_code": "completed",
        "required_final_rendered": True,
    }
