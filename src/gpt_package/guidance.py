"""Intake questions and lightweight design guide content."""

from __future__ import annotations


def build_intake_questions() -> list[dict]:
    return [
        {"id": "purpose", "question": "這張海報的用途或主題是什麼？", "choices": ["商品宣傳", "活動宣傳", "其他用途"], "allow_freeform": True},
        {"id": "size", "question": "需要什麼尺寸或使用平台？", "choices": ["直式社群海報", "正方形貼文", "請 AI 建議"], "allow_freeform": True},
        {
            "id": "copy_ready",
            "question": "你是否已有現成文案？",
            "choices": ["有，直接使用", "部分有，請幫我補齊", "沒有，請 AI 發想"],
            "allow_freeform": True,
        },
        {
            "id": "image_ready",
            "question": "你是否有現成圖片（人物/商品/活動照）？",
            "choices": [
                "有真實圖片（建議優先）",
                "有，但需要裁切或去背",
                "沒有，請 AI 生成主視覺",
            ],
            "allow_freeform": True,
        },
        {
            "id": "creative_source_preference",
            "question": "主視覺要怎麼決定？",
            "choices": [
                "由 GPT 生成與自動判斷（背景模式/色彩/幾何/圖源）",
                "我想自訂設計參數（背景模式、色系、幾何等）",
            ],
            "allow_freeform": False,
        },
        {
            "id": "style_preference",
            "question": "你偏好的海報風格是什麼？",
            "choices": ["簡約清新", "活潑可愛", "專業穩重", "潮流強烈", "請 AI 發想"],
            "allow_freeform": True,
        },
        {
            "id": "background_mode",
            "question": "背景模式要用哪一種？",
            "choices": [
                "auto（依素材自動判斷）",
                "solid（單色背景）",
                "gradient（漸層背景）",
                "reference（直接引用圖庫/參考圖）",
            ],
            "allow_freeform": False,
        },
        {
            "id": "image_role_mode",
            "question": "你提供的圖片要當主體、背景，還是兩者皆是？",
            "choices": [
                "auto（先詢問後由系統自動判斷）",
                "subject（主體物件）",
                "background（背景底圖）",
                "both（同張圖直接加字，不加幾何）",
            ],
            "allow_freeform": False,
        },
        {
            "id": "tone_and_keywords",
            "question": "有沒有想強調的情緒或關鍵字（例如：溫暖、可信任、公益感）？",
            "choices": ["我提供關鍵字", "請 AI 發想關鍵字與語氣"],
            "allow_freeform": True,
        },
        {
            "id": "image_prompt_seed",
            "question": "如果要 AI 生圖，你想要的畫面元素是什麼？（角色、場景、色系、構圖）",
            "choices": ["我提供具體元素", "請 AI 先提 3 組 prompt 草案"],
            "allow_freeform": True,
        },
    ]


def build_design_guide() -> dict:
    return {
        "principles": [
            "真圖優先：有使用者圖片就優先使用，AI 圖只當備援。",
            "避免過度設計：每張海報聚焦 1 個主標與 1 個行動呼籲。",
            "文字層級清楚：標題 > 副標 > 補充資訊，避免同級競爭。",
            "控制色彩：建議 1 主色 + 1 輔色 + 1 中性色。",
            "保留留白：四周至少保留 5% 畫布邊距，提升可讀性。",
        ],
        "font_guidance": {
            "note": "預設建議使用開源字型；若本機商用流程已取得授權，也可使用商用字型。",
            "open_source_font_links": [
                "https://fonts.google.com/noto",
                "https://github.com/adobe-fonts/source-han-sans",
                "https://github.com/adobe-fonts/source-han-serif",
                "https://fonts.google.com/",
            ],
        },
        "free_commercial_image_links": [
            "https://unsplash.com/",
            "https://www.pexels.com/",
            "https://pixabay.com/",
            "https://www.foodiesfeed.com/",
        ],
        "image_prompt_tips": [
            "先寫主體（誰/什麼）→ 場景（在哪）→ 光線/色調（什麼氛圍）→ 構圖（特寫/半身/遠景）。",
            "避免抽象形容詞過多，改用可視元素（材質、鏡位、背景物件）。",
            "先出 2-3 組方向，再挑一組細修，品質會比一次到底更穩定。",
        ],
    }
