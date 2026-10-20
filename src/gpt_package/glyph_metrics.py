"""Actual registered font cmap coverage and per-run Pillow measurements."""
import functools
import struct
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageChops
from .font_registry import resolve_font_weight
from .font_provider import materialize_font
from .design_rules import DesignRuleError, diagnostic


@functools.lru_cache(maxsize=12)
def coverage(path):
    raw=Path(path).read_bytes()
    u16=lambda off:struct.unpack_from('>H',raw,off)[0]
    u32=lambda off:struct.unpack_from('>I',raw,off)[0]
    table=None
    for i in range(u16(4)):
        off=12+i*16
        if raw[off:off+4]==b'cmap':table=u32(off+8);break
    if table is None: raise DesignRuleError('FONT_UNAVAILABLE','TYPO-009','Font has no cmap')
    supported=set()
    for i in range(u16(table+2)):
        entry=table+4+i*8
        platform,encoding=u16(entry),u16(entry+2)
        if platform not in (0,3) or (platform==3 and encoding not in (1,10)): continue
        sub=table+u32(entry+4);fmt=u16(sub)
        if fmt==12:
            for g in range(u32(sub+12)):
                start,end,glyph=struct.unpack_from('>III',raw,sub+16+g*12)
                supported.update(range(start+(glyph==0),end+1))
        elif fmt==4:
            count=u16(sub+6)//2;ends=sub+14;starts=ends+count*2+2;deltas=starts+count*2;ranges=deltas+count*2
            for seg in range(count):
                first,last=u16(starts+seg*2),u16(ends+seg*2)
                delta=u16(deltas+seg*2);distance=u16(ranges+seg*2)
                for code in range(first,min(last,65534)+1):
                    glyph=u16(ranges+seg*2+distance+(code-first)*2) if distance else code
                    if glyph and ((glyph+delta)&65535):supported.add(code)
    if not supported: raise DesignRuleError('FONT_UNAVAILABLE','TYPO-009','No supported Unicode cmap')
    return frozenset(supported)


class GlyphMeasurer:
    def __init__(self, family, weight, size, fallback):
        self.fonts=[]
        for name in dict.fromkeys([family,*fallback]):
            try:
                _,value=resolve_font_weight(name,weight if name in ('sans','serif') else 400)
                path=materialize_font(value)
                self.fonts.append((name,ImageFont.truetype(path,max(1,round(size))),coverage(path)))
            except Exception as exc:
                if name==family: raise DesignRuleError('FONT_UNAVAILABLE','TYPO-009',str(exc)) from exc
        if not self.fonts:raise DesignRuleError('FONT_UNAVAILABLE','TYPO-009','No measurable font')
        self.fallback_used=set()
        self.used_fonts=set()

    def runs(self,text):
        result=[]
        for char in text:
            match=next(((name,font) for name,font,cmap in self.fonts if ord(char) in cmap),None)
            if not match: raise DesignRuleError('FONT_UNAVAILABLE','TYPO-009',f'No registered glyph for U+{ord(char):04X}')
            name,font=match
            self.used_fonts.add(name)
            if name != self.fonts[0][0]:self.fallback_used.add(name)
            if result and result[-1][0]==name:result[-1]=(name,font,result[-1][2]+char)
            else:result.append((name,font,char))
        return result

    def width(self,text,tracking=0):
        return sum(font.getlength(run) for _,font,run in self.runs(text))+max(0,len(text)-1)*tracking

    def wrap(self,text,width,tracking=0):
        lines=[]
        closing='，。！？；：、）》】」』,.!?;:)'
        for paragraph in text.split('\n'):
            rest=paragraph
            while rest:
                limit=0
                for n in range(1,len(rest)+1):
                    if self.width(rest[:n],tracking)>width:break
                    limit=n
                if not limit: raise DesignRuleError('TYPO_TEXT_OVERFLOW','TYPO-003','A glyph does not fit the box')
                cut=limit
                if limit<len(rest):
                    choices=[i for i in range(1,limit+1) if (rest[i-1].isspace() or ord(rest[i-1])>255) and rest[i] not in closing]
                    if choices:cut=choices[-1]
                    elif rest[cut] in closing and cut>1:cut-=1
                lines.append(rest[:cut]);rest=rest[cut:]
            if not paragraph:lines.append('')
        if ''.join(lines) != text.replace('\n',''):raise DesignRuleError('TEXT_INTEGRITY','VAL-003','Wrapping changed the original text')
        return lines

    def raster(self,lines,tracking,line_height,align):
        # Measure baseline-relative runs, then draw the same runs; no estimated GPT boxes.
        draw=ImageDraw.Draw(Image.new('L',(1,1)))
        asc=max(font.getmetrics()[0] for _,font,_ in self.fonts)
        desc=max(font.getmetrics()[1] for _,font,_ in self.fonts)
        advance=max(1,round(max(font.size for _,font,_ in self.fonts)*line_height))
        widths=[self.width(line,tracking) for line in lines];maximum=max(widths,default=0)
        glyphs=[];bounds=[]
        for row,line in enumerate(lines):
            x={'left':0,'center':(maximum-widths[row])/2,'right':maximum-widths[row]}[align]
            for _,font,run in self.runs(line):
                parts=list(run) if tracking else [run]
                for part in parts:
                    y=row*advance
                    b=draw.textbbox((x,y),part,font=font,anchor='ls')
                    bounds.append(b);glyphs.append((row,part,font,x,y))
                    x+=font.getlength(part)+(tracking if tracking else 0)
        visible=[b for b in bounds if b[2]>b[0] and b[3]>b[1]]
        if not visible:raise DesignRuleError('POSTER_MISSING_LAYER','TYPO-001','Text has no visible glyphs')
        left=min(b[0] for b in visible);top=min(b[1] for b in visible)
        right=max(b[2] for b in visible);bottom=max(b[3] for b in visible)
        size=(max(1,math.ceil(right-left)),max(1,math.ceil(bottom-top)))
        mask=Image.new('L',size);painter=ImageDraw.Draw(mask)
        for row in range(len(lines)):
            entries=[entry for entry in glyphs if entry[0]==row]
            if not entries:continue
            row_bounds=[draw.textbbox((x-left,y-top),part,font=font,anchor='ls') for _,part,font,x,y in entries]
            x0=math.floor(min(b[0] for b in row_bounds));y0=math.floor(min(b[1] for b in row_bounds))
            x1=math.ceil(max(b[2] for b in row_bounds));y1=math.ceil(max(b[3] for b in row_bounds))
            if x1<=x0 or y1<=y0:continue
            local=Image.new('L',(x1-x0,y1-y0));local_draw=ImageDraw.Draw(local)
            for _,part,font,x,y in entries:local_draw.text((x-left-x0,y-top-y0),part,font=font,fill=255,anchor='ls')
            prior=mask.crop((x0,y0,x1,y1))
            if ImageChops.multiply(local,prior).getbbox():
                raise DesignRuleError('TYPO_GLYPH_COLLISION','TYPO-003','Important text lines have overlapping glyph ink')
            mask.paste(ImageChops.lighter(local,prior),(x0,y0))
        return mask,dict(width=size[0],height=size[1],advance=advance,ascender=asc,descender=desc)
