from __future__ import annotations

from io import BytesIO
from functools import lru_cache

from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1280, 720
BG = (10, 14, 16)
GOLD = (205, 164, 92)
PAPER = (211, 188, 145)
RED = (126, 35, 30)
INK = (30, 24, 19)


def _font(size: int, bold: bool = False):
    paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill, width=W):
    box = draw.textbbox((0, 0), text, font=font)
    x = (width - (box[2] - box[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _finish(image: Image.Image, name: str) -> BufferedInputFile:
    out = BytesIO()
    image.save(out, format='PNG', optimize=True)
    return BufferedInputFile(out.getvalue(), filename=name)


@lru_cache(maxsize=8)
def _render(kind: str) -> bytes:
    image = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(image)

    # cinematic glow
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((400, 120, 880, 680), fill=(208, 145, 60, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    image = Image.alpha_composite(image.convert('RGBA'), glow).convert('RGB')
    draw = ImageDraw.Draw(image)

    if kind == 'entry':
        # archive table, seal, candle
        draw.rounded_rectangle((170, 120, 1110, 620), radius=28, fill=(28, 27, 24), outline=GOLD, width=3)
        draw.polygon([(330, 220), (900, 180), (950, 500), (290, 535)], fill=(86, 66, 44), outline=(143, 111, 70))
        draw.rounded_rectangle((370, 250, 850, 500), radius=12, fill=PAPER, outline=(127, 96, 60), width=3)
        draw.ellipse((790, 380, 900, 490), fill=RED, outline=(176, 88, 61), width=4)
        draw.line((845, 392, 845, 478), fill=(218, 143, 96), width=4)
        draw.line((804, 435, 886, 435), fill=(218, 143, 96), width=4)
        draw.rectangle((960, 255, 978, 500), fill=(98, 69, 45))
        draw.ellipse((940, 210, 999, 290), fill=(242, 177, 72))
        _center(draw, 'АРХИВ ПАМЯТИ', 30, _font(48, True), GOLD)
        _center(draw, 'Повреждение зафиксировано', 655, _font(28), (224, 218, 201))

    elif kind == 'riddle':
        # moonlit oak and chain
        draw.ellipse((850, 80, 1040, 270), fill=(230, 224, 175))
        draw.rectangle((555, 235, 700, 650), fill=(61, 46, 27))
        for x1, y1, x2, y2 in [(620, 290, 220, 170), (640, 335, 1020, 180), (610, 420, 180, 390), (670, 455, 1080, 390)]:
            draw.line((x1, y1, x2, y2), fill=(63, 78, 37), width=35)
        # gold chain around trunk
        for i in range(13):
            x = 500 + i * 26
            y = 365 + int(28 * ((i % 2) - .5))
            draw.ellipse((x, y, x + 34, y + 22), outline=GOLD, width=5)
        # cat silhouette
        draw.ellipse((760, 460, 850, 555), fill=(8, 9, 9))
        draw.polygon([(775, 475), (790, 430), (810, 475)], fill=(8, 9, 9))
        draw.polygon([(820, 475), (842, 430), (850, 478)], fill=(8, 9, 9))
        draw.line((840, 520, 915, 500), fill=(8, 9, 9), width=14)
        draw.rounded_rectangle((90, 95, 520, 595), radius=18, fill=(213, 190, 145), outline=GOLD, width=3)
        lines = ['У лукоморья дуб зелёный;', 'Златая цепь на дубе том:', 'И днём и ночью кот учёный', 'Всё ходит по цепи кругом.']
        y = 165
        for line in lines:
            draw.text((130, y), line, font=_font(27), fill=INK)
            y += 62
        draw.text((130, 455), 'Какое слово скрыто', font=_font(29, True), fill=RED)
        draw.text((130, 500), 'на слайде?', font=_font(29, True), fill=RED)
        _center(draw, 'КЛЮЧ НАХОДИТСЯ В ЖИВОЙ ПРЕЗЕНТАЦИИ', 30, _font(34, True), GOLD)

    else:
        # restored archive
        draw.rounded_rectangle((190, 105, 1090, 630), radius=35, fill=(22, 29, 27), outline=GOLD, width=4)
        draw.polygon([(380, 215), (640, 270), (640, 570), (350, 510)], fill=PAPER, outline=GOLD)
        draw.polygon([(640, 270), (900, 215), (930, 510), (640, 570)], fill=(228, 207, 162), outline=GOLD)
        for i in range(26):
            x = 640 + (i % 7) * 34 - 100
            y = 150 + (i // 7) * 48
            draw.ellipse((x, y, x + 7, y + 7), fill=(244, 186, 75))
        _center(draw, 'ФРАГМЕНТ ВОССТАНОВЛЕН', 35, _font(44, True), GOLD)
        _center(draw, 'Живой формат открыл цифровой путь', 650, _font(28), (225, 221, 205))

    out = BytesIO()
    image.save(out, format='PNG', optimize=True)
    return out.getvalue()


def visual(kind: str) -> BufferedInputFile:
    names = {'entry': 'archive-entry.png', 'riddle': 'lukomorye-key.png', 'restored': 'archive-restored.png'}
    return BufferedInputFile(_render(kind), filename=names.get(kind, 'archive.png'))
