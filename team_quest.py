from __future__ import annotations

from aiogram import Router

import quest_admin
import quest_common
import quest_games
import quest_route

router = Router(name='last_keeper_team_quest')
router.include_router(quest_route.router)
router.include_router(quest_games.router)
router.include_router(quest_admin.router)

init_team_quest = quest_common.init_team_quest
main_menu = quest_common.main_menu
progress_bar = quest_common.progress_bar
ordered_games = quest_common.ordered_games
