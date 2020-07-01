# -*- coding: utf-8 -*-
# telethonlib.py
# Copyright (C) 2018-2020 KunoiSayami
#
# This module is part of Things-Forward-telegram and is released under
# the AGPL v3 License: https://www.gnu.org/licenses/agpl-3.0.txt
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
from typing import Awaitable, Callable, List

import telethon

from utils import get_chat_id

class TelethonClient:
    _instance: 'TelethonClient'

    def __init__(self, session_name: str, api_id: int, api_hash: str, *, on_album: Callable[[telethon.events.Album.Event], Awaitable[None]],**kwargs) -> None:
        self.app = telethon.TelegramClient(session_name, api_id, api_hash, **kwargs)
        self.app.add_event_handler(on_album, telethon.events.Album(func=lambda x: get_chat_id(x) < 0))

    async def start(self) -> None:
        await self.app.start()

    async def stop(self) -> None:
        await self.app.disconnect()

    async def forward_messages(self, *args) -> List[telethon.tl.patched.Message]:
        return await self.app.forward_messages(*args)

    @classmethod
    def create_instance(cls, session_name: str, api_id: int, api_hash: str, *, on_album: Callable[[telethon.events.Album.Event], Awaitable[None]],**kwargs) -> 'TelethonClient':
        cls._instance = cls(session_name, api_id, api_hash, on_album=on_album, **kwargs)
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'TelethonClient':
        return cls._instance
