from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1280, 720
IVORY = (247, 244, 237)
PAPER = (232, 224, 209)
INK = (28, 28, 30)
MUTED = (106, 100, 92)
RED = (160, 29, 39)
RED_SOFT = (196, 79, 86)
GOLD = (184, 145, 79)
LINE = (202, 195, 183)


def _font(size: int, bold: bool = False):
    paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill, x0: int = 0, x1: int = W):
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    draw.text((x0 + (x1 - x0 - width) // 2, y), text, font=font, fill=fill)


def _paper_texture(image: Image.Image) -> Image.Image:
    overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(0, H, 7):
        od.line((0, y, W, y), fill=(130, 115, 92, 7), width=1)
    for x in range(0, W, 11):
        od.line((x, 0, x, H), fill=(255, 255, 255, 7), width=1)
    return Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')


def _header(draw: ImageDraw.ImageDraw, index: str, title: str, subtitle: str):
    draw.text((72, 52), index, font=_font(18, True), fill=RED)
    draw.line((72, 86, 1208, 86), fill=LINE, width=2)
    draw.text((72, 112), title, font=_font(44, True), fill=INK)
    draw.text((74, 170), subtitle, font=_font(22), fill=MUTED)


def _artifact_layers(draw: ImageDraw.ImageDraw):
    draw.rounded_rectangle((760, 190, 1160, 570), radius=24, fill=(238, 232, 220), outline=LINE, width=2)
    draw.rounded_rectangle((720, 225, 1120, 605), radius=24, fill=(242, 237, 228), outline=LINE, width=2)
    draw.rounded_rectangle((680, 260, 1080, 640), radius=24, fill=(249, 247, 242), outline=RED_SOFT, width=2)
    draw.line((725, 325, 1035, 325), fill=LINE, width=2)
    draw.line((725, 370, 995, 370), fill=LINE, width=2)
    draw.line((725, 415, 1025, 415), fill=LINE, width=2)
    draw.line((725, 460, 960, 460), fill=LINE, width=2)
    draw.ellipse((925, 505, 1015, 595), outline=RED, width=5)
    draw.text((944, 524), 'Х', font=_font(34, True), fill=RED)


def _finish(image: Image.Image, name: str) -> BufferedInputFile:
    out = BytesIO()
    image.save(out, format='PNG', optimize=True)
    return BufferedInputFile(out.getvalue(), filename=name)


@lru_cache(maxsize=10)
def _render(kind: str) -> bytes:
    image = Image.new('RGB', (W, H), IVORY)
    image = _paper_texture(image)
    draw = ImageDraw.Draw(image)

    # мягкий красный световой акцент
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((805, 80, 1320, 610), fill=(173, 33, 45, 26))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    image = Image.alpha_composite(image.convert('RGBA'), glow).convert('RGB')
    draw = ImageDraw.Draw(image)

    if kind == 'entry':
        _header(draw, 'АРХИВ / 00', 'Память повреждена', 'Из истории исчезают слова, открытия и человеческие голоса')
        draw.text((72, 260), '01:59', font=_font(116, True), fill=RED)
        draw.text((78, 385), 'до необратимых изменений', font=_font(25), fill=MUTED)
        draw.rounded_rectangle((72, 474, 560, 566), radius=16, fill=RED)
        draw.text((112, 501), 'АРХИВ ИЩЕТ ХРАНИТЕЛЯ', font=_font(28, True), fill=IVORY)
        _artifact_layers(draw)

    elif kind == 'scan':
        _header(draw, 'АРХИВ / 01', 'Идентификация Хранителя', 'Система сопоставляет решения, память и готовность вмешаться')
        draw.rounded_rectangle((72, 266, 614, 346), radius=15, outline=LINE, width=2)
        for i, p in enumerate((18, 42, 67, 91)):
            x0 = 88 + i * 126
            draw.rounded_rectangle((x0, 282, x0 + 102, 330), radius=9, fill=RED if i < 3 else PAPER)
            draw.text((x0 + 27, 292), f'{p}%', font=_font(21, True), fill=IVORY if i < 3 else MUTED)
        draw.text((72, 405), 'Совпадение найдено', font=_font(46, True), fill=INK)
        draw.text((74, 470), 'Вы можете изменить ход Архива.', font=_font(28), fill=RED)
        _artifact_layers(draw)

    elif kind == 'riddle':
        _header(draw, 'АРХИВ / 02', 'Живой ключ', 'Цифровая ветвь откроется только после подсказки из презентации')
        draw.rounded_rectangle((72, 245, 620, 570), radius=20, fill=(250, 248, 244), outline=LINE, width=2)
        draw.text((110, 285), 'У лукоморья дуб …', font=_font(42, True), fill=INK)
        draw.line((110, 356, 545, 356), fill=RED, width=4)
        draw.text((110, 402), 'Найдите слово на слайде', font=_font(27), fill=MUTED)
        draw.text((110, 452), 'и введите его в бот.', font=_font(27), fill=MUTED)
        draw.rounded_rectangle((805, 250, 1085, 530), radius=140, outline=GOLD, width=5)
        draw.ellipse((900, 345, 990, 435), outline=RED, width=6)
        draw.line((945, 267, 945, 345), fill=GOLD, width=4)
        draw.line((945, 435, 945, 515), fill=GOLD, width=4)
        draw.line((822, 390, 900, 390), fill=GOLD, width=4)
        draw.line((990, 390, 1068, 390), fill=GOLD, width=4)
        draw.text((842, 570), 'ОФЛАЙН  →  TELEGRAM', font=_font(24, True), fill=RED)

    elif kind == 'restored':
        _header(draw, 'АРХИВ / 03', 'Фрагмент восстановлен', 'Живая подсказка изменила цифровой маршрут')
        draw.text((72, 275), 'КЛЮЧ ПРИНЯТ', font=_font(62, True), fill=RED)
        draw.text((74, 365), 'Следующая ситуация уже отличается', font=_font(30), fill=INK)
        draw.text((74, 410), 'от той, которую увидел бы другой участник.', font=_font(30), fill=INK)
        draw.rounded_rectangle((72, 510, 590, 582), radius=14, outline=RED, width=2)
        draw.text((105, 532), 'ПЕРВАЯ ВЕТВЬ СОХРАНЕНА', font=_font(25, True), fill=RED)
        _artifact_layers(draw)

    elif kind == 'finale':
        _header(draw, 'АРХИВ / ФИНАЛ', 'Легенда сформирована', 'Результат создан вашими решениями, а не заранее написанным сценарием')
        draw.text((72, 264), '1 из 59 049', font=_font(74, True), fill=RED)
        draw.text((76, 352), 'возможных индивидуальных путей', font=_font(28), fill=INK)
        draw.line((72, 420, 590, 420), fill=LINE, width=2)
        draw.text((72, 455), 'Архив закрывается.', font=_font(34, True), fill=INK)
        draw.text((72, 505), 'Память — нет.', font=_font(42, True), fill=RED)
        _artifact_layers(draw)

    else:
        _header(draw, 'АРХИВ', 'Фрагмент памяти', 'Интерактивная система проекта «Последний хранитель»')
        _artifact_layers(draw)

    out = BytesIO()
    image.save(out, format='PNG', optimize=True)
    return out.getvalue()


def visual(kind: str) -> BufferedInputFile:
    names = {
        'entry': 'archive-entry-premium.png',
        'scan': 'archive-scan-premium.png',
        'riddle': 'archive-live-key-premium.png',
        'restored': 'archive-restored-premium.png',
        'finale': 'archive-legend-premium.png',
    }
    return BufferedInputFile(_render(kind), filename=names.get(kind, 'archive-card.png'))
