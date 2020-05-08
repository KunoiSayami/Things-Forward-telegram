# -*- coding: utf-8 -*-
# getitem.py
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
from dataclasses import dataclass
from typing import Dict, List, NoReturn, T

from pyrogram import Message, Client

from configure import ConfigParser
from fileid_checker import checkfile


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

class LogStruct:
	def __init__(self, need_log: bool, fmt_log: str, *fmt_args):
		self.need_log = need_log
		self.fmt_log = fmt_log
		self.fmt_args = fmt_args

class BlackListForwardRequest:
	def __init__(self, msg: Message, log: LogStruct = LogStruct(False, '')):
		self.msg = msg
		self.log = log

class ForwardRequest(BlackListForwardRequest):
	def __init__(self, target_id: int, msg: Message, log: LogStruct = LogStruct(False, '')):
		super().__init__(msg, log)
		self.target_id = target_id
	@staticmethod
	def from_super(target_id: int, request: BlackListForwardRequest):
		return ForwardRequest(target_id, request.msg, request.log)

class Plugin:

	def plugin_start(self) -> NoReturn:
		pass

	def plugin_pending_start(self) -> NoReturn:
		pass

	def plugin_pending_stop(self) -> NoReturn:
		pass

	def plugin_stop(self) -> NoReturn:
		pass


class _PluginModule:
	requirement: Dict[str, bool]


@dataclass
class _Requirement:
	config: bool
	database: bool


class PluginLoader:
	
	def __init__(self, module: _PluginModule, module_name: str, client: Client, config: ConfigParser, database: checkfile):
		self.requirement: Dict[str, bool] = module.requirement
		self.args: List[T] = [client]
		_requirement = _Requirement(self.requirement.get('config'), self.requirement.get('database'))
		if _requirement.config:
			self.args.append(config)
		if _requirement.database:
			self.args.append(database)
		self.module: T = module
		self.module_name: str = module_name
		self.instance: Plugin = None
	
	def __call__(self) -> Plugin:
		self.create_instace()
		return self.instance

	def create_instace(self) -> 'PluginLoader':
		self.instance = getattr(self.module, self.module_name)(*self.args)
		return self
