# -*- coding: utf-8 -*-
# utils.py
# Copyright (C) 2018-2022 KunoiSayami
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
from dataclasses import dataclass
from typing import TypeVar

from pyrogram import Client
from pyrogram.types import Message

from configure import ConfigParser
from helper import CheckFile

T = TypeVar('T')


def get_msg_key(msg: Message, key1: str, key2: str, fallback: T = None) -> T:
    try:
        return getattr(getattr(msg, key1), key2)
    except (AttributeError, ValueError):
        return fallback


def get_forward_id(msg: Message, fallback: T = None) -> T | int:
    if msg.forward_from_chat:
        return msg.forward_from_chat.id
    if msg.forward_from:
        return msg.forward_from.id
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


class BasicForwardRequest:
    def __init__(self, msg: Message, log: LogStruct = LogStruct(False, '')):
        self.msg = msg
        self.log = log


class BlackListForwardRequest(BasicForwardRequest):
    pass


class ForwardRequest(BasicForwardRequest):

    def __init__(self, target_id: int, msg: Message, log: LogStruct = LogStruct(False, '')):
        super().__init__(msg, log)
        self.target_id = target_id

    @classmethod
    def from_super(cls, target_id: int, request: BlackListForwardRequest):
        return cls(target_id, request.msg, request.log)


class Plugin:

    @classmethod
    async def create_plugin(cls, *_args) -> Plugin:
        self = cls()
        return self

    async def plugin_start(self) -> None:
        pass

    async def plugin_pending_start(self) -> None:
        pass

    async def plugin_pending_stop(self) -> None:
        pass

    async def plugin_stop(self) -> None:
        pass


class _PluginModule:
    requirement: dict[str, bool]


@dataclass
class _Requirement:
    config: bool
    database: bool


class PluginLoader:

    def __init__(self, module: _PluginModule, module_name: str, client: Client, config: ConfigParser,
                 database: CheckFile):
        self.requirement: dict[str, bool] = module.requirement
        self.args: list[T] = [client]
        _requirement = _Requirement(self.requirement.get('config'), self.requirement.get('database'))  # type: ignore
        if _requirement.config:
            self.args.append(config)
        if _requirement.database:
            self.args.append(database)
        self.module: T = module
        self.module_name: str = module_name
        self.instance: Plugin = None  # type: ignore

    async def __call__(self) -> Plugin:
        await self.create_instance()
        return self.instance

    async def create_instance(self) -> PluginLoader:
        self.instance = await getattr(self.module, self.module_name).create_plugin(*self.args)
        return self
