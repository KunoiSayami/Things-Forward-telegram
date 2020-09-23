# -*- coding: utf-8 -*-
# config2mysql.py
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
from configparser import ConfigParser

from fileid_checker import CheckFile


async def main():
	config = ConfigParser()
	config.read('config.ini')
	conn = CheckFile.create(config.get('mysql', 'host'), config.get('mysql', 'username'), config.get('mysql', 'passwd'), config.get('mysql', 'database'))
	if input('Clear database before import? [y/N]: ').lower() == 'y':
		await conn.execute('DELETE FROM `user_list`')
		await conn.execute('DELETE FROM `blacklist`')
		await conn.execute('DELETE FROM `special_forward`')
		#conn.commit()
		print('Clear!')
	for x in map(int, config.get('forward', 'bypass_list')[1:-1].split(',')):
		await conn.insert_bypass(x)
	await conn.insert_blacklist(list(map(int, config.get('forward', 'black_list')[1:-1].split(','))))
	#for x in {x[0]: re.findall(r'\'([^\']+)\'', x[1])[0] for x in map(lambda x: x.strip().split(':'), config.get('forward', 'special')[1:-1].split(','))}.items():
	for x in {x[0]: x[1].strip()[1:-1] for x in map(lambda x: x.strip().split(':'), config.get('forward', 'special')[1:-1].split(','))}.items():
		await conn.update_forward_target(*x)
	for x in map(int, config.get('account', 'auth_users')[1:-1].split(',')):
		await conn.insert_admin(x)
	await conn.close()

if __name__ == "__main__":
	asyncio.run(main())
