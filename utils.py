# -*- coding: utf-8 -*-
# getitem.py
# Copyright (C) 2018-2019 KunoiSayami
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
from pyrogram import Message
def get_msg_key(msg: Message, key1: str, key2: str, fallback: object=None) -> object:
	try:
		return msg[key1][key2]
	except:
		return fallback

def get_forward_id(msg: Message, fallback: object=None) -> int:
	if msg.forward_from_chat: return msg.forward_from_chat.id
	if msg.forward_from: return msg.forward_from.id
	return fallback

def get_msg_from(msg: Message) -> int:
	return msg.from_user.id if msg.from_user else msg.chat.id

def is_bot(msg: Message) -> bool:
	return any((
		msg.from_user and msg.from_user.is_bot,
		msg.forward_from and msg.forward_from.is_bot
		))

class log_struct:
	def __init__(self, need_log: bool, fmt_log: str = '', *fmt_args):
		self.need_log = need_log
		self.fmt_log = fmt_log
		self.fmt_args = fmt_args

class forward_request:
	def __init__(self, target_id: int, chat_id: int, msg_id: int or tuple, Log_info: log_struct):
		self.target_id = target_id
		self.chat_id = chat_id
		self.msg_id = msg_id
		self.Log_info = Log_info