# -*- coding: utf-8 -*-
# helper.py
# Copyright (C) 2020-2022 KunoiSayami
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
from __future__ import annotations

import logging
import random
import string
from collections.abc import Iterable
from typing import Optional, Sequence, Union

import aioredis
import asyncpg
from pyrogram.types import Photo

from libpy3.aiopgsqldb import PgSQLdb

logger = logging.getLogger("forwarder.pgsql")
logger.setLevel(logging.DEBUG)


class CheckFile(PgSQLdb):
    min_resolution = 120

    async def check(self, sql: str, exec_sql: str, *args) -> bool:
        try:
            if await self.query1(sql, *args) is None:
                await self.execute(exec_sql, *args)
                return True
            else:
                return False
        except asyncpg.PostgresError:
            logger.exception("Got postgresql exception error")
            return False

    async def check_file(self, file_id: str) -> bool:
        return await self.check(
            """SELECT "id" FROM "file_id" WHERE "id" = $1""",
            """INSERT INTO "file_id" VALUES ($1, CURRENT_TIMESTAMP)""",
            file_id,
        )

    async def check_file_dirty(self, file_id: str) -> bool:
        return (
            await self.query1("""SELECT "id" FROM "file_id" WHERE "id" = $1""", file_id)
            is None
        )

    async def insert_log(self, *args) -> None:
        await self.execute(
            """INSERT INTO "msg_detail" 
        ("to_chat", "to_msg", "from_chat", "from_id", "from_user", "forward_from") 
        VALUES ($1, $2, $3, $4, $5, $6)""",
            *args,
        )

    @staticmethod
    def check_photo(photo: Photo) -> bool:
        return not (
            photo.file_size / (photo.width * photo.height) * 1000
            < CheckFile.min_resolution
            or photo.file_size < 40960
        )

    async def update_forward_target(self, chat_id: int, target: str) -> None:
        if await self.query1(
            """SELECT * FROM "special_forward" WHERE "chat_id" = $1""", chat_id
        ):
            await self.execute(
                """UPDATE "special_forward" SET "target" = $1 WHERE "chat_id" = $2""",
                target,
                chat_id,
            )
        else:
            await self.execute(
                """INSERT INTO "special_forward" ("chat_id", "target") VALUES ($1, $2)""",
                chat_id,
                target,
            )

    async def insert_blacklist(self, user_ids: Union[int, Sequence[int]]) -> None:
        await self.execute(
            """INSERT INTO "blacklist" ("id") VALUES ($1)""",
            user_ids,
            isinstance(user_ids, Iterable),
        )

    async def remove_blacklist(self, user_id: int) -> None:
        await self.execute("""DELETE FROM "blacklist" WHERE "id" = $1""", user_id)

    async def query_user(self, user_id: int) -> Optional[asyncpg.Record]:
        return await self.query1(
            """SELECT * FROM "user_list" WHERE "id" = $1""", user_id
        )

    async def insert_bypass(self, user_id: int) -> None:
        if await self.query_user(user_id):
            await self.execute(
                """UPDATE "user_list" SET "bypass" = true WHERE "id" = $1""", user_id
            )
        else:
            await self.execute(
                """INSERT INTO "user_list" ("id", "bypass") VALUES ($1, true)""",
                user_id,
            )

    async def insert_admin(self, user_id: int) -> None:
        if await self.query_user(user_id):
            await self.execute(
                """UPDATE "user_list" SET "authorized" = true WHERE "id" = $1""",
                user_id,
            )
        else:
            await self.execute(
                """INSERT INTO "user_list" ("id", "authorized") VALUES ($1, true)""",
                user_id,
            )

    async def remove_admin(self, user_id: int) -> None:
        await self.execute(
            """UPDATE "user_list" SET "authorized" = false WHERE "id" = $1""", user_id
        )

    async def query_all_admin(self) -> list[int]:
        return [
            x["id"]
            for x in await self.query(
                """SELECT "id" FROM "user_list" WHERE "authorized" = true"""
            )
        ]

    async def query_all_bypass(self) -> list[int]:
        return [
            x["id"]
            for x in await self.query(
                """SELECT "id" FROM "user_list" WHERE "bypass" = true"""
            )
        ]

    async def query_all_blacklist(self) -> list[int]:
        return [x["id"] for x in await self.query('''SELECT "id" FROM "blacklist"''')]

    async def query_all_special_forward(self) -> dict[str, str]:
        return {
            str(x["chat_id"]): str(x["target"])
            for x in await self.query('''SELECT * FROM "special_forward"''')
        }

    async def query_forward_from(
        self, chat_id: int, message_id: int
    ) -> asyncpg.Record | None:
        return await self.query1(
            """SELECT "from_chat", "from_user", "forward_from" 
            FROM "msg_detail" WHERE "to_chat" = $1 AND "to_msg" = $2""",
            chat_id,
            message_id,
        )  # type: ignore

    _instance = None

    @classmethod
    def get_instance(cls) -> CheckFile:
        if cls._instance is None:
            raise RuntimeError("Instance not initialized")
        return cls._instance

    @classmethod
    async def init_instance(
        cls, host: str, port: int, username: str, password: str, database: str
    ) -> CheckFile:
        cls._instance = await cls.create(host, port, username, password, database)
        return cls._instance

    @classmethod
    async def close_instance(cls) -> None:
        await CheckFile._instance.close()


class RedisHelper:
    def __init__(self, redis_conn: aioredis.Redis, prefix: str):
        self.conn = redis_conn
        self.prefix = prefix

    async def _basic_s_methods(self, method: str, client_id: list[int] | int) -> int:
        if isinstance(client_id, int):
            client_id = [client_id]
        return await self.conn.sadd(f"{self.prefix}for_{method}", *client_id)

    async def add_bypass(self, client_id: list[int] | int) -> int:
        return await self._basic_s_methods("bypass", client_id)

    async def add_blacklist(self, client_id: list[int] | int) -> int:
        return await self._basic_s_methods("blacklist", client_id)

    async def add_admin(self, client_id: list[int] | int) -> int:
        return await self._basic_s_methods("admin", client_id)

    async def delete_blacklist(self, client_id: int) -> None:
        return await self.conn.srem(f"{self.prefix}for_blacklist", client_id)

    async def delete_admin(self, client_id: int) -> None:
        return await self.conn.srem(f"{self.prefix}for_admin", client_id)

    async def set(self, key: str, value: str) -> None:
        await self.set(key, value)

    async def mset(self, mp: dict[str, str]) -> None:
        await self.conn.mset(mp)

    async def clean(self, mp: dict[str, str]) -> None:
        await self.conn.delete(f"{self.prefix}for_bypass")
        await self.conn.delete(f"{self.prefix}for_blacklist")
        await self.conn.delete(" ".join(map(str, (key for key, _ in mp.items()))))
        await self.conn.delete(f"{self.prefix}for_admin")

    async def _basic_s_query(self, method: str, client_id: int) -> bool:
        return await self.conn.sismember(f"{self.prefix}for_{method}", client_id)

    async def query_admin(self, client_id: int) -> bool:
        return await self._basic_s_query("admin", client_id)

    async def query_blacklist(self, client_id: int) -> bool:
        return await self._basic_s_query("blacklist", client_id)

    async def query_bypass(self, client_id: int) -> bool:
        return await self._basic_s_query("bypass", client_id)

    async def query_channel_mapping(self, client_id: int) -> int | None:
        if result := await self.conn.get(f"{client_id}"):
            return int(result)
        return None

    async def get(self, key: str) -> bytes | None:
        return await self.conn.get(key)

    @classmethod
    async def new(cls, sql_conn: CheckFile, owner: int = 0) -> RedisHelper:
        redis_ = await aioredis.from_url("redis://localhost")
        prefix = "".join(random.choices(string.ascii_lowercase, k=5))
        self = cls(redis_, prefix)
        await self.add_admin(await sql_conn.query_all_admin())
        await self.add_blacklist(await sql_conn.query_all_blacklist())
        await self.add_bypass(await sql_conn.query_all_bypass())
        await self.mset(await sql_conn.query_all_special_forward())
        if owner != 0:
            await self.add_admin(owner)
        return self

    async def close(self) -> None:
        await self.conn.close()


class ClientRedisHelper(RedisHelper):
    from pyrogram.types import Message

    async def check_msg_from_blacklist(self, msg: Message) -> bool:
        if await self.query_blacklist(msg.chat.id):
            return True
        if msg.from_user and await self.query_blacklist(msg.from_user.id):
            return True
        if msg.sender_chat and await self.query_blacklist(msg.sender_chat.id):
            return True
        if msg.forward_from and await self.query_blacklist(msg.forward_from.id):
            return True
        if msg.forward_from_chat and await self.query_blacklist(
            msg.forward_from_chat.id
        ):
            return True
        return False

    async def check_msg_from_admin(self, msg: Message) -> bool:
        return await self.query_admin(msg.chat.id)
