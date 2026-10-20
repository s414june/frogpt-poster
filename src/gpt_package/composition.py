"""Resolve a poster once; reuse the existing Pillow/font/Blob rendering pipeline.

No network or image generation here. Asset materialization remains in the existing
transport layer. Missing inputs describe the next assistant action, never success.
"""
from dataclasses import dataclass, asdict
import math
from .errors import ValidationError
from .text_layers import validate_text_layers


@dataclass
class PosterSpec:
    canvas: dict
    background: dict
    subject: dict
    typography: list
    design: dict
    geometry: list
    legacy_draft: bool = False

    def to_dict(self):
        return asdict(self)


class BackgroundResolver:
    def resolve(self, request, arguments):
        if request.assets.user_image_paths:
            source = 'pexels_library' if arguments.get('reference_library_id') else (
                'pexels_api' if arguments.get('pexels_query') else 'user_upload')
            return dict(type='image', source=source, assetRef=request.assets.user_image_paths[0])
        mode = 'gradient' if request.style.background_mode == 'gradient' else 'solid'
        return dict(type=mode, source='ai_auto', color=request.style.primary_color,
                    gradient={'start': request.style.primary_color, 'end': request.style.secondary_color} if mode == 'gradient' else None)


class SubjectResolver:
    def resolve(self, request, arguments, draft):
        paths = request.assets.subject_image_paths
        if not paths and not draft:
            return None
        w, h = request.layout.width, request.layout.height
        position = arguments.get('subject_position') or dict(x=w*.25, y=h*.27, width=w*.5, height=h*.46)
        if not isinstance(position, dict):
            raise ValidationError('subject_position must be an object')
        for key in ('x', 'y', 'width', 'height'):
            val = position.get(key)
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValidationError('subject position must contain finite x/y/width/height')
        x,y,bw,bh = (position[k] for k in ('x','y','width','height'))
        if x < 0 or y < 0 or bw <= 0 or bh <= 0 or x+bw > w or y+bh > h:
            raise ValidationError('subject position must fit canvas')
        source = arguments.get('subject_source', 'user_upload')
        if source not in ('user_upload', 'ai_generated'):
            raise ValidationError('subject_source must be user_upload or ai_generated')
        return dict(assetRef=paths[0] if paths else request.assets.user_image_paths[0],
                    source='legacy_draft' if draft and not paths else source, position=position)


class DesignResolver:
    def resolve(self, request, arguments):
        variant = arguments.get('design_variant', 'reinterpret')
        if variant not in ('reinterpret', 'faithful'):
            raise ValidationError('design_variant must be reinterpret or faithful')
        return dict(referenceIds=arguments.get('design_reference_ids', []),
                    styleDescription=arguments.get('reference_style_description', ''), variant=variant,
                    source='user_reference' if arguments.get('design_reference') or arguments.get('reference_image_base64') else
                    ('builtin_reference' if arguments.get('design_reference_ids') else 'ai_auto'),
                    safe_margin_ratio=.05, alignment=request.style.text_align)


class TypographyResolver:
    def resolve(self, request):
        if request.style.text_layers:
            return validate_text_layers(request.style.text_layers, request.layout.width, request.layout.height)
        # Keep the existing measured typography algorithm as the default strategy.
        # Explicit AI-authored layers retain independent font/color/spacing values.
        if not request.title.strip() or not request.body.strip():
            return None
        return [dict(text=request.title, role='headline', strategy='existing_typography'),
                dict(text=request.body, role='body', strategy='existing_typography')]


class PosterRequestResolver:
    def resolve(self, request, arguments):
        draft = bool(arguments.get('generated_background_base64') or
                     (arguments.get('poster_request') or {}).get('generated_background_base64') or
                     (request.style.image_role_mode == 'both' and request.assets.user_image_paths))
        subject = SubjectResolver().resolve(request, arguments, draft)
        if not subject:
            if not request.allow_ai_fallback:
                return None, dict(ok=True, rendered=False, poster_status='needs_user_input',
                    status={'code':'needs_input','message':'subject_upload_required'}, next_action='upload_subject_then_retry')
            return None, dict(ok=True, rendered=False, pipeline_stage='needs_subject_generation', poster_status='needs_subject_generation',
                status={'code':'needs_subject_generation', 'message':'subject_required'},
                next_action='generate_subject_then_retry',
                subject_prompt=f"Create an isolated foreground subject for {request.style.subject or request.title}. No poster headline, slogan or watermark. Preserve product packaging labels; prefer transparent PNG.",
                subject_requirements={'transparent_background_preferred':True},
                retry_arguments_hint={'subject_source':'ai_generated', 'transport':'subject_image or subject_image_base64; reuse the original request and asset_refs'},
                composition={'background_source':BackgroundResolver().resolve(request, arguments)['source'], 'subject_source':None, 'geometry_used':False})
        typography = TypographyResolver().resolve(request)
        if not typography:
            return None, dict(ok=True, rendered=False, poster_status='needs_user_input',
                status={'code':'needs_input','message':'copy_required'}, next_action='supply_copy_then_retry')
        spec = PosterSpec(dict(width=request.layout.width,height=request.layout.height),
            BackgroundResolver().resolve(request, arguments), subject, typography,
            DesignResolver().resolve(request, arguments),
            ([{'assetRef':request.assets.geometry_image_path}] if request.assets.geometry_image_path else request.style.geometry_layers)
            if request.style.geometry_enabled else [], draft)
        return spec, None


class PosterRenderer:
    def render(self, spec, request, render_copy=True):
        if not spec.background or not spec.subject or not spec.typography:
            raise ValidationError('Background, subject and typography are required')
        # Adapt the resolved spec to the existing renderer; no design choices here.
        request.style.composition_resolved = True
        request.style.background_mode = 'reference' if spec.background['type'] == 'image' else spec.background['type']
        request.assets.user_image_paths = [spec.background['assetRef']] if spec.background['type'] == 'image' else []
        if spec.background['type'] != 'image':
            request.style.primary_color = spec.background['color']
            if spec.background.get('gradient'):
                request.style.secondary_color = spec.background['gradient']['end']
        if spec.subject['source'] != 'legacy_draft':
            request.assets.subject_image_paths = [spec.subject['assetRef']]
            request.style.subject_position = spec.subject['position']
        request.style.geometry_enabled = bool(spec.geometry)
        request.assets.geometry_image_path = next((layer['assetRef'] for layer in spec.geometry if 'assetRef' in layer), '')
        request.style.geometry_layers = [layer for layer in spec.geometry if 'assetRef' not in layer]
        if all('strategy' not in layer for layer in spec.typography):
            request.style.text_layers = spec.typography
        from .client import PosterGenerator
        return PosterGenerator().generate(request, render_copy=render_copy)


def composition_summary(spec):
    return dict(background_source='legacy_draft' if spec.legacy_draft else spec.background['source'],
                subject_source=spec.subject['source'], design_source=spec.design['source'], geometry_used=bool(spec.geometry))
