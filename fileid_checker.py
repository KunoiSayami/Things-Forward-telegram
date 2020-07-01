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
from typing import Dict, List, Sequence, Tuple, TypeVar, Union

import aiomysql
from pyrogram import Photo

from libpy3.aiomysqldb import MySqlDB

mixedType = TypeVar('mixedType', str, int)

class checkfile(MySqlDB):
    min_resolution = 120
    def __init__(self,
            host: str,
            user: str,
            password: str,
            db: str,
            charset: str='utf8mb4',
            cursorclass: aiomysql.Cursor=aiomysql.DictCursor
        ):
        self.checker_lock = asyncio.Lock()
        super().__init__(host, user, password, db, charset, cursorclass)

    async def check(self, sql: str, exec_sql: str, args=()) -> bool:
        async with self.checker_lock:
            try:
                if await self.query1(sql, args) is None:
                    await self.execute(exec_sql, args)
                    return True
                else:
                    return False
            except:
                return False

    async def checkFile(self, file_id: str) -> bool:
        return await self.check("SELECT `id` FROM `file_id` WHERE `id` = %s",
            "INSERT INTO `file_id` (`id`,`timestamp`) VALUES (%s, CURRENT_TIMESTAMP())", file_id)

    async def checkFile_dirty(self, file_id: str) -> bool:
        return await self.query1("SELECT `id` FROM `file_id` WHERE `id` = %s", file_id) is None

    async def insert_log(self, *args: Tuple[Tuple[mixedType, ...], ...]) -> None:
        await self.execute("INSERT INTO `msg_detail` (`to_chat`, `to_msg`, `from_chat`, `from_id`, `from_user`, `from_forward`) \
            VALUES (%s, %s, %s, %s, %s, %s)", args) # type: ignore

    @classmethod
    def check_photo(cls, photo: Photo) -> bool:
        return not (photo.file_size / (photo.width * photo.height) * 1000 < cls.min_resolution or photo.file_size < 40960)

    async def update_forward_target(self, chat_id: int, target: str) -> None:
        if await self.query1("SELECT * FROM `special_forward` WHERE `chat_id` = %s", chat_id):
            await self.execute("UPDATE `special_forward` SET `target` = %s WHERE `chat_id` = %s", (target, chat_id)) # type: ignore
        else:
            await self.execute("INSERT INTO `special_forward` (`chat_id`, `target`) VALUE (%s, %s)", (chat_id, target)) # type: ignore

    async def insert_blacklist(self, user_ids: Union[int, Sequence[int]]) -> None:
        await self.execute("INSERT INTO `blacklist` (`id`) VALUES (%s)", user_ids, isinstance(user_ids, Iterable))

    async def remove_blacklist(self, user_id: int) -> None:
        await self.execute("DELETE FROM `blacklist` WHERE `id` = %s", user_id)

    async def query_user(self, user_id: int) -> Dict[str, Union[bool, int]]:
        return await self.query1("SELECT * FROM `user_list` WHERE `id` = %s", user_id) # type: ignore

    async def insert_bypass(self, user_id: int) -> None:
        if await self.query_user(user_id):
            await self.execute("UPDATE `user_list` SET `bypass` = 'Y' WHERE `id` = %s", user_id)
        else:
            await self.execute("INSERT INTO `user_list` (`id`, `bypass`) VALUE (%s, 'Y')", user_id)

    async def insert_admin(self, user_id: int) -> None:
        if await self.query_user(user_id):
            await self.execute("UPDATE `user_list` SET `authorized` = 'Y' WHERE `id` = %s", user_id)
        else:
            await self.execute("INSERT INTO `user_list` (`id`, `authorized`) VALUE (%s, 'Y')", user_id)

    async def remove_admin(self, user_id: int) -> None:
        await self.execute("UPDATE `user_list` SET `authorized` = 'N' WHERE `id` = %s", user_id)
    
    async def query_all_admin(self) -> List[int]:
        return [x['id'] for x in await self.query("SELECT `id` FROM `user_list` WHERE `authorized` = 'Y'")] # type: ignore

    async def query_all_bypass(self) -> List[int]:
        return [x['id'] for x in await self.query("SELECT `id` FROM `user_list` WHERE `bypass` = 'Y'")] # type: ignore
    
    async def query_all_blacklist(self) -> List[int]:
        return [x['id'] for x in await self.query("SELECT `id` FROM `blacklist`")] # type: ignore

    async def query_all_special_forward(self) -> Dict[int, int]:
        return {x['chat_id']: x['target'] for x in await self.query("SELECT * FROM `special_forward`")} # type: ignore

    async def query_forward_from(self, chat_id: int, message_id: int) -> Dict[str, int]:
        return await self.query1("SELECT `from_chat`, `from_user`, `from_forward` FROM `msg_detail` WHERE `to_chat` = %s AND `to_msg` = %s", (chat_id, message_id)) # type: ignore

    _instance = None
    @classmethod
    def get_instance(cls) -> 'checkfile':
        if cls._instance is None:
            raise RuntimeError('Instance not initialized')
        return cls._instance

    @classmethod
    async def init_instance(cls, host: str, username: str, password: str, database: str) -> 'checkfile':
        cls._instance = await cls.create(host, username, password, database)
        return cls._instance

    @classmethod
    async def close_instance(cls) -> None:
        await checkfile._instance.close()

    @classmethod
    async def create(cls,
        host: str,
        user: str,
        password: str,
        db: str,
        charset: str='utf8mb4',
        cursorclass: aiomysql.Cursor=aiomysql.DictCursor
    ) -> 'checkfile':
        self = cls(host, user, password, db, charset, cursorclass)
        await self.init_connection()
        return self
