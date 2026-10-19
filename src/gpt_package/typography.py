"""Typography and text layout for poster rendering."""

from __future__ import annotations

import hashlib

from PIL import Image, ImageDraw, ImageFont


class TypographyEngine:
    """Applies title/body text on poster image."""

    def select_font(self, font_paths: list[str], sample_text: str = "") -> str | None:
        return self.select_font_by_role(
            font_paths, sample_text=sample_text, role="body"
        )

    def select_font_by_role(
        self, font_paths: list[str], sample_text: str, role: str
    ) -> str | None:
        if not font_paths:
            return None
        ranked = sorted(
            font_paths,
            key=lambda path: self._font_priority(path, sample_text, role=role),
        )
        return ranked[0]

    def apply(
        self,
        image: Image.Image,
        title: str,
        body: str,
        font_paths: list[str],
        style=None,
    ) -> dict:
        role_mode = (
            str(getattr(style, "image_role_mode", "auto")).strip().lower()
            if style
            else "auto"
        )
        if role_mode == "both":
            return self._apply_focus_aware_two_size(
                image, title, body, font_paths, style=style
            )

        width, height = image.size
        margin = self._snap8(max(36, int(width * 0.06)))
        sample_text = f"{title}\n{body}"
        variant_token = str(getattr(style, "variation_token", ""))
        variant_index = self._variant_index(variant_token, modulo=17)
        title_jitter = self._variant_jitter(variant_token, salt="title", max_abs=0.028)
        body_jitter = self._variant_jitter(variant_token, salt="body", max_abs=0.032)
        body_font_path = self.select_font_by_role(
            font_paths, sample_text=sample_text, role="body"
        )
        heading_font_path = self._find_heading_font_from_body_family(
            font_paths=font_paths,
            body_font_path=body_font_path,
            sample_text=sample_text,
        )
        title_font = self._load_font(
            [heading_font_path] if heading_font_path else font_paths,
            size=max(48, int(round(width * 0.07))),
            sample_text=sample_text,
            role="heading",
        )
        minor_font = self._load_font(
            [body_font_path] if body_font_path else font_paths,
            size=max(24, int(round(width * 0.04))),
            sample_text=sample_text,
            role="body",
        )

        text_width = width - margin * 2
        draw = ImageDraw.Draw(image, "RGBA")
        title_lines = self._wrap_text(draw, title.strip(), title_font, text_width)
        body_lines_major = self._wrap_text(draw, body.strip(), title_font, text_width)
        body_lines_minor = self._wrap_text(draw, body.strip(), minor_font, text_width)

        title_max_lines = int(getattr(style, "title_max_lines", 2)) if style else 2
        body_max_lines = int(getattr(style, "body_max_lines", 4)) if style else 4
        title_max_lines = max(1, min(4, title_max_lines))
        body_max_lines = max(2, min(8, body_max_lines))

        title_region = (
            margin,
            max(8, int(height * 0.05)),
            width - margin,
            int(height * 0.35),
        )
        body_region = (margin, int(height * 0.70), width - margin, int(height * 0.97))
        title_color = body_color = self._pick_shared_text_color(image, [title_region, body_region])
        style_focus_box = self._style_focus_box(style, image)
        focus_box = style_focus_box or self._estimate_focus_box(image)
        has_explicit_focus_box = style_focus_box is not None

        title_y_candidates = [0.10, 0.12, 0.14, 0.16]
        body_y_candidates = [0.70, 0.72, 0.74, 0.76]
        title_base = title_y_candidates[variant_index % len(title_y_candidates)]
        body_base = body_y_candidates[variant_index % len(body_y_candidates)]
        title_ratio = max(0.06, min(0.22, title_base + title_jitter))
        body_ratio = max(0.66, min(0.84, body_base + body_jitter))
        y = self._snap8(max(24, int(height * title_ratio)))
        major_gap = self._snap8(max(8, int(title_font.size * 0.2)))
        focus_clearance = self._snap8(max(8, int(title_font.size * 0.25)))
        title_line_count = max(1, len(title_lines[:title_max_lines]))
        title_step = self._line_step(title_font.size)
        minor_step = self._line_step(minor_font.size)
        title_block_h = title_step * title_line_count
        if has_explicit_focus_box:
            y = max(margin, focus_box[1] - focus_clearance - title_block_h)
        else:
            y = self._keep_region_clear_of_focus(
                y=y,
                block_h=title_block_h,
                focus_box=focus_box,
                clearance=focus_clearance,
                margin=margin,
                image_w=width,
                image_h=height,
                prefer="up",
            )
        title_start_y = y
        for line in title_lines[:title_max_lines]:
            box = draw.textbbox((0, 0), line, font=title_font)
            line_w = box[2] - box[0]
            x = self._aligned_text_x(style, width, margin, box)
            draw.text((x, y), line, fill=title_color, font=title_font)
            y += title_step

        y = self._snap8(int(height * body_ratio))
        # Two-size policy: body first line uses major size; remaining lines use minor size.
        subtitle_line = body_lines_major[0] if body_lines_major else ""
        rest_lines = body_lines_minor[1:] if len(body_lines_minor) > 1 else []
        body_block_h = 0
        if subtitle_line:
            body_block_h += title_step
        if rest_lines:
            body_block_h += major_gap
            body_block_h += minor_step * max(1, min(len(rest_lines), max(1, body_max_lines - 1)))
        if body_block_h > 0:
            if has_explicit_focus_box:
                min_body_y = focus_box[3] + focus_clearance
                max_body_y = max(margin, height - margin - body_block_h)
                y = max(y, min_body_y)
                y = min(y, max_body_y)
            else:
                y = self._keep_region_clear_of_focus(
                    y=y,
                    block_h=body_block_h,
                    focus_box=focus_box,
                    clearance=focus_clearance,
                    margin=margin,
                    image_w=width,
                    image_h=height,
                    prefer="down",
                )
        body_start_y = self._snap8(y)
        y = body_start_y
        if subtitle_line:
            y = max(
                y,
                self._snap8(int(height * title_ratio)) + (title_step * max(1, len(title_lines[:title_max_lines]))) + major_gap,
            )
            box = draw.textbbox((0, 0), subtitle_line, font=title_font)
            line_w = box[2] - box[0]
            x = self._aligned_text_x(style, width, margin, box)
            draw.text((x, y), subtitle_line, fill=body_color, font=title_font)
            y += title_step
        if subtitle_line and rest_lines:
            y += major_gap
        for line in rest_lines[: max(1, body_max_lines - 1)]:
            box = draw.textbbox((0, 0), line, font=minor_font)
            line_w = box[2] - box[0]
            x = self._aligned_text_x(style, width, margin, box)
            draw.text((x, y), line, fill=body_color, font=minor_font)
            y += minor_step

        credit_text = (
            str(getattr(style, "source_credit_text", "")).strip() if style else ""
        )
        if credit_text:
            self.apply_source_credit_overlay(image, credit_text, font_paths)

        return {
            "selected_font": body_font_path
            or self.select_font(font_paths, sample_text=sample_text),
            "title_font": heading_font_path or body_font_path,
            "body_font": body_font_path,
            "layout_mode": "default",
            "layout_variant": variant_index,
            "major_font_size": title_font.size,
            "minor_font_size": minor_font.size,
            "focus_box": focus_box,
            "focus_clearance": focus_clearance,
            "title_start_y": title_start_y,
            "title_block_h": title_block_h,
            "body_start_y": body_start_y,
        }

    def _apply_focus_aware_two_size(
        self,
        image: Image.Image,
        title: str,
        body: str,
        font_paths: list[str],
        style=None,
    ) -> dict:
        width, height = image.size
        margin = self._snap8(max(36, int(width * 0.06)))
        sample_text = f"{title}\n{body}"

        body_font_path = self.select_font_by_role(
            font_paths, sample_text=sample_text, role="body"
        )
        heading_font_path = self._find_heading_font_from_body_family(
            font_paths=font_paths,
            body_font_path=body_font_path,
            sample_text=sample_text,
        )

        hero_font = self._load_font(
            [heading_font_path] if heading_font_path else font_paths,
            size=max(48, int(round(width * 0.065))),
            sample_text=sample_text,
            role="heading",
        )
        minor_font = self._load_font(
            [body_font_path] if body_font_path else font_paths,
            size=max(24, int(round(width * 0.05))),
            sample_text=sample_text,
            role="body",
        )

        draw = ImageDraw.Draw(image, "RGBA")
        text_width = width - margin * 2
        raw_title_lines = self._wrap_text(draw, title.strip(), minor_font, text_width)
        raw_body_lines = self._wrap_text(draw, body.strip(), minor_font, text_width)
        if getattr(style, "headline_source", "body_first") != "title" and raw_body_lines and raw_body_lines[0].strip():
            hero_text = raw_body_lines[0].strip()
            hero_lines = self._wrap_text(draw, hero_text, hero_font, text_width)
            minor_lines = [
                line for line in (raw_title_lines + raw_body_lines[1:]) if line.strip()
            ]
        else:
            hero_text = title.strip()
            hero_lines = self._wrap_text(draw, hero_text, hero_font, text_width)
            minor_lines = [line for line in raw_body_lines if line.strip()]

        if not hero_lines:
            hero_lines = [title.strip() or body.strip() or ""]
        if not minor_lines:
            minor_lines = [line for line in raw_title_lines if line.strip()]

        hero_height = self._lines_height(hero_font.size, len(hero_lines))
        minor_height = self._lines_height(minor_font.size, len(minor_lines))
        focus_box = self._estimate_focus_box(image)
        variant_token = str(getattr(style, "variation_token", ""))
        variant_index = self._variant_index(variant_token, modulo=29)
        hero_shift = self._variant_jitter(variant_token, salt="hero", max_abs=0.05)
        minor_shift = self._variant_jitter(variant_token, salt="minor", max_abs=0.05)
        hero_region, minor_region = self._pick_two_block_regions(
            image=image,
            margin=margin,
            hero_height=hero_height,
            minor_height=minor_height,
            focus_box=focus_box,
            variant_index=variant_index,
            hero_shift=hero_shift,
            minor_shift=minor_shift,
        )

        body_y_ratio = getattr(style, "body_y_ratio", None)
        if body_y_ratio is not None:
            body_y = max(margin, min(int(height * body_y_ratio), height - margin - minor_height))
            minor_region = (margin, body_y, width - margin, body_y + minor_height)
        hero_color = minor_color = self._pick_shared_text_color(image, [hero_region, minor_region])
        hero_start_y = hero_region[1]
        for line in hero_lines:
            box = draw.textbbox((0, 0), line, font=hero_font)
            line_w = box[2] - box[0]
            x = self._aligned_text_x(style, width, margin, box)
            draw.text((x, hero_start_y), line, fill=hero_color, font=hero_font)
            hero_start_y += self._line_step(hero_font.size)

        minor_start_y = minor_region[1]
        for line in minor_lines:
            box = draw.textbbox((0, 0), line, font=minor_font)
            line_w = box[2] - box[0]
            x = self._aligned_text_x(style, width, margin, box)
            draw.text((x, minor_start_y), line, fill=minor_color, font=minor_font)
            minor_start_y += self._line_step(minor_font.size)

        credit_text = (
            str(getattr(style, "source_credit_text", "")).strip() if style else ""
        )
        if credit_text:
            self.apply_source_credit_overlay(image, credit_text, font_paths)

        return {
            "selected_font": body_font_path
            or self.select_font(font_paths, sample_text=sample_text),
            "title_font": heading_font_path or body_font_path,
            "body_font": body_font_path,
            "layout_mode": "both_focus_aware",
            "layout_variant": variant_index,
            "hero_font_size": hero_font.size,
            "minor_font_size": minor_font.size,
            "focus_box": focus_box,
            "hero_region": hero_region,
            "hero_lines": hero_lines,
            "minor_lines": minor_lines,
            "text_align": getattr(style, "text_align", "center"),
            "minor_region": minor_region,
        }

    def apply_source_credit_overlay(
        self, image: Image.Image, credit_text: str, font_paths: list[str]
    ) -> None:
        text = credit_text.strip()
        if not text:
            return
        width, _height = image.size
        draw = ImageDraw.Draw(image, "RGBA")
        font = self._load_font(
            font_paths, size=max(14, int(width * 0.018)), sample_text=text, role="body"
        )
        margin = max(12, int(width * 0.018))
        box = draw.textbbox((0, 0), text, font=font)
        text_w = box[2] - box[0]
        text_h = box[3] - box[1]
        x = width - margin - text_w
        y = margin
        pad_x = max(8, int(width * 0.008))
        pad_y = max(5, int(width * 0.005))
        draw.rounded_rectangle(
            [(x - pad_x, y - pad_y), (x + text_w + pad_x, y + text_h + pad_y)],
            radius=max(6, int(width * 0.01)),
            fill=(0, 0, 0, 125),
        )
        draw.text((x, y), text, fill=(245, 245, 245, 235), font=font)

    def _load_font(
        self,
        font_paths: list[str],
        size: int,
        sample_text: str,
        role: str = "body",
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in sorted(
            font_paths,
            key=lambda item: self._font_priority(item, sample_text, role=role),
        ):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        if not text:
            return [""]

        text = text.replace("\r\n", "\n")
        lines: list[str] = []
        current = ""
        for ch in text:
            if ch == "\n":
                if current:
                    lines.append(current.rstrip())
                current = ""
                continue
            candidate = current + ch
            box = draw.textbbox((0, 0), candidate, font=font)
            if (box[2] - box[0]) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current.rstrip())
                current = ch
        if current:
            lines.append(current.rstrip())
        return lines if lines else [text]

    def _font_priority(
        self, path: str, sample_text: str, role: str = "body"
    ) -> tuple[int, int, str]:
        name = path.lower()
        has_han = any("\u4e00" <= ch <= "\u9fff" for ch in sample_text)
        cjk_hits = (
            "noto-sans-tc",
            "noto-sans-sc",
            "noto-sans-hk",
            "noto-sans-jp",
            "noto-sans-kr",
            "sourcehan",
            "source-han",
            "cjk",
            "han",
            "nanum",
            "mplus",
            "m-plus",
        )
        sans_hits = ("sans", "gothic", "heiti", "hei")
        serif_hits = ("serif", "ming", "song")
        heading_weight_hits = ("bold", "semibold", "demi", "medium")
        regular_weight_hits = ("regular", "book", "normal", "medium")

        cjk_rank = 3
        if has_han and any(
            token in name
            for token in ("tc", "sc", "hk", "sourcehan", "source-han", "cjk", "han")
        ):
            cjk_rank = 0
        elif any(token in name for token in cjk_hits):
            cjk_rank = 1
        elif "noto" in name:
            cjk_rank = 2

        sans_rank = 0 if any(token in name for token in sans_hits) else 2
        if any(token in name for token in serif_hits):
            sans_rank = 4

        if role == "heading":
            if any(token in name for token in heading_weight_hits):
                weight_rank = 0
            elif any(token in name for token in regular_weight_hits):
                weight_rank = 1
            elif any(token in name for token in ("black", "bold")):
                weight_rank = 2
            else:
                weight_rank = 3
        else:
            weight_rank = (
                0 if any(token in name for token in regular_weight_hits) else 2
            )
            if any(token in name for token in ("black", "bold")):
                weight_rank = max(weight_rank, 1)

        variable_rank = 1 if ("variablefont" in name or "[wght]" in name) else 0

        return (cjk_rank, sans_rank + weight_rank + variable_rank, name)

    def _find_heading_font_from_body_family(
        self,
        font_paths: list[str],
        body_font_path: str | None,
        sample_text: str,
    ) -> str | None:
        if not body_font_path:
            return self.select_font_by_role(
                font_paths, sample_text=sample_text, role="heading"
            )
        family = self._font_family_key(body_font_path)
        same_family = [p for p in font_paths if self._font_family_key(p) == family]
        if same_family:
            return self.select_font_by_role(
                same_family, sample_text=sample_text, role="heading"
            )
        return body_font_path

    def _line_step(self, font_size: int) -> int:
        """One font em plus a half-em gap, rounded only to whole pixels."""
        return max(1, int(round(font_size * 1.5)))

    def _lines_height(self, font_size: int, line_count: int) -> int:
        return self._line_step(font_size) * max(1, line_count)

    def _snap8(self, value: int) -> int:
        if value <= 0:
            return 0
        return max(8, int(round(value / 8.0) * 8))


    def _estimate_focus_box(self, image: Image.Image) -> tuple[int, int, int, int]:
        width, height = image.size
        small = image.convert("L").resize((96, 96), Image.Resampling.BILINEAR)
        pix = small.load()
        total = 0.0
        sum_x = 0.0
        sum_y = 0.0
        for y in range(1, 95):
            for x in range(1, 95):
                gx = abs(int(pix[x + 1, y]) - int(pix[x - 1, y]))
                gy = abs(int(pix[x, y + 1]) - int(pix[x, y - 1]))
                w = float(gx + gy)
                total += w
                sum_x += x * w
                sum_y += y * w
        if total <= 0.0:
            cx = width // 2
            cy = height // 2
        else:
            cx = int((sum_x / total) / 95.0 * width)
            cy = int((sum_y / total) / 95.0 * height)
        box_w = int(width * 0.34)
        box_h = int(height * 0.30)
        x1 = max(0, min(width - box_w, cx - box_w // 2))
        y1 = max(0, min(height - box_h, cy - box_h // 2))
        return (x1, y1, x1 + box_w, y1 + box_h)

    def _style_focus_box(
        self, style, image: Image.Image
    ) -> tuple[int, int, int, int] | None:
        if style is None:
            return None
        raw = getattr(style, "subject_focus_box", None)
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            return None
        try:
            x1, y1, x2, y2 = [int(v) for v in raw]
        except (TypeError, ValueError):
            return None
        x1 = max(0, min(image.width - 1, x1))
        y1 = max(0, min(image.height - 1, y1))
        x2 = max(x1 + 1, min(image.width, x2))
        y2 = max(y1 + 1, min(image.height, y2))
        return (x1, y1, x2, y2)

    def _pick_two_block_regions(
        self,
        image: Image.Image,
        margin: int,
        hero_height: int,
        minor_height: int,
        focus_box: tuple[int, int, int, int],
        variant_index: int = 0,
        hero_shift: float = 0.0,
        minor_shift: float = 0.0,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        width, height = image.size
        candidates = [
            (0.10, 0.80),
            (0.13, 0.74),
            (0.18, 0.78),
            (0.70, 0.16),
            (0.76, 0.22),
        ]
        if candidates:
            offset = variant_index % len(candidates)
            candidates = candidates[offset:] + candidates[:offset]
        best: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None = None
        best_score = float("inf")
        for hero_r, minor_r in candidates:
            hero_y = int(height * max(0.06, min(0.86, hero_r + hero_shift)))
            minor_y = int(height * max(0.06, min(0.90, minor_r + minor_shift)))
            hero_region = (margin, hero_y, width - margin, hero_y + hero_height)
            minor_region = (margin, minor_y, width - margin, minor_y + minor_height)
            clearance = int(max(8, hero_height * 0.05))
            score = 0.0
            score += self._overlap_area(hero_region, focus_box) * 6.0
            score += self._overlap_area(minor_region, focus_box) * 4.0
            score += self._clearance_penalty(hero_region, focus_box, clearance) * 5.0
            score += self._clearance_penalty(minor_region, focus_box, clearance) * 3.0
            score += self._overlap_area(hero_region, minor_region) * 8.0
            score += self._out_of_bounds_penalty(hero_region, width, height)
            score += self._out_of_bounds_penalty(minor_region, width, height)
            if score < best_score:
                best_score = score
                best = (hero_region, minor_region)
        if best is None:
            top = (
                margin,
                int(height * 0.12),
                width - margin,
                int(height * 0.12) + hero_height,
            )
            bottom = (
                margin,
                int(height * 0.76),
                width - margin,
                int(height * 0.76) + minor_height,
            )
            return top, bottom
        return best

    def _overlap_area(
        self, a: tuple[int, int, int, int], b: tuple[int, int, int, int]
    ) -> int:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        if x2 <= x1 or y2 <= y1:
            return 0
        return (x2 - x1) * (y2 - y1)

    def _out_of_bounds_penalty(
        self, region: tuple[int, int, int, int], width: int, height: int
    ) -> float:
        x1, y1, x2, y2 = region
        p = 0.0
        if x1 < 0:
            p += abs(x1) * 20.0
        if y1 < 0:
            p += abs(y1) * 20.0
        if x2 > width:
            p += abs(x2 - width) * 20.0
        if y2 > height:
            p += abs(y2 - height) * 20.0
        return p

    def _keep_region_clear_of_focus(
        self,
        y: int,
        block_h: int,
        focus_box: tuple[int, int, int, int],
        clearance: int,
        margin: int,
        image_w: int,
        image_h: int,
        prefer: str,
    ) -> int:
        if block_h <= 0:
            return y
        region = (margin, y, max(margin + 1, image_w - margin), y + block_h)
        if self._clearance_penalty(region, focus_box, clearance) <= 0:
            return y
        fx1, fy1, fx2, fy2 = focus_box
        up_y = max(margin, fy1 - clearance - block_h)
        down_y = min(max(margin, image_h - margin - block_h), fy2 + clearance)
        if prefer == "up":
            return up_y if up_y >= margin else down_y
        return down_y if down_y + block_h <= image_h - margin else up_y

    def _clearance_penalty(
        self,
        region: tuple[int, int, int, int],
        focus_box: tuple[int, int, int, int],
        clearance: int,
    ) -> int:
        expanded = (
            focus_box[0] - clearance,
            focus_box[1] - clearance,
            focus_box[2] + clearance,
            focus_box[3] + clearance,
        )
        return self._overlap_area(region, expanded)

    def _variant_index(self, token: str, modulo: int) -> int:
        text = (token or "").strip()
        if not text or modulo <= 0:
            return 0
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % modulo

    def _variant_jitter(self, token: str, salt: str, max_abs: float) -> float:
        text = (token or "").strip()
        if not text or max_abs <= 0:
            return 0.0
        digest = hashlib.sha256(f"{text}|{salt}".encode("utf-8")).hexdigest()
        raw = int(digest[:8], 16) / 0xFFFFFFFF
        centered = (raw * 2.0) - 1.0
        return centered * max_abs

    def _font_family_key(self, path: str) -> str:
        stem = path.lower().replace("\\", "/").split("/")[-1]
        base = stem.split(".")[0]
        for token in (
            "-bold",
            "_bold",
            "-black",
            "_black",
            "-regular",
            "_regular",
            "-medium",
            "_medium",
        ):
            base = base.replace(token, "")
        return base

    def _aligned_text_x(self, style, width, margin, box):
        align = getattr(style, "text_align", "center")
        if align == "left":
            return margin - box[0]
        if align == "right":
            return width - margin - box[2]
        return max(margin, (width - (box[2] - box[0])) // 2 - box[0])

    def _pick_shared_text_color(self, image: Image.Image, regions: list) -> tuple[int, int, int, int]:
        """Choose one color maximizing the worst contrast across all text blocks."""
        candidates = [(18, 18, 18, 240), (248, 248, 248, 240)]
        luminances = [self._region_luma(image, region) for region in regions]
        return max(candidates, key=lambda color: min(
            self._contrast_ratio(luma, self._rgb_luma(color[:3])) for luma in luminances
        ))

    def _pick_text_color(
        self, image: Image.Image, region: tuple[int, int, int, int]
    ) -> tuple[int, int, int, int]:
        dark = (18, 18, 18, 240)
        light = (248, 248, 248, 240)
        bg_luma = self._region_luma(image, region)
        dark_ratio = self._contrast_ratio(bg_luma, self._rgb_luma(dark[:3]))
        light_ratio = self._contrast_ratio(bg_luma, self._rgb_luma(light[:3]))
        return light if light_ratio >= dark_ratio else dark

    def _region_luma(
        self, image: Image.Image, region: tuple[int, int, int, int]
    ) -> float:
        x1, y1, x2, y2 = region
        x1 = max(0, min(image.width - 1, x1))
        y1 = max(0, min(image.height - 1, y1))
        x2 = max(x1 + 1, min(image.width, x2))
        y2 = max(y1 + 1, min(image.height, y2))
        crop = (
            image.convert("RGB")
            .crop((x1, y1, x2, y2))
            .resize((1, 1), Image.Resampling.BILINEAR)
        )
        rgb = crop.getpixel((0, 0))
        return self._rgb_luma(rgb)

    def _rgb_luma(self, rgb: tuple[int, int, int]) -> float:
        def to_lin(v: int) -> float:
            c = v / 255.0
            if c <= 0.04045:
                return c / 12.92
            return ((c + 0.055) / 1.055) ** 2.4

        r, g, b = rgb
        return 0.2126 * to_lin(r) + 0.7152 * to_lin(g) + 0.0722 * to_lin(b)

    def _contrast_ratio(self, a_luma: float, b_luma: float) -> float:
        hi = max(a_luma, b_luma)
        lo = min(a_luma, b_luma)
        return (hi + 0.05) / (lo + 0.05)
