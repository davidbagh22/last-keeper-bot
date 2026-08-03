from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
BG=(10,14,16); GOLD=(205,164,92); PAPER=(221,201,160); RED=(126,35,30); INK=(30,24,19)


def _font(size:int,bold:bool=False):
    paths=[
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf']
    for p in paths:
        try:return ImageFont.truetype(p,size)
        except OSError:pass
    return ImageFont.load_default()


def _center(d,text,y,font,fill):
    b=d.textbbox((0,0),text,font=font); d.text(((W-(b[2]-b[0]))//2,y),text,font=font,fill=fill)


def _base():
    im=Image.new('RGB',(W,H),BG)
    glow=Image.new('RGBA',(W,H),(0,0,0,0)); gd=ImageDraw.Draw(glow); gd.ellipse((360,80,920,700),fill=(208,145,60,75)); glow=glow.filter(ImageFilter.GaussianBlur(100))
    return Image.alpha_composite(im.convert('RGBA'),glow).convert('RGB')


@lru_cache(maxsize=16)
def _render(kind:str)->bytes:
    im=_base(); d=ImageDraw.Draw(im)
    if kind=='entry':
        d.rounded_rectangle((150,110,1130,625),28,fill=(27,25,22),outline=GOLD,width=3)
        d.polygon([(300,215),(900,175),(955,510),(275,545)],fill=(87,66,43),outline=(145,112,72))
        d.rounded_rectangle((365,245,845,505),14,fill=PAPER,outline=(126,95,60),width=3)
        d.ellipse((790,380,900,490),fill=RED,outline=(180,90,62),width=4)
        d.rectangle((965,250,982,505),fill=(96,68,45)); d.ellipse((942,205,1004,292),fill=(244,178,72))
        _center(d,'АРХИВ ПАМЯТИ',30,_font(48,True),GOLD); _center(d,'Повреждение зафиксировано',655,_font(28),PAPER)
    elif kind=='scan':
        _center(d,'СКАНИРОВАНИЕ АРХИВА',30,_font(44,True),GOLD)
        for x,label,symbol in [(150,'СЛОВО','А'),(490,'ОТКРЫТИЕ','★'),(830,'КУЛЬТУРА','◈')]:
            d.rounded_rectangle((x,155,x+300,560),24,fill=(28,30,29),outline=GOLD,width=3)
            d.ellipse((x+75,210,x+225,360),outline=GOLD,width=5); _center_local=lambda t,y,f,c: d.text((x+150-d.textbbox((0,0),t,font=f)[2]/2,y),t,font=f,fill=c)
            _center_local(symbol,245,_font(70,True),GOLD); _center_local(label,405,_font(28,True),PAPER)
        _center(d,'Система удержит только один фрагмент',625,_font(27),PAPER)
    elif kind=='riddle':
        d.ellipse((850,75,1045,270),fill=(230,224,175)); d.rectangle((555,235,700,650),fill=(61,46,27))
        for seg in [(620,290,220,170),(640,335,1020,180),(610,420,180,390),(670,455,1080,390)]: d.line(seg,fill=(63,78,37),width=35)
        for i in range(13):
            x=500+i*26; y=365+int(28*((i%2)-.5)); d.ellipse((x,y,x+34,y+22),outline=GOLD,width=5)
        d.ellipse((760,460,850,555),fill=(8,9,9)); d.polygon([(775,475),(790,430),(810,475)],fill=(8,9,9)); d.polygon([(820,475),(842,430),(850,478)],fill=(8,9,9))
        d.rounded_rectangle((85,95,525,595),18,fill=PAPER,outline=GOLD,width=3)
        lines=['У лукоморья дуб зелёный;','Златая цепь на дубе том:','И днём и ночью кот учёный','Всё ходит по цепи кругом.']
        y=160
        for line in lines:d.text((125,y),line,font=_font(27),fill=INK); y+=62
        d.text((125,455),'Какое слово',font=_font(29,True),fill=RED); d.text((125,500),'открывает путь?',font=_font(29,True),fill=RED)
        _center(d,'КЛЮЧ НАХОДИТСЯ В ЖИВОЙ ПРЕЗЕНТАЦИИ',30,_font(34,True),GOLD)
    elif kind=='restored':
        d.rounded_rectangle((185,105,1095,630),35,fill=(22,29,27),outline=GOLD,width=4)
        d.polygon([(380,215),(640,270),(640,570),(350,510)],fill=PAPER,outline=GOLD); d.polygon([(640,270),(900,215),(930,510),(640,570)],fill=(228,207,162),outline=GOLD)
        for i in range(30):
            x=520+(i%10)*30; y=155+(i//10)*45; d.ellipse((x,y,x+8,y+8),fill=(244,186,75))
        _center(d,'ФРАГМЕНТ ВОССТАНОВЛЕН',35,_font(44,True),GOLD); _center(d,'Живой формат открыл цифровой путь',650,_font(28),PAPER)
    elif kind=='final':
        d.rounded_rectangle((160,90,1120,630),30,fill=(24,27,25),outline=GOLD,width=4)
        d.ellipse((500,180,780,460),outline=GOLD,width=7); d.ellipse((555,235,725,405),fill=(72,45,31),outline=(235,190,100),width=4)
        d.text((606,270),'Х',font=_font(86,True),fill=GOLD)
        for i in range(42):
            x=250+(i*83)%780; y=135+(i*47)%410; d.ellipse((x,y,x+6,y+6),fill=(245,188,76))
        _center(d,'ЛЕГЕНДА ХРАНИТЕЛЯ',32,_font(46,True),GOLD); _center(d,'Архив запомнил ваш путь',555,_font(31),PAPER); _center(d,'Память — это действие',650,_font(28,True),GOLD)
    else:
        _center(d,'АРХИВ ПАМЯТИ',290,_font(52,True),GOLD)
    out=BytesIO(); im.save(out,format='PNG',optimize=True); return out.getvalue()


def visual(kind:str)->BufferedInputFile:
    names={'entry':'archive-entry.png','scan':'archive-scan.png','riddle':'lukomorye-key.png','restored':'archive-restored.png','final':'keeper-legend.png'}
    return BufferedInputFile(_render(kind),filename=names.get(kind,'archive.png'))
