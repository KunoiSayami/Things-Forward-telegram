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
import asyncio
from asyncio.events import TimerHandle
import datetime
import logging
import traceback
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Generator, List, Optional, Tuple, TypeVar, Union

import telethon
from pyrogram import Client, Message

from configure import ConfigParser
from fileid_checker import checkfile

T = TypeVar('T')

logger = logging.getLogger('utils')
logger.setLevel(logging.DEBUG)

def get_msg_key(msg: Message, key1: str, key2: str, fallback: T=None) -> T:
    try:
        return msg[key1][key2]
    except:
        return fallback


def get_forward_id(msg: Message, fallback: T=None) -> Union[T, int]:
    if msg.forward_from_chat: return msg.forward_from_chat.id
    if msg.forward_from: return msg.forward_from.id
    return fallback


def get_forward_id_a(msg: telethon.tl.patched.Message, fallback: T=None) -> Union[T, int]:
    if msg.fwd_from is not None:
        if msg.fwd_from.from_id:
            return msg.fwd_from.from_id
        elif msg.fwd_from.channel_id:
            return msg.fwd_from.channel_id
        elif msg.fwd_from.saved_from_peer:
            return get_peer_user_id(msg.fwd_from.saved_from_peer)
    return fallback

def get_msg_forward_from(msg: Union[telethon.tl.patched.Message, Message], fallback: T=None) -> Union[T, int]:
    return get_forward_id(msg) if isinstance(msg, Message) else get_forward_id_a(msg)

def get_msg_from(msg: Message) -> int:
    return msg.from_user.id if msg.from_user else msg.chat.id

def get_chat_id(msg: Union[telethon.events.Album.Event, Message]) -> int:
    return msg.chat.id if isinstance(msg, Message) else get_peer_user_id(msg.original_update.message.to_id)

def get_peer_user_id(peer_id: Union[telethon.tl.types.PeerChannel, telethon.tl.types.PeerChat]):
    if isinstance(peer_id, telethon.tl.types.PeerChannel):
        return -peer_id.channel_id - 1000000000000
    else:
        return peer_id.user_id

def get_msg_from_a(msg: telethon.tl.patched.Message) -> int:
    return msg.from_id if msg.from_id is not None else get_peer_user_id(msg.to_id)

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


class BlackListForwardRequest(BasicForwardRequest): pass


class ForwardRequest(BasicForwardRequest):

    def __init__(self, target_id: int, msg: Message, log: LogStruct = LogStruct(False, '')):
        super().__init__(msg, log)
        self.target_id = target_id

    @classmethod
    def from_super(cls, target_id: int, request: BlackListForwardRequest) -> 'ForwardRequest':
        return cls(target_id, request.msg, request.log)


class AlbumForwardRequest(BasicForwardRequest):
    def __init__(self, app: telethon.TelegramClient, target_id: int, msg: telethon.events.Album.Event, log: LogStruct=LogStruct(False, '')) -> None:
        super().__init__(None, log)
        self.app = app
        self.target_id = target_id
        self.msgs: List[telethon.tl.patched.Message] = msg

    async def forward(self) -> List[telethon.tl.patched.Message]:
        return await self.app.forward_messages(await self.app.get_peer_id(self.target_id), self.msgs)


class Plugin(metaclass=ABCMeta):

    @classmethod
    @abstractmethod
    async def create_plugin(cls, *_args) -> 'Plugin':
        return NotImplemented

    @abstractmethod
    async def plugin_start(self) -> None:
        return NotImplemented

    async def plugin_pending_start(self) -> None:
        pass

    async def plugin_pending_stop(self) -> None:
        pass

    @abstractmethod
    async def plugin_stop(self) -> None:
        return NotImplemented


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
        _requirement = _Requirement(self.requirement.get('config'), self.requirement.get('database')) # type: ignore
        if _requirement.config:
            self.args.append(config)
        if _requirement.database:
            self.args.append(database)
        self.module: T = module
        self.module_name: str = module_name
        self.instance: Plugin = None # type: ignore

    async def __call__(self) -> Plugin:
        await self.create_instace()
        return self.instance

    async def create_instace(self) -> 'PluginLoader':
        self.instance = await getattr(self.module, self.module_name).create_plugin(*self.args)
        return self


@dataclass
class TracebackableCallable:
    callback: Callable[[], Awaitable[T]]

    async def __call__(self) -> None:
        try:
            await self.callback()
        except GeneratorExit:
            raise
        except:
            traceback.print_exc()


class AlbumStructure:
    pmsg: List[Message]
    thonmsg: telethon.events.Album.Event
    check_status: Optional[bool] = None
    ready_list: List[telethon.tl.patched.Message] = []
    lower: bool = False

    class NotReadyError(Exception): pass

    def __init__(self, msg: Union[telethon.events.Album.Event, Message]) -> None:
        self.conn = checkfile.get_instance()
        if isinstance(msg, Message):
            self.pmsg = [msg]
            self.thonmsg = None
        else:
            self.pmsg = []
            self.thonmsg = msg
            logger.debug('length => %d', len(msg.messages))

    def update(self, msg: Union[telethon.events.Album.Event, Message]):
        if isinstance(msg, Message):
            self.pmsg.append(msg)
        else:
            self.thonmsg = msg
    
    def _do_sort(self):
        self.pmsg.sort(key=lambda x: x.message_id)
    
    @property
    def event(self) -> Optional[telethon.events.Album.Event]:
        return self.thonmsg
    
    @property
    def timestamp(self) -> int:
        if len(self.pmsg):
            return self.pmsg[0].date
        else:
            return int(datetime.datetime.timestamp(self.thonmsg.original_update.message.date))

    @property
    def done(self) -> bool:
        obj = self.thonmsg is not None and len(self.pmsg) == len(self.thonmsg.messages)
        logger.debug('obj => %s', obj)
        return obj
    
    async def check(self) -> bool:
        if self.check_status is not None:
            return self.check_status
        if not self.done:
            raise self.NotReadyError()
        self._do_sort()
        result = await asyncio.gather(self.conn.checkFile(self.pmsg[i].photo.file_id) for i in range(len(self.pmsg)))
        for i in range(len(result)):
            self.ready_list.append(self.thonmsg.messages[i])
        self.check_status = bool(len(self.ready_list))
        self.lower = sum(map(int, (self.conn.check_photo(x) for x in self.pmsg))) > (len(self.pmsg) // 2)
        del self.pmsg, self.thonmsg
        return self.check_status

class MediaGroupObjectStore:
    _instance: 'MediaGroupObjectStore'
    def __init__(self) -> None:
        self.store: Dict[int, AlbumStructure] = {}
        #self.clean_job_futures: Dict[int, TimerHandle] = {}
        self.lock = asyncio.Lock()
        #self.conn = conn
        #self.iter_lock = asyncio.Lock()
    
    def _update(self, media_id: int, obj: AlbumStructure) -> None:
        #self.clean_job_futures.update({media_id:asyncio.get_event_loop().call_later(120, self.delete, media_id)})
        self.store.update({media_id: obj})

    async def delete(self, media_id: int) -> None:
        async with self.lock:
            self.store.pop(media_id)
            logger.warning('Pop unused group %d', media_id)

    async def update_item(self, media_id: int, obj: Union[telethon.events.Album.Event, Message]) -> bool:
        async with self.lock:
            logger.debug('dict length => %d', self.__len__())
            if media_id not in self.store:
                self._update(media_id, AlbumStructure(obj))
                logger.debug('Insert media group: %d', media_id)
                return False
            else:
                self.store[media_id].update(obj)
                logger.debug('Update media group: %d', media_id)
                return self.store[media_id].done

    async def pop(self, media_id: int) -> AlbumStructure:
        async with self.lock:
        #self.clean_job_futures.pop(media_id).cancel()
            return self.store.pop(media_id)

    @classmethod
    def create_instance(cls) -> 'MediaGroupObjectStore':
        cls._instance = cls()
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'MediaGroupObjectStore':
        return cls._instance
    
    def enum(self) -> Generator[Tuple[int, AlbumStructure], None, None]:
        for key, item in self.store.items():
            yield key, item
        
    def __len__(self) -> int:
        return len(self.store)