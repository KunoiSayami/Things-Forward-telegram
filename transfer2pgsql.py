#!/usr/bin/env python
# -*- coding: utf-8 -*-
# transfer2pgsql.py
# Copyright (C) 2019-2020 KunoiSayami
#
# This module is part of Things-Forward-Telegram and is released under
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
import asyncpg
import aiomysql
import asyncio
from configparser import ConfigParser

from typing import Callable, Tuple, Union, Any

config = ConfigParser()
config.read('config.ini')
host = config.get('mysql', 'host')
port = config.get('pgsql', 'port')  # only for pgsql
muser = config.get('mysql', 'username')
mpasswd = config.get('mysql', 'passwd')
puser = config.get('pgsql', 'username')
ppasswd = config.get('pgsql', 'passwd')
mdatabase = config.get('mysql', 'database')
pdatabase = config.get('pgsql', 'database')


async def main() -> None:
    pgsql_connection = await asyncpg.connect(host=host, port=port, user=puser, password=ppasswd, database=pdatabase)
    mysql_connection = await aiomysql.create_pool(
        host=host,
        user=muser,
        password=mpasswd,
        db=mdatabase,
        charset='utf8mb4',
        cursorclass=aiomysql.cursors.Cursor,
    )
    if input('Do you want to delete all data? [y/N]: ').strip().lower() == 'y':
        await clean(pgsql_connection)
        print('Clear database successfully')
    else:
        print('Skipped clear database')
    async with mysql_connection.acquire() as conn:
        async with conn.cursor() as cursor:
            await exec_and_insert(cursor, "SELECT * FROM blacklist", pgsql_connection,
                                  '''INSERT INTO "blacklist" VALUES ($1)''')
            await exec_and_insert(cursor, "SELECT * FROM user_list", pgsql_connection,
                                  '''INSERT INTO "user_list" VALUES ($1, $2, $3, $4)''', transfer)
            await exec_and_insert(cursor, "SELECT * FROM file_id", pgsql_connection,
                                  '''INSERT INTO "file_id" VALUES ($1, $2)''', bigdata=True)
            await exec_and_insert(cursor, "SELECT * FROM msg_detail", pgsql_connection,
                                  '''INSERT INTO "msg_detail" VALUES ($1, $2, $3, $4, $5, $6, $7)''', bigdata=True)
            await exec_and_insert(cursor, "SELECT * FROM special_forward", pgsql_connection,
                                  '''INSERT INTO "special_forward" VALUES ($1, $2)''')
    await pgsql_connection.close()
    mysql_connection.close()
    await mysql_connection.wait_closed()


def transfer(obj: Tuple[int, str, str, str]) -> Tuple[Union[bool, Any], ...]:
    def str2bool(x: str) -> bool:
        return True if x == 'Y' else False
    return tuple(map(lambda x: str2bool(x) if isinstance(x, str) else x, obj))


async def exec_and_insert(cursor, sql: str, pg_connection, insert_sql: str,
                          process: Callable[[Any], Any] = None, bigdata: bool = False) -> None:
    print('Processing table:', sql[13:])
    if await pg_connection.fetchrow(f'{sql} LIMIT 1') is not None:
        if input(f'Table {sql[13:]} has data, do you still want to process insert? [y/N]: ').strip().lower() != 'y':
            return
    if bigdata:
        step = 0
        await cursor.execute(f'{sql} LIMIT {step}, 1000')
        obj = await cursor.fetchall()
        while True:
            print(f'\rstep: {step}', end='')
            queue = [pg_connection.executemany(insert_sql, list(obj))]
            if len(obj) == 1000:
                await cursor.execute(f'{sql} LIMIT {step + 1000}, 1000')
                queue.append(cursor.fetchall())
            rt = await asyncio.gather(*queue)
            if len(obj) < 1000:
                print()
                break
            if len(rt) > 1:
                obj = rt[1]
            step += 1000
    else:
        await cursor.execute(sql)
        obj = await cursor.fetchall()
        for sql_obj in obj:
            if process is not None:
                sql_obj = process(sql_obj)
            await pg_connection.execute(insert_sql, *sql_obj)


async def clean(pgsql_connection: asyncpg.connection) -> None:
    await pgsql_connection.execute('''TRUNCATE "blacklist"''')
    await pgsql_connection.execute('''TRUNCATE "user_list"''')
    await pgsql_connection.execute('''TRUNCATE "file_id"''')
    await pgsql_connection.execute('''TRUNCATE "msg_detail"''')
    await pgsql_connection.execute('''TRUNCATE "special_forward"''')


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())