from __future__ import annotations

import json
from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from quest_common import LOCATION_TITLES, completed_locations, game_is_unlocked, is_assigned, option_keyboard, option_text, ordered_games, passed_games, progress_bar
from storage import utcnow
from team_games import GAMES_BY_ID, presented_correct_index, presented_options

router = Router(name='last_keeper_production_v7')

VALUES = {
    'memory': ('📜', 'Память'), 'truth': ('🔎', 'Точность'), 'voice': ('💬', 'Живое слово'),
    'responsibility': ('⚖️', 'Ответственность'), 'future': ('🚀', 'Будущее'),
    'unity': ('🤝', 'Связь поколений'), 'culture': ('🪆', 'Культурный код'),
    'courage': ('🔥', 'Смелость'), 'human': ('🕯', 'Человеческий голос'),
    'curiosity': ('🧭', 'Любознательность'),
}
TEAM_BASE = {
    'Красные': ('Огненная летопись', 'Вы первыми входили в неизвестность и возвращали Архиву движение.'),
    'Белые': ('Светлый свод', 'Вы искали ясность там, где проще было принять красивую версию.'),
    'Оранжевые': ('Мост эпох', 'Вы соединяли прошлое и будущее, традицию и новый язык.'),
    'Зелёные': ('Живая память', 'Вы сохраняли голос, интонацию и право человека быть услышанным.'),
    'Синие': ('Карта будущего', 'Вы превращали наследие в маршрут вперёд.'),
}
PAIR_TITLES = {
    frozenset(('memory','truth')): 'Стражи подлинной памяти',
    frozenset(('memory','human')): 'Хранители живых свидетельств',
    frozenset(('voice','unity')): 'Проводники живого слова',
    frozenset(('future','responsibility')): 'Архитекторы ответственного будущего',
    frozenset(('culture','voice')): 'Переводчики культурного кода',
    frozenset(('future','courage')): 'Первые за горизонтом',
    frozenset(('truth','curiosity')): 'Исследователи скрытых связей',
    frozenset(('unity','human')): 'Собиратели голосов поколений',
}

NODES = {
'culture': [
('Слово меняет форму','Старинный текст понятен не всем. Что сохранить в первую очередь?',[
('form','Сохранить исходную форму','Архив сохранил точность, но потребовал проводника.',{'memory':2,'truth':2}),
('voice','Перевести на живой язык','Смысл снова заговорил, но форма начала меняться.',{'voice':2,'unity':1}),
('dialogue','Показать обе версии рядом','Прошлое и настоящее вступили в честный диалог.',{'culture':1,'curiosity':2})]),
('Символ без подписи','Символ узнают многие, но объяснить могут не все. Как вернуть ему смысл?',[
('protect','Оставить без изменений','Архив защитил знак, но сделал его труднее для нового читателя.',{'memory':2,'culture':2}),
('story','Объяснить через личную историю','Символ получил человеческий голос.',{'human':2,'voice':1}),
('rebuild','Создать новую форму','Традиция получила новый носитель и новый риск.',{'future':2,'courage':1})])],
'science': [
('Цена открытия','Открытие готово, но последствия не ясны. Что важнее сейчас?',[
('launch','Дать миру возможность','Будущее открылось раньше, чем общество успело подготовиться.',{'future':2,'courage':2}),
('verify','Остановиться и проверить','Архив принял цену задержки ради ответственности.',{'responsibility':2,'truth':2}),
('share','Открыть данные для обсуждения','Решение стало коллективным, но потеряло скорость.',{'unity':2,'curiosity':1})]),
('Неудачный эксперимент','Результат не подтвердил гипотезу. Что делать с этой страницей?',[
('publish','Сохранить неудачу целиком','Ошибка стала знанием и защитила будущих исследователей.',{'truth':2,'responsibility':1}),
('repeat','Повторить другим способом','Сомнение открыло новую ветку поиска.',{'curiosity':2,'courage':1}),
('teach','Превратить в урок','Неудача стала частью общего опыта.',{'unity':2,'future':1})])],
'history': [
('Неполный источник','Документ сохранился частично. Как показать его будущим читателям?',[
('literal','Показать только сохранившееся','Пробел остался честным, но история стала тише.',{'truth':2,'memory':1}),
('context','Добавить проверенный контекст','Фрагмент получил горизонт и ответственность редактора.',{'curiosity':2,'responsibility':1}),
('voices','Сопоставить разные свидетельства','История заговорила несколькими голосами.',{'human':2,'unity':1})]),
('Спор об эпохе','Два свидетельства противоречат друг другу. Что станет основой рассказа?',[
('evidence','Лучше подтверждённое','Точность победила удобную версию.',{'truth':2,'responsibility':1}),
('both','Оба взгляда рядом','Противоречие осталось частью памяти.',{'curiosity':2,'human':1}),
('question','Оставить открытый вопрос','Архив отказался притворяться, что знает всё.',{'courage':1,'future':2})])],
'memory': [
('Имя или число','В Архиве осталось мало места. Что нельзя потерять?',[
('names','Имена и личные судьбы','История сохранила человека, но потеряла часть масштаба.',{'human':2,'memory':1}),
('facts','Проверенные факты и даты','Общая память получила основание, но стала холоднее.',{'truth':2,'responsibility':1}),
('letters','Письма и голоса очевидцев','Интонация пережила сухую справку.',{'human':2,'unity':1})]),
('Трудная память','История вызывает спор и боль. Как говорить о ней?',[
('quiet','Бережно, без громких выводов','Тишина стала формой уважения.',{'memory':2,'responsibility':1}),
('direct','Прямо, не скрывая сложного','Честность сохранила трудную правду.',{'truth':2,'courage':1}),
('together','Через разговор поколений','Память стала общей работой.',{'unity':2,'human':1})])],
'open': [
('Пространство, которое осталось с тобой','Что вы унесёте из открытых пространств дальше?',[
('question','Новый вопрос','Маршрут продолжился после завершения события.',{'curiosity':2,'future':1}),
('image','Образ, который хочется сохранить','Культурная память закрепилась в символе.',{'culture':2,'memory':1}),
('story','Историю, которую расскажу другому','Наследие начало жить в передаче.',{'voice':2,'unity':1})]),
('Последний свободный фрагмент','Архив позволяет сохранить только один след. Что выберете?',[
('past','Подлинный фрагмент прошлого','Основание осталось узнаваемым.',{'memory':2,'truth':1}),
('person','Личную реакцию участника','Культура продолжилась через человека.',{'human':2,'voice':1}),
('project','Идею для нового действия','Сохранение стало началом будущего проекта.',{'future':2,'courage':1})])],
}

async def init_v7():
    await game.db.execute('''CREATE TABLE IF NOT EXISTS decision_tree_choices(
        user_id INTEGER NOT NULL, game_id TEXT NOT NULL, node_key TEXT NOT NULL,
        option_code TEXT NOT NULL, option_title TEXT NOT NULL, consequence TEXT NOT NULL,
        effects_json TEXT NOT NULL, path_signature TEXT NOT NULL, depth INTEGER NOT NULL,
        created_at TEXT NOT NULL, PRIMARY KEY(user_id, game_id))''')

async def rows(uid):
    return await game.db.all('SELECT * FROM decision_tree_choices WHERE user_id=? ORDER BY depth', (uid,))

async def scores(uid):
    total = Counter()
    for row in await rows(uid):
        total.update(json.loads(row['effects_json']))
    return total

def dominant(total):
    return total.most_common(1)[0][0] if total else 'curiosity'

def item_index(item):
    pair = sorted([x for x in GAMES_BY_ID.values() if x.team == item.team and x.location == item.location], key=lambda x:x.game_id)
    return 0 if pair and pair[0].game_id == item.game_id else 1

def node_for(item, history, total):
    title, prompt, options = NODES[item.location][item_index(item)]
    lead = dominant(total)
    previous = history[-1]['option_code'] if history else 'origin'
    contexts = {
      'memory':'Ранее вы выбрали сохранение. Теперь цена этого решения стала заметнее.',
      'truth':'Архив помнит вашу требовательность к точности. Следующий выбор проверит её предел.',
      'voice':'Вы дали памяти живой голос. Теперь нужно решить, что допустимо изменить ради понимания.',
      'responsibility':'Вы уже замедляли путь ради ответственности. Архив ставит новую границу.',
      'future':'Вы открывали дорогу будущему. Следующий шаг покажет, что останется позади.',
      'unity':'Вы искали общее решение. Теперь разные голоса требуют нового выбора.',
      'culture':'Вы защищали культурный код. Теперь он должен встретиться с новым временем.',
      'courage':'Вы рискнули раньше. Архив проверяет, готовы ли вы принять последствия.',
      'human':'Вы ставили человека в центр. Теперь личная история спорит с общей картиной.',
      'curiosity':'Вы оставляли вопросы открытыми. Следующая страница не даст простого ответа.'}
    if history:
        prompt = contexts[lead] + '\n\n' + prompt
    return f'{item.location}:{item_index(item)}:{lead}:{previous}', title, prompt, options

def choice_text(options):
    marks=('1️⃣','2️⃣','3️⃣')
    return '\n\n'.join(f'<b>{marks[i]}</b> {game.escape(o[1])}\n<i>{game.escape(o[2])}</i>' for i,o in enumerate(options))

async def show_branch(target, uid, item):
    history, total = await rows(uid), await scores(uid)
    _, title, prompt, options = node_for(item, history, total)
    await target.answer('┏━━━━━━━━━━━━━━┓\n   <b>ВЫБОР ХРАНИТЕЛЯ</b>\n┗━━━━━━━━━━━━━━┛\n\n'
        f'<b>{game.escape(title)}</b>\n\n{game.escape(prompt)}\n\n{choice_text(options)}\n\n'
        '<i>Здесь нет правильного ответа. Каждый вариант меняет следующую ветвь и финальную легенду.</i>',
        reply_markup=game.inline_buttons([(('1️⃣','2️⃣','3️⃣')[i],f'v7:choose:{item.game_id}:{i}') for i in range(3)],columns=3))

@router.callback_query(F.data=='tq:games')
async def game_list(callback: CallbackQuery):
    await init_v7(); user=await game.get_user(callback.from_user.id)
    if not is_assigned(user):
        await callback.answer('Сначала получите команду.',show_alert=True); return
    await callback.answer(); passed=await passed_games(callback.from_user.id)
    chosen={r['game_id'] for r in await rows(callback.from_user.id)}; items=ordered_games(user['team'])
    lines=[f'<b>Дерево пути команды «{game.escape(user["team"])}»</b>',
           f'Знания: {progress_bar(len(passed),10)} {len(passed)}/10',
           f'Развилки: {progress_bar(len(chosen),10)} {len(chosen)}/10','',
           'Каждая развилка меняет контекст следующего решения.']; buttons=[]
    for n,item in enumerate(items,1):
        unlocked=await game_is_unlocked(user,item)
        if item.game_id in chosen: marker,state='✓','ветвь сохранена'
        elif item.game_id in passed: marker,state='🧭','нужен выбор'; buttons.append((f'🧭 {n}. Выбор',f'v7:branch:{item.game_id}'))
        elif unlocked: marker,state='▶','доступна'; buttons.append((f'▶ {n}. Играть',f'tq:game:{item.game_id}'))
        else: marker,state='🔒','закрыта маршрутом'
        lines.append(f'{marker} <b>{n}. {game.escape(item.title)}</b> · {state}')
    await callback.message.answer('\n'.join(lines),reply_markup=game.inline_buttons(buttons) if buttons else None)

@router.callback_query(F.data.startswith('tq:game:'))
async def open_game(callback: CallbackQuery):
    await init_v7(); gid=callback.data.split(':',2)[2]; item=GAMES_BY_ID.get(gid); user=await game.get_user(callback.from_user.id)
    if not item or not is_assigned(user) or item.team!=user['team']:
        await callback.answer('Эта миссия не принадлежит вашей команде.',show_alert=True); return
    if not await game_is_unlocked(user,item):
        await callback.answer('Миссия закрыта живым маршрутом.',show_alert=True); return
    if await game.db.one('SELECT 1 FROM decision_tree_choices WHERE user_id=? AND game_id=?',(callback.from_user.id,gid)):
        await callback.answer('Эта ветвь уже сохранена.',show_alert=True); return
    passed=await game.db.one('SELECT passed FROM team_game_progress WHERE user_id=? AND game_id=?',(callback.from_user.id,gid))
    if passed and passed['passed']:
        await callback.answer(); await show_branch(callback.message,callback.from_user.id,item); return
    options=presented_options(item); await callback.answer()
    await callback.message.answer('╭────────────────╮\n   <b>ФРАГМЕНТ ЗНАНИЯ</b>\n╰────────────────╯\n\n'
      f'<b>{game.escape(item.title)}</b>\n<i>{game.escape(LOCATION_TITLES[item.location])}</i>\n\n'
      f'{game.escape(item.prompt)}\n\n{option_text(options)}\n\n<i>Сначала восстановите факт. Затем начнётся выбор без правильного ответа.</i>',
      reply_markup=option_keyboard(f'tq:answer:{gid}',len(options)))

@router.callback_query(F.data.startswith('tq:answer:'))
async def answer(callback: CallbackQuery):
    await init_v7(); p=callback.data.split(':')
    if len(p)!=4 or not p[3].isdigit(): return
    gid,index=p[2],int(p[3]); item=GAMES_BY_ID.get(gid); user=await game.get_user(callback.from_user.id)
    if not item or not is_assigned(user) or item.team!=user['team']: return
    options=presented_options(item)
    if index>=len(options): return
    old=await game.db.one('SELECT attempts FROM team_game_progress WHERE user_id=? AND game_id=?',(callback.from_user.id,gid)); attempts=int(old['attempts'])+1 if old else 1
    correct=index==presented_correct_index(item)
    await game.db.execute('''INSERT INTO team_game_progress(user_id,game_id,attempts,passed,completed_at) VALUES(?,?,?,?,?)
      ON CONFLICT(user_id,game_id) DO UPDATE SET attempts=excluded.attempts,passed=MAX(team_game_progress.passed,excluded.passed),completed_at=CASE WHEN excluded.passed=1 THEN excluded.completed_at ELSE team_game_progress.completed_at END''',
      (callback.from_user.id,gid,attempts,1 if correct else 0,utcnow() if correct else None)); await callback.answer()
    if not correct:
        await callback.message.edit_text('╭────────────────╮\n   <b>ФРАГМЕНТ НЕ СОШЁЛСЯ</b>\n╰────────────────╯\n\n'+game.escape(item.hint)+f'\n\nПопытка: {attempts}.',reply_markup=game.inline_buttons([('↻ Собрать снова',f'tq:game:{gid}')]))
        return
    await callback.message.edit_text('┏━━━━━━━━━━━━━━┓\n   <b>ФРАГМЕНТ ВОССТАНОВЛЕН</b>\n┗━━━━━━━━━━━━━━┛\n\n'+game.escape(item.success)+'\n\n<b>Но знание — только первая половина.</b>\nТеперь Архив спросит, как именно вы поступите с этим наследием.',reply_markup=game.inline_buttons([('🧭 Перейти к выбору',f'v7:branch:{gid}')]))

@router.callback_query(F.data.startswith('v7:branch:'))
async def branch(callback: CallbackQuery):
    gid=callback.data.rsplit(':',1)[1]; item=GAMES_BY_ID.get(gid)
    if not item: return
    if await game.db.one('SELECT 1 FROM decision_tree_choices WHERE user_id=? AND game_id=?',(callback.from_user.id,gid)):
        await callback.answer('Выбор уже сохранён.',show_alert=True); return
    await callback.answer(); await show_branch(callback.message,callback.from_user.id,item)

@router.callback_query(F.data.startswith('v7:choose:'))
async def choose(callback: CallbackQuery):
    await init_v7(); p=callback.data.split(':')
    if len(p)!=4 or not p[3].isdigit(): return
    gid,index=p[2],int(p[3]); item=GAMES_BY_ID.get(gid); user=await game.get_user(callback.from_user.id)
    if not item or not is_assigned(user) or item.team!=user['team']: return
    history,total=await rows(callback.from_user.id),await scores(callback.from_user.id); node_key,_,_,options=node_for(item,history,total)
    if index>=len(options): return
    code,title,consequence,effects=options[index]; signature='>'.join([r['option_code'] for r in history]+[code])
    try:
        await game.db.execute('INSERT INTO decision_tree_choices VALUES(?,?,?,?,?,?,?,?,?,?)',(callback.from_user.id,gid,node_key,code,title,consequence,json.dumps(effects,ensure_ascii=False),signature,len(history)+1,utcnow()))
    except Exception:
        await callback.answer('Этот выбор уже сохранён.',show_alert=True); return
    await callback.answer(); total.update(effects); lead=dominant(total); icon,label=VALUES[lead]
    await callback.message.edit_text('┏━━━━━━━━━━━━━━┓\n   <b>ВЕТВЬ СОХРАНЕНА</b>\n┗━━━━━━━━━━━━━━┛\n\n'
      f'<b>{game.escape(title)}</b>\n\n{game.escape(consequence)}\n\n{icon} Сейчас сильнее проявляется: <b>{label}</b>\n'
      f'Путь: {progress_bar(len(history)+1,10)} {len(history)+1}/10\n\n<i>Следующая ситуация изменится с учётом этого решения.</i>',
      reply_markup=game.inline_buttons([('🎮 Продолжить путь','tq:games'),('📜 Моя легенда','v7:legend')]))

async def legend_text(uid,final=False):
    user=await game.get_user(uid); history=await rows(uid); total=await scores(uid); ranked=total.most_common(); top=[k for k,_ in ranked[:2]]
    title=PAIR_TITLES.get(frozenset(top)) if len(top)==2 else None
    if not title: title=f'Хранитель линии «{VALUES[top[0]][1]}»' if top else 'Хранитель незавершённого пути'
    base,desc=TEAM_BASE.get(user['team'],('Неизвестный свод','Архив ещё формирует вашу историю.'))
    lines=['╭──────────────────╮',f'   <b>{"ФИНАЛЬНАЯ" if final else "ТЕКУЩАЯ"} ЛЕГЕНДА</b>','╰──────────────────╯','',f'<b>{game.escape(title)}</b>',f'<i>{base} · команда «{game.escape(user["team"])}»</i>','',desc,'']
    if ranked:
        lines.append('<b>Сильные линии</b>'); maximum=max(v for _,v in ranked)
        for key,score in ranked[:5]:
            blocks=max(1,round(score/maximum*5)); lines.append(f'{VALUES[key][0]} {VALUES[key][1]}  {"■"*blocks}{"□"*(5-blocks)}')
    lines+=['','<b>Последние развилки</b>',' → '.join(game.escape(r['option_title']) for r in history[-5:]) or 'путь ещё не начат']
    if final:
        weak=ranked[-1][0] if ranked else 'memory'; lines+=['',f'<b>Сохранено сильнее всего:</b> {VALUES[top[0]][1] if top else "путь"}',f'<b>Хрупкая линия:</b> {VALUES[weak][1]}','','<i>Это не оценка. Это версия Архива, созданная вашими решениями.</i>','','<b>Архив закрывается. Память — нет.</b>']
    else: lines+=['',f'<i>Развилок: {len(history)}/10. Итог скрыт до общего финала.</i>']
    return '\n'.join(lines)

@router.callback_query(F.data=='v7:legend')
async def legend_cb(callback: CallbackQuery):
    await callback.answer(); await callback.message.answer(await legend_text(callback.from_user.id))

@router.message(Command('legend'))
async def legend_cmd(message: Message):
    await init_v7(); await message.answer(await legend_text(message.from_user.id))

async def final_report(target: Message,uid: int):
    await init_v7(); user=await game.get_user(uid)
    if not is_assigned(user): await target.answer('Финал откроется после назначения команды.'); return
    done=await completed_locations(user); team_choices=await game.team_choices(user['event_date'],user['team']); history=await rows(uid); opened=await game.db.setting('final_open','0')
    if opened!='1' or len(done)<5 or len(team_choices)<4:
        await target.answer('<b>◻️ ЭФФЕКТ БАБОЧКИ ЗАКРЫТ</b>\n\n'+f'Маршрут: {progress_bar(len(done),5)} {len(done)}/5\nКомандные решения: {progress_bar(len(team_choices),4)} {len(team_choices)}/4\nЛичные развилки: {progress_bar(len(history),10)} {len(history)}/10\n\nПоследствия не раскрываются до решения главного Архивариуса.'); return
    await target.answer('…\n\n<b>Архив завершает реконструкцию.</b>\nНе закрывайте чат.')
    await target.answer('▓▓▓▓░░░░░░ 41%\n\nСопоставляем маршруты, решения и человеческие голоса…')
    await target.answer('▓▓▓▓▓▓▓▓▓▓ 100%\n\n<b>АРХИВ ВОССТАНОВЛЕН</b>\nНо он стал другим — потому что его сохраняли вы.')
    await target.answer(await legend_text(uid,True))
