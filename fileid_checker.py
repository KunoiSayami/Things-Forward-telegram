# -*- coding: utf-8 -*-
# fileid_checker.py
# Copyright (C) 2020 KunoiSayami
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
import asyncio
from collections.abc import Iterable
from typing import Dict, List, Optional, Sequence, Tuple, Union

import asyncpg
from pyrogram.types import Photo

from libpy3.aiopgsqldb import PgSQLdb


class CheckFile(PgSQLdb):
    min_resolution = 120

    async def check(self, sql: str, exec_sql: str, args=()) -> bool:
        try:
            if await self.query1(sql, args) is None:
                await self.execute(exec_sql, args)
                return True
            else:
                return False
        except:
            return False

    async def checkFile(self, file_id: str) -> bool:
        return await self.check('''SELECT "id" FROM "file_id" WHERE "id" = $1''',
                                '''INSERT INTO "file_id" VALUES ($1, CURRENT_TIMESTAMP)''', file_id)

    async def checkFile_dirty(self, file_id: str) -> bool:
        return await self.query1('''SELECT "id" FROM "file_id" WHERE "id" = $1''', file_id) is None

    async def insert_log(self, *args: Tuple[Tuple[str, ...], ...]) -> None:
        await self.execute('''INSERT INTO "msg_detail" 
        ("to_chat", "to_msg", "from_chat", "from_id", "from_user", "forward_from") 
        VALUES ($1, $2, $3, $4, $5, $6)''', *args)  # type: ignore

    @staticmethod
    def check_photo(photo: Photo) -> bool:
        return not (photo.file_size / (
                    photo.width * photo.height) * 1000 < CheckFile.min_resolution or photo.file_size < 40960)

    async def update_forward_target(self, chat_id: int, target: str) -> None:
        if await self.query1('''SELECT * FROM "special_forward" WHERE "chat_id" = $1''', chat_id):
            await self.execute('''UPDATE "special_forward" SET "target" = $1 WHERE "chat_id" = $2''',
                               target, chat_id)  # type: ignore
        else:
            await self.execute('''INSERT INTO "special_forward" ("chat_id", "target") VALUES ($1, $2)''',
                               chat_id, target)  # type: ignore

    async def insert_blacklist(self, user_ids: Union[int, Sequence[int]]) -> None:
        await self.execute('''INSERT INTO "blacklist" ("id") VALUES ($1)''', user_ids, isinstance(user_ids, Iterable))

    async def remove_blacklist(self, user_id: int) -> None:
        await self.execute('''DELETE FROM "blacklist" WHERE "id" = $1''', user_id)

    async def query_user(self, user_id: int) -> Optional[asyncpg.Record]:
        return await self.query1('''SELECT * FROM "user_list" WHERE "id" = $1''', user_id)  # type: ignore

    async def insert_bypass(self, user_id: int) -> None:
        if await self.query_user(user_id):
            await self.execute('''UPDATE "user_list" SET "bypass" = true WHERE "id" = $1''', user_id)
        else:
            await self.execute('''INSERT INTO "user_list" ("id", "bypass") VALUES ($1, true)''', user_id)

    async def insert_admin(self, user_id: int) -> None:
        if await self.query_user(user_id):
            await self.execute('''UPDATE "user_list" SET "authorized" = true WHERE "id" = $1''', user_id)
        else:
            await self.execute('''INSERT INTO "user_list" ("id", "authorized") VALUES ($1, true)''', user_id)

    async def remove_admin(self, user_id: int) -> None:
        await self.execute('''UPDATE "user_list" SET "authorized" = false WHERE "id" = $1''', user_id)

    async def query_all_admin(self) -> List[int]:
        return [x['id'] for x in
                await self.query('''SELECT "id" FROM "user_list" WHERE "authorized" = true''')]  # type: ignore

    async def query_all_bypass(self) -> List[int]:
        return [x['id'] for x in await self.query('''SELECT "id" FROM "user_list" WHERE "bypass" = true''')]  # type: ignore

    async def query_all_blacklist(self) -> List[int]:
        return [x['id'] for x in await self.query('''SELECT "id" FROM "blacklist"''')]  # type: ignore

    async def query_all_special_forward(self) -> Dict[int, int]:
        return {x['chat_id']: x['target'] for x in await self.query('''SELECT * FROM "special_forward"''')}  # type: ignore

    async def query_forward_from(self, chat_id: int, message_id: int) -> Optional[asyncpg.Record]:
        return await self.query1(
            '''SELECT "from_chat", "from_user", "forward_from" 
            FROM "msg_detail" WHERE "to_chat" = $1 AND "to_msg" = $2''',
            chat_id, message_id)  # type: ignore

    _instance = None

    @classmethod
    def get_instance(cls) -> 'CheckFile':
        if cls._instance is None:
            raise RuntimeError('Instance not initialized')
        return cls._instance

    @classmethod
    async def init_instance(cls, host: str, port: int, username: str, password: str, database: str) -> 'CheckFile':
        cls._instance = await cls.create(host, port, username, password, database)
        return cls._instance

    @classmethod
    async def close_instance(cls) -> None:
        await CheckFile._instance.close()

