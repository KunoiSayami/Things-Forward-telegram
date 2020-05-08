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
from threading import Lock
from typing import List, NoReturn, Tuple

from pyrogram import Photo

from libpy3.mysqldb import MySqlDB


class _checkfile(MySqlDB):
	min_resolution = 120
	def __init__(self, host: str, username: str, password: str, database: str):
		self.lock = Lock()
		super().__init__(host, username, password, database, autocommit=True)

	def check(self, sql: str, exec_sql: str, args=()) -> bool:
		with self.lock:
			try:
				if self.query1(sql, args) is None:
					self.execute(exec_sql, args)
					return True
				else:
					return False
			except:
				return False

	def checkFile(self, file_id: str) -> bool:
		return self.check("SELECT `id` FROM `file_id` WHERE `id` = %s",
			"INSERT INTO `file_id` (`id`,`timestamp`) VALUES (%s, CURRENT_TIMESTAMP())", file_id)

	def checkFile_dirty(self, file_id: str) -> bool:
		return self.query1("SELECT `id` FROM `file_id` WHERE `id` = %s", file_id) is None

	def insert_log(self, *args: Tuple[str, ...]) -> NoReturn:
		self.execute("INSERT INTO `msg_detail` (`to_chat`, `to_msg`, `from_chat`, `from_id`, `from_user`, `from_forward`) \
			VALUES (%s, %s, %s, %s, %s, %s)", args)

	@staticmethod
	def check_photo(photo: Photo) -> bool:
		return not (photo.file_size / (photo.width * photo.height) * 1000 < _checkfile.min_resolution or photo.file_size < 40960)

	def update_forward_target(self, chat_id: int, target: str):
		if self.query1("SELECT * FROM `special_forward` WHERE `chat_id` = %s", chat_id):
			self.execute("UPDATE `special_forward` SET `target` = %s WHERE `chat_id` = %s", (target, chat_id))
		else:
			self.execute("INSERT INTO `special_forward` (`chat_id`, `target`) VALUE (%s, %s)", (chat_id, target))

	def insert_blacklist(self, user_ids: int or tuple):
		self.execute("INSERT INTO `blacklist` (`id`) VALUES (%s)", user_ids, isinstance(user_ids, (tuple, list)))

	def remove_blacklist(self, user_id: int):
		self.execute("DELETE FROM `blacklist` WHERE `id` = %s", user_id)

	def query_user(self, user_id: int) -> dict:
		return self.query1("SELECT * FROM `user_list` WHERE `id` = %s", user_id)

	def insert_bypass(self, user_id: int):
		if self.query_user(user_id):
			self.execute("UPDATE `user_list` SET `bypass` = 'Y' WHERE `id` = %s", user_id)
		else:
			self.execute("INSERT INTO `user_list` (`id`, `bypass`) VALUE (%s, 'Y')", user_id)

	def insert_admin(self, user_id: int):
		if self.query_user(user_id):
			self.execute("UPDATE `user_list` SET `authorized` = 'Y' WHERE `id` = %s", user_id)
		else:
			self.execute("INSERT INTO `user_list` (`id`, `authorized`) VALUE (%s, 'Y')", user_id)

	def remove_admin(self, user_id: int):
		self.execute("UPDATE `user_list` SET `authorized` = 'N' WHERE `id` = %s", user_id)
	
	def query_all_admin(self) -> list:
		return [x['id'] for x in self.query("SELECT `id` FROM `user_list` WHERE `authorized` = 'Y'")]

	def query_all_bypass(self) -> list:
		return [x['id'] for x in self.query("SELECT `id` FROM `user_list` WHERE `bypass` = 'Y'")]
	
	def query_all_blacklist(self) -> list:
		return [x['id'] for x in self.query("SELECT `id` FROM `blacklist`")]

	def query_all_special_forward(self) -> dict:
		return {x['chat_id']: x['target'] for x in self.query("SELECT * FROM `special_forward`")}

	def query_forward_from(self, chat_id: int, message_id: int) -> dict:
		return self.query1("SELECT `from_chat`, `from_user`, `from_forward` FROM `msg_detail` WHERE `to_chat` = %s AND `to_msg` = %s", (chat_id, message_id))

class checkfile(_checkfile):
	_instance = None
	@staticmethod
	def get_instance() -> _checkfile:
		return checkfile._instance

	@staticmethod
	def init_instance(host: str, username: str, password: str, database: str) -> _checkfile:
		checkfile._instance = _checkfile(host, username, password, database)
		return checkfile._instance

	@staticmethod
	def close_instance() -> None:
		checkfile._instance.close()
