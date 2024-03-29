#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# forward.py
# Copyright (C) 2018-2023 KunoiSayami
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
import concurrent.futures
import importlib
import logging
import os
import re
import signal
from configparser import ConfigParser
from dataclasses import dataclass
from typing import Callable, Coroutine

import asyncpg
import redis.exceptions
import pyrogram.errors
from pyrogram import Client, filters, raw, ContinuePropagation
from pyrogram.enums import ParseMode, ChatAction
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from configure import Configure
from helper import CheckFile, ClientRedisHelper
from utils import (
    BlackListForwardRequest,
    ForwardRequest,
    LogStruct,
    PluginLoader,
    get_forward_id,
    get_msg_from,
    is_bot,
)

logger = logging.getLogger("forward_main")
logger.setLevel(logging.DEBUG)


class ForwardThread:
    @dataclass
    class _IDObject:
        id: int

    class _BuildInMessage:
        def __init__(
            self,
            chat_id: int,
            msg_id: int,
            from_user_id: int = -1,
            forward_from_id: int = -1,
        ):
            self.chat: ForwardThread._IDObject = ForwardThread._IDObject(chat_id)
            self.message_id: int = msg_id
            self.from_user: ForwardThread._IDObject = ForwardThread._IDObject(
                from_user_id
            )
            self.forward_from: ForwardThread._IDObject = ForwardThread._IDObject(
                forward_from_id
            )

    queue: asyncio.Queue = asyncio.Queue()
    switch: bool = True
    """
        Queue tuple structure:
        (target_id: int, chat_id: int, msg_id: int|tuple, Log_info: tuple)
        `target_id` : Forward to where
        `chat_id` : Forward from
        `msg_id` : Forward from message id
        `Loginfo` structure: (need_log: bool, log_msg: str, args: tuple)
    """

    def __init__(self, redis_conn: ClientRedisHelper):
        self.checker: CheckFile = CheckFile.get_instance()
        self.configure: Configure = Configure.get_instance()
        self.logger: logging.Logger = logging.getLogger("fwd_thread")
        log_file_header: logging.FileHandler = logging.FileHandler("log.log")
        log_file_header.setFormatter(
            logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")
        )
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(log_file_header)
        self.logger.propagate = False
        self.redis = redis_conn

    @classmethod
    def put(cls, request: ForwardRequest) -> None:
        cls.queue.put_nowait(request)

    @classmethod
    async def get(cls) -> ForwardRequest:
        return await cls.queue.get()

    @classmethod
    def get_status(cls) -> bool:
        return cls.switch

    def start(self) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(self._run(), asyncio.get_event_loop())

    async def _run(self) -> None:
        while self.get_status():
            task = asyncio.create_task(self.get())
            while True:
                result, _pending = await asyncio.wait([task], timeout=1)
                if len(result):
                    request = result.pop().result()
                    break
                if not self.get_status():
                    task.cancel()
                    return
            try:
                r = await request.msg.forward(request.target_id, True)
                await self.checker.insert_log(
                    r.chat.id,
                    r.id,
                    request.msg.chat.id,
                    request.msg.id,
                    get_msg_from(request.msg),
                    get_forward_id(request.msg, -1),
                )
                if request.log.need_log:
                    self.logger.info(request.log.fmt_log, *request.log.fmt_args)
            except pyrogram.errors.exceptions.bad_request_400.MessageIdInvalid:
                pass
            except pyrogram.errors.RPCError:
                if request.msg:
                    print(repr(request.msg))
                # self.put(target_id, chat_id, msg_id, request.log, msg_raw)
                logger.exception("Got other exceptions in forward thread")
            await asyncio.sleep(0.5)


class SetTypingCoroutine:
    def __init__(self, client: Client, chat_id: int):
        self.switch: bool = True
        self.client: Client = client
        self.chat_id: int = chat_id
        self.future: concurrent.futures.Future = self.start()

    def set_off(self) -> None:
        self.switch = False

    def start(self) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(self._run(), asyncio.get_event_loop())

    async def _run(self) -> None:
        while self.switch:
            await self.client.send_chat_action(self.chat_id, ChatAction.TYPING)
            # After 5 seconds, chat action will cancel automatically
            await asyncio.sleep(4.5)
        await self.client.send_chat_action(self.chat_id, ChatAction.CANCEL)


class GetHistoryCoroutine:
    def __init__(
        self,
        client: Client,
        chat_id: int,
        target_id: int | str,
        offset_id: int = 0,
        dirty_run: bool = False,
    ):
        self.checker: CheckFile = CheckFile.get_instance()
        self.configure: Configure = Configure.get_instance()
        self.client: Client = client
        self.target_id: int = int(target_id)
        self.offset_id: int = offset_id
        self.chat_id: int = chat_id
        self.dirty_run: bool = dirty_run
        self.start()

    def start(self) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(self.run(), asyncio.get_event_loop())

    async def run(self) -> None:
        check_func = (
            self.checker.check_file
            if not self.dirty_run
            else self.checker.check_file_dirty
        )
        photos, videos, docs = [], [], []
        msg_group = [
            msg
            async for msg in self.client.get_chat_history(
                self.target_id, offset_id=self.offset_id, limit=1
            )
        ]
        await self.client.send_message(
            self.chat_id,
            "Now process query {}, total {} messages{}".format(
                self.target_id,
                msg_group[0]["message_id"],
                " (Dirty mode)" if self.dirty_run else "",
            ),
        )
        status_thread = SetTypingCoroutine(self.client, self.chat_id)
        self.offset_id = msg_group[0]["message_id"]
        while self.offset_id > 1:
            for x in list(msg_group):
                if x.photo:
                    if not await check_func(x.photo.file_unique_id):
                        continue
                    photos.append(
                        (
                            is_bot(x),
                            {
                                "chat": {"id": self.target_id},
                                "message_id": x["message_id"],
                            },
                        )
                    )
                elif x.video:
                    if not await check_func(x.video.file_unique_id):
                        continue
                    videos.append(
                        (
                            is_bot(x),
                            {
                                "chat": {"id": self.target_id},
                                "message_id": x["message_id"],
                            },
                        )
                    )
                elif x.document:
                    if (
                        "/" in x.document.mime_type
                        and x.document.mime_type.split("/")[0] in ("image", "video")
                        and not await check_func(x.document.file_unique_id)
                    ):
                        continue
                    docs.append(
                        (
                            is_bot(x),
                            {
                                "chat": {"id": self.target_id},
                                "message_id": x["message_id"],
                            },
                        )
                    )
            try:
                self.offset_id = msg_group[-1]["message_id"] - 1
            except IndexError:
                logger.info("Query channel end by message_id %d", self.offset_id + 1)
                break
            try:
                msg_group = [
                    msg
                    async for msg in self.client.get_chat_history(
                        self.target_id, offset_id=self.offset_id, limit=100
                    )
                ]
            except pyrogram.errors.FloodWait as e:
                logger.warning("Got flood wait, sleep %d seconds", e.value)
                await asyncio.sleep(e.value)
        if not self.dirty_run:
            await self.client.send_message(
                self.configure.query_photo, f"Begin {self.target_id} forward"
            )
            await self.client.send_message(
                self.configure.query_video, f"Begin {self.target_id} forward"
            )
            await self.client.send_message(
                self.configure.query_doc, f"Begin {self.target_id} forward"
            )
            for x in reversed(photos):
                ForwardThread.put(
                    ForwardRequest(
                        self.configure.query_photo
                        if not x[0]
                        else self.configure.bot_for,
                        x[1],
                    )
                )
            for x in reversed(videos):
                ForwardThread.put(
                    ForwardRequest(
                        self.configure.query_video
                        if not x[0]
                        else self.configure.bot_for,
                        x[1],
                    )
                )
            for x in reversed(docs):
                ForwardThread.put(
                    ForwardRequest(
                        self.configure.query_doc
                        if not x[0]
                        else self.configure.bot_for,
                        x[1],
                    )
                )
        status_thread.set_off()
        await self.client.send_message(
            self.chat_id,
            "Query completed {} photos,"
            " {} videos, {} docs{}".format(
                len(photos),
                len(videos),
                len(docs),
                " (Dirty mode)" if self.dirty_run else "",
            ),
        )
        logger.info(
            "Query %d completed%s, total %d photos, %d videos, %d documents.",
            self.target_id,
            " (Dirty run)" if self.dirty_run else "",
            len(photos),
            len(videos),
            len(docs),
        )
        del photos, videos, docs


class UnsupportedType(Exception):
    pass


class BotController:
    def __init__(
        self,
        config: ConfigParser,
        redis_: ClientRedisHelper,
        checker: CheckFile,
        forward_thread: ForwardThread,
    ):
        self.configure = Configure.init_instance(config)
        self.app = Client(
            "forward",
            config.get("account", "api_id"),
            config.get("account", "api_hash"),
        )
        self.checker: CheckFile = checker

        self.redis = redis_

        self.ForwardThread: ForwardThread = forward_thread

        self.min_resolution: int = config.getint(
            "forward", "lowq_resolution", fallback=120
        )
        self.owner_group_id: int = config.getint("account", "group_id", fallback=-1)

        self.echo_switch: bool = False
        self.detail_msg_switch: bool = False
        # self.delete_blocked_message_after_blacklist: bool = False
        self.func_blacklist: Callable[[BlackListForwardRequest], int] | None = None
        self.custom_switch: bool = False

        self.init_handle()

        self.future: concurrent.futures.Future | None = None

        self.plugins: list[PluginLoader] = []

    @classmethod
    async def create(cls, config: ConfigParser):
        checker = await CheckFile.init_instance(
            config.get("pgsql", "host"),
            config.getint("pgsql", "port"),
            config.get("pgsql", "username"),
            config.get("pgsql", "passwd"),
            config.get("pgsql", "database"),
        )
        redis_ = await ClientRedisHelper.new(checker, config.getint("account", "owner"))
        forward_thread = ForwardThread(redis_)
        self = cls(config, redis_, checker, forward_thread)
        await self.load_plugins(config)
        return self

    async def clean(self) -> None:
        await self.redis.clean(await self.checker.query_all_special_forward())

    def init_handle(self) -> None:
        self.app.add_handler(
            MessageHandler(
                self.get_msg_from_owner_group,
                filters.chat(self.owner_group_id) & filters.reply,
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.get_command_from_target,
                filters.chat(self.configure.predefined_group_list)
                & filters.text
                & filters.reply,
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.pre_check,
                filters.media
                & ~filters.private
                & ~filters.sticker
                & ~filters.voice
                & ~filters.web_page,
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.handle_photo,
                filters.photo
                & ~filters.private
                & ~filters.chat([self.configure.photo, self.configure.lowq]),
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.handle_video,
                filters.video & ~filters.private & ~filters.chat(self.configure.video),
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.handle_gif,
                filters.animation
                & ~filters.private
                & ~filters.chat(self.configure.gif),
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.handle_document,
                filters.document & ~filters.private & ~filters.chat(self.configure.doc),
            )
        )
        self.app.add_handler(MessageHandler(self.do_nothing, filters.contact))
        self.app.add_handler(
            MessageHandler(
                self.handle_other,
                filters.media
                & ~filters.private
                & ~filters.sticker
                & ~filters.voice
                & ~filters.web_page,
            )
        )
        self.app.add_handler(MessageHandler(self.pre_private, filters.private))
        self.app.add_handler(
            MessageHandler(
                self.handle_add_bypass, filters.command("e") & filters.private
            )
        )
        self.app.add_handler(
            MessageHandler(self.process_query, filters.command("q") & filters.private)
        )
        self.app.add_handler(
            MessageHandler(
                self.handle_add_black_list, filters.command("b") & filters.private
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.process_show_detail, filters.command("s") & filters.private
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.set_forward_target_reply,
                filters.command("f") & filters.reply & filters.private,
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.set_forward_target, filters.command("f") & filters.private
            )
        )
        self.app.add_handler(
            MessageHandler(self.add_user, filters.command("a") & filters.private)
        )
        self.app.add_handler(
            MessageHandler(self.change_code, filters.command("pw") & filters.private)
        )
        self.app.add_handler(
            MessageHandler(
                self.undo_blacklist_operation, filters.command("undo") & filters.private
            )
        )
        self.app.add_handler(
            MessageHandler(
                self.switch_detail2, filters.command("sd2") & filters.private
            )
        )
        self.app.add_handler(
            MessageHandler(self.switch_detail, filters.command("sd") & filters.private)
        )
        self.app.add_handler(
            MessageHandler(
                self.show_help_message, filters.command("help") & filters.private
            )
        )
        self.app.add_handler(MessageHandler(self.process_private, filters.private))

    async def do_nothing(self, _client: Client, _msg: Message) -> None:
        pass

    async def load_plugins(self, config: ConfigParser) -> None:
        try:
            for root, _dirs, filenames in os.walk("."):
                if root != ".":
                    continue
                for filename in filenames:
                    if not (filename.startswith("Plugin") and filename.endswith(".py")):
                        continue
                    module_name = filename.split(".py")[0]
                    try:
                        mod = importlib.import_module(module_name)
                        loader = await PluginLoader(
                            mod, module_name, self.app, config, CheckFile
                        ).create_instance()  # type: ignore
                        await loader.instance.plugin_pending_start()  # type: ignore
                        self.plugins.append(loader)  # type: ignore
                    except:
                        logger.exception(
                            "Loading plugin: %s catch exception!", module_name
                        )
                    else:
                        logger.info("Load plugin: %s successfully", module_name)
        except FileNotFoundError:
            pass

    async def start_plugins(self) -> None:
        for x in self.plugins:
            try:
                await x.instance.plugin_start()
            except:
                logger.error("Start %s plugin fail", x.module_name)

    async def stop_plugins(self) -> None:
        for x in self.plugins:
            try:
                await x.instance.plugin_stop()
            except:
                logger.error("Stop %s plugin fail", x.module_name)

    async def pending_stop_plugins(self) -> None:
        for x in self.plugins:
            try:
                await x.instance.plugin_pending_stop()
            except:
                logger.error("Pending stop %s plugin fail", x.module_name)

    async def reply_checker_and_del_from_blacklist(
        self, client: Client, msg: Message
    ) -> None:
        try:
            pending_del = None
            if msg.reply_to_message.text:
                r = re.match(r"^Add (-?\d+) to blacklist$", msg.reply_to_message.text)
                if r and msg.reply_to_message.from_user.id != msg.chat.id:
                    pending_del = int(r.group(1))
            else:
                group_id = (
                    msg.forward_from.id
                    if msg.forward_from
                    else msg.forward_from_chat.id
                    if msg.forward_from_chat
                    else None
                )
                if group_id and await self.redis.query_blacklist(group_id):
                    pending_del = group_id
            if pending_del is not None:
                if await self.redis.delete_blacklist(pending_del):
                    await self.checker.remove_blacklist(pending_del)
                await client.send_message(
                    self.owner_group_id,
                    f"Remove `{pending_del}` from blacklist",
                    parse_mode=ParseMode.MARKDOWN,
                )
        except (
            pyrogram.errors.RPCError,
            asyncpg.PostgresError,
            redis.exceptions.RedisError,
        ):
            if msg.reply_to_message.text:
                print(msg.reply_to_message.text)
            logger.exception("Catch!")

    async def add_black_list(self, user_id: int | dict | list[int], post_back_id=None) -> None:
        if isinstance(user_id, dict):
            await self.app.send_message(
                self.owner_group_id,
                f'User id:`{user_id["from_user"]}`\nFrom '
                f'chat id:`{user_id["from_chat"]}`\nForward '
                f'from id:`{user_id["from_forward"]}`',
                ParseMode.MARKDOWN,
            )
            user_id = user_id["from_user"]
        # Check is msg from authorized user
        if user_id is None or await self.redis.query_admin(user_id):
            raise KeyError
        if await self.redis.add_blacklist(user_id):
            await self.checker.insert_blacklist(user_id)  # type: ignore
        logger.info("Add %d to blacklist", user_id)
        if post_back_id is not None:
            await self.app.send_message(
                post_back_id, f"Add `{user_id}` to blacklist", ParseMode.MARKDOWN
            )

    async def del_message_by_id(
        self, client: Client, msg: Message, send_message_to: int | str | None = None
    ) -> None:
        id_from_reply = get_forward_id(msg.reply_to_message)
        q = await self.checker.query(
            """SELECT "to_chat", "to_msg" FROM "msg_detail"
         WHERE ("from_chat" = $1 OR "from_user" = $2 OR "forward_from" = $3)""",
            id_from_reply,
            id_from_reply,
            id_from_reply,
        )

        if send_message_to:
            _msg = await client.send_message(
                send_message_to, f"Find {len(q)} message(s)"
            )

            for x in q:
                try:
                    await client.delete_messages(x["to_chat"], x["to_msg"])
                except pyrogram.errors.RPCError:
                    pass
            await self.checker.execute(
                """DELETE FROM "msg_detail" 
                 WHERE ("from_chat" = $1 OR "from_user" = $2 OR "forward_from" = $3)""",
                id_from_reply,
                id_from_reply,
                id_from_reply,
            )
            await _msg.edit(
                f"Delete all message from `{id_from_reply}` completed.",
                ParseMode.MARKDOWN,
            )
        else:
            for x in q:
                try:
                    await client.delete_messages(x["to_chat"], x["to_msg"])
                except pyrogram.errors.RPCError:
                    pass
            await msg.reply(
                f"Delete all message from `{id_from_reply}` completed.",
                False,
                ParseMode.MARKDOWN,
            )

    async def get_msg_from_owner_group(self, client: Client, msg: Message) -> None:
        try:
            if msg.text and msg.text == "/undo":
                await self.reply_checker_and_del_from_blacklist(client, msg)
        except pyrogram.errors.RPCError:
            logger.exception("Exception occurred on `get_msg_from_owner_group()'")

    async def get_command_from_target(self, client: Client, msg: Message) -> None:
        if re.match(r"^/(del(f)?|b|undo|print)$", msg.text):
            if msg.text == "/b":
                for_id = await self.checker.query_forward_from(
                    msg.chat.id, msg.reply_to_message.id
                )
                await self.add_black_list(
                    [
                        for_id.from_chat,
                        for_id.from_user,  # type: ignore
                        for_id.forward_from,
                        self.owner_group_id,
                    ]
                )
                # To enable delete message, please add `delete other messages' privilege to bot
                call_delete_msg(
                    30,
                    client.delete_messages,
                    msg.chat.id,
                    (msg.id, msg.reply_to_message.id),
                )
            elif msg.text == "/undo":
                group_id = msg.reply_to_message.id if msg.reply_to_message else None
                if group_id:
                    try:
                        if await self.redis.delete_admin(group_id):
                            await self.checker.remove_admin(group_id)
                        await client.send_message(
                            self.owner_group_id,
                            f"Remove `{group_id}` from blacklist",
                            ParseMode.MARKDOWN,
                        )
                    except ValueError:
                        await client.send_message(
                            self.owner_group_id,
                            f"`{group_id}` not in blacklist",
                            ParseMode.MARKDOWN,
                        )
            elif msg.text == "/print" and msg.reply_to_message is not None:
                print(msg.reply_to_message)
            else:
                call_delete_msg(20, client.delete_messages, msg.chat.id, msg.id)
                if get_forward_id(msg.reply_to_message):
                    await self.del_message_by_id(client, msg, self.owner_group_id)

    @staticmethod
    def get_file_unique_id(msg: Message, _type: str) -> str:
        if _type == "contact":
            return msg.contact.phone_number
        return getattr(msg, _type).file_unique_id

    @staticmethod
    def get_file_type(msg: Message) -> str:
        s = BotController._get_file_type(msg)
        if s == "error":
            raise UnsupportedType()
        return s

    @staticmethod
    def _get_file_type(msg: Message) -> str:
        return (
            "photo"
            if msg.photo
            else "video"
            if msg.video
            else "animation"
            if msg.animation
            else "sticker"
            if msg.sticker
            else "voice"
            if msg.voice
            else "document"
            if msg.document
            else "audio"
            if msg.audio
            else "contact"
            if msg.contact
            else "error"
        )

    async def pre_check(self, _client: Client, msg: Message) -> None:
        try:
            if await self.redis.query_bypass(
                msg.chat.id
            ) or not await self.checker.check_file(
                self.get_file_unique_id(msg, self.get_file_type(msg))
            ):
                return
        except UnsupportedType:
            pass
        else:
            raise ContinuePropagation

    async def forward_msg(self, msg: Message, to: int, what: str = "photo") -> None:
        if msg.has_protected_content:
            return
        if await self.redis.check_msg_from_blacklist(msg):
            return
        forward_target = to
        # spec_target = None if what == 'other' else await self.redis.get(f'{self.redis_prefix}{msg.chat.id}')
        spec_target = (
            None if what == "other" else await self.redis.get(str(msg.chat.id))
        )
        if spec_target is None:
            # spec_target = await self.redis.get(f'{self.redis_prefix}{msg.forward_from_chat.id}')
            if msg.forward_from_chat:
                spec_target = await self.redis.get(str(msg.forward_from_chat.id))
        if spec_target is not None:
            forward_target = getattr(self.configure, spec_target.decode())
        elif is_bot(msg):
            forward_target = self.configure.bot
        self.ForwardThread.put(
            ForwardRequest(
                forward_target,
                msg,
                LogStruct(
                    True,
                    "forward %s from %s (id: %d)",
                    what,
                    msg.chat.title,
                    msg.chat.id,
                ),
            )
        )

    async def handle_photo(self, _client: Client, msg: Message) -> None:
        await self.forward_msg(
            msg,
            self.configure.photo
            if self.checker.check_photo(msg.photo)
            else self.configure.lowq,
        )

    async def handle_video(self, _client: Client, msg: Message) -> None:
        await self.forward_msg(msg, self.configure.video, "video")

    async def handle_gif(self, _client: Client, msg: Message) -> None:
        await self.forward_msg(msg, self.configure.gif, "gif")

    async def handle_document(self, _client: Client, msg: Message):
        if msg.document.file_name.split(".")[-1] in ("com", "exe", "bat", "cmd"):
            return
        forward_target = (
            self.configure.doc
            if "/" in msg.document.mime_type
            and msg.document.mime_type.split("/")[0] in ("image", "video")
            else self.configure.other
        )
        await self.forward_msg(
            msg,
            forward_target,
            "doc" if forward_target != self.configure.other else "other",
        )

    async def handle_other(self, _client: Client, msg: Message) -> None:
        await self.forward_msg(msg, self.configure.other, "other")

    async def pre_private(self, client: Client, msg: Message) -> None:
        if not await self.redis.check_msg_from_admin(msg):
            await client.invoke(
                raw.functions.messages.ReportSpam(
                    peer=await client.resolve_peer(msg.chat.id)
                )
            )
            return
        await client.invoke(
            raw.functions.messages.ReadHistory(
                peer=await client.resolve_peer(msg.chat.id), max_id=msg.id
            )
        )
        raise ContinuePropagation

    async def handle_add_bypass(self, _client: Client, msg: Message) -> None:
        if len(msg.text) < 4:
            return
        except_id = msg.text[3:]
        if await self.redis.add_bypass(except_id):
            await self.checker.insert_bypass(except_id)
        await msg.reply(
            f"Add `{except_id}` to bypass list", parse_mode=ParseMode.MARKDOWN
        )
        logger.info("add except id: %s", except_id)

    @staticmethod
    async def process_query(client: Client, msg: Message) -> None:
        r = re.match(r"^/q (-?\d+)(d)?$", msg.text)
        if r is None:
            return
        GetHistoryCoroutine(
            client, msg.chat.id, r.group(1), dirty_run=r.group(2) is not None
        )

    async def handle_add_black_list(self, _client: Client, msg: Message) -> None:
        try:
            await self.add_black_list(msg.text[3:])
        except (ValueError, IndexError):
            await msg.reply("Check your input")
            logger.exception("Catch!")

    async def process_show_detail(self, _client: Client, msg: Message) -> None:
        self.echo_switch = not self.echo_switch
        await msg.reply(f"Set echo to {self.echo_switch}")

    async def set_forward_target_reply(self, _client: Client, msg: Message) -> None:
        if msg.reply_to_message.text is None:
            await msg.reply("Reply to None text messages")
            return
        r = re.match(r"^forward_from = (-\d+)$", msg.reply_to_message.text)
        r1 = re.match(r"^/f (other|photo|bot|video|anime|gif|doc|lowq)$", msg.text)
        if r is None or r1 is None:
            await msg.reply("Cannot found special target forward for")
            return
        await self._set_forward_target(int(r.group(1)), r1.group(1), msg)

    async def set_forward_target(self, _client: Client, msg: Message) -> None:
        r = re.match(
            r"^/f (-?\d+) (other|photo|bot|video|anime|gif|doc|lowq)$", msg.text
        )
        if r is None:
            return
        await self._set_forward_target(int(r.group(1)), r.group(2), msg)

    async def _set_forward_target(
        self, chat_id: int, target: str, msg: Message
    ) -> None:
        await self.redis.set(str(chat_id), target)
        await self.checker.update_forward_target(chat_id, target)
        await msg.reply(
            f"Set group `{chat_id}` forward to `{target}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def add_user(self, _client: Client, msg: Message) -> None:
        r = re.match(r"^/a (.+)$", msg.text)
        if r and r.group(1) == self.configure.authorized_code:
            if await self.redis.add_admin(msg.chat.id):
                await self.checker.insert_admin(msg.chat.id)
            await msg.reply("Success add to authorized users.")

    @staticmethod
    async def change_code(_client: Client, msg: Message) -> None:
        r = re.match(r"^/pw (.+)$", msg.text)
        if r:
            await msg.reply("Success changed authorize code.")

    async def undo_blacklist_operation(self, client: Client, msg: Message) -> None:
        await self.reply_checker_and_del_from_blacklist(client, msg)

    async def switch_detail2(self, _client: Client, msg: Message) -> None:
        self.custom_switch = not self.custom_switch
        await msg.reply(f"Switch custom print to {self.custom_switch}")

    async def switch_detail(self, _client: Client, msg: Message) -> None:
        self.detail_msg_switch = not self.detail_msg_switch
        await msg.reply(f"Switch detail print to {self.detail_msg_switch}")

    @staticmethod
    async def show_help_message(_client: Client, msg: Message) -> None:
        await msg.reply(
            """ Usage:
        /e <chat_id>            Add `chat_id' to bypass list
        /a <password>           Use the `password' to obtain authorization
        /q <chat_id>            Request to query one specific `chat_id'
        /b <chat_id>            Add `chat_id' to blacklist
        /s                      Toggle echo switch
        /f <chat_id> <target>   Add `chat_id' to specified forward rules
        /pw <new_password>      Change password to new password
        """,
            parse_mode=ParseMode.DISABLED,
        )

    async def process_private(self, _client: Client, msg: Message) -> None:
        if self.custom_switch:
            obj = getattr(msg, self.get_file_type(msg), None)
            if obj:
                await msg.reply(
                    "```{}```\n{}".format(
                        str(obj),
                        "Resolution: `{}`".format(
                            msg.photo.file_size
                            / (msg.photo.width * msg.photo.height)
                            * 1000
                        )
                        if msg.photo
                        else "",
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
        if self.echo_switch:
            await msg.reply(
                "forward_from = `{}`".format(get_forward_id(msg, -1)),
                parse_mode=ParseMode.MARKDOWN,
            )
            if self.detail_msg_switch:
                print(msg)
        if msg.text is None:
            return
        r = re.match(r"^Add (-?\d+) to blacklist$", msg.text)
        if r is None:
            return
        await self.add_black_list(int(r.group(1)), msg.chat.id)

    async def start(self) -> None:
        await self.app.start()
        self.future = self.ForwardThread.start()
        await self.start_plugins()

    async def idle(self) -> None:
        _idle = asyncio.Event()

        def _reset_idle(*_args):
            _idle.set()

        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(sig, _reset_idle)

        while not _idle.is_set():
            try:
                if (e := self.future.exception(0)) is not None:
                    raise e
            except (pyrogram.errors.RPCError, asyncpg.PostgresError):
                logger.exception("Got Telegram or database exception, raising")
                raise
            except (concurrent.futures.CancelledError, concurrent.futures.TimeoutError):
                pass
            if _idle.is_set():
                break
            await asyncio.sleep(1)

    async def stop(self) -> None:
        logger.info("Calling clean up function")
        ForwardThread.switch = False
        await asyncio.sleep(1)
        await self.pending_stop_plugins()
        try:
            if self.future.running():
                logger.warning(
                    "Future is still running, Wait more time until it finished"
                )
                for _ in range(3):
                    if self.future.running():
                        await asyncio.sleep(1.5)
                    else:
                        break
                if self.future.running():
                    logger.error(
                        "Future in still running after period of time, cancel it."
                    )
                    self.future.cancel()
                try:
                    self.future.result(0)
                except (
                    concurrent.futures.CancelledError,
                    concurrent.futures.TimeoutError,
                ):
                    pass
        finally:
            await self.app.stop()
            await self.stop_plugins()
            await self.clean()
            await asyncio.gather(self.checker.close(), self.redis.close())


def call_delete_msg(
    interval: int,
    func: Callable[[int, int | tuple[int, ...]], Coroutine[None, None, bool]],
    target_id: int,
    msg_: int | tuple[int, ...],
) -> None:
    asyncio.get_event_loop().call_later(interval, func, target_id, msg_)


async def main() -> None:
    config = ConfigParser()
    config.read("config.ini")
    bot = await BotController.create(config)
    await bot.start()
    try:
        await bot.idle()
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        import coloredlogs

        coloredlogs.install(
            logging.DEBUG,
            fmt="%(asctime)s,%(msecs)03d - %(levelname)s - %(name)s - "
            "%(funcName)s - %(lineno)d - %(message)s",
        )
    except ModuleNotFoundError:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - "
            "%(name)s - %(funcName)s - %(lineno)d - %(message)s",
        )
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    asyncio.run(main())
