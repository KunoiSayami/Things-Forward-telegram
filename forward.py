# -*- coding: utf-8 -*-
# forward.py
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
import importlib
import logging
import os
import random
import re
import string
import time
from configparser import ConfigParser
from dataclasses import dataclass
from queue import Queue
from threading import Thread, Timer
from typing import Callable, Dict, List, NoReturn, Optional, Tuple, Union

import pyrogram.errors
import redis
from pymysql.err import ProgrammingError
from pyrogram import (Client, ContinuePropagation, Filters, Message,
                      MessageHandler, api)

from configure import configure
from fileid_checker import checkfile
from utils import (BlackListForwardRequest, ForwardRequest, LogStruct,
                   PluginLoader, get_forward_id, get_msg_from, is_bot)

logger = logging.getLogger('forward_main')
logger.setLevel(logging.DEBUG)


class ForwardThread(Thread):

	@dataclass
	class _IDObject:
		id: int

	class _BuildInMessage:
		def __init__(self, chat_id: int, msg_id: int, from_user_id: int=-1, forward_from_id: int=-1):
			self.chat: int = ForwardThread._IDObject(chat_id)
			self.message_id: int = msg_id
			self.from_user: int = ForwardThread._IDObject(from_user_id)
			self.forward_from: int = ForwardThread._IDObject(forward_from_id)

	queue = Queue()
	switch = True
	'''
		Queue tuple structure:
		(target_id: int, chat_id: int, msg_id: int|tuple, Log_info: tuple)
		`target_id` : Forward to where
		`chat_id` : Forward from
		`msg_id` : Forward from message id
		`Loginfo` structure: (need_log: bool, log_msg: str, args: tulpe)
	'''
	def __init__(self):
		super().__init__(daemon=True)
		self.checker: checkfile = checkfile.get_instance()
		self.configure: configure = configure.get_instance()
		self.logger: logging.Logger = logging.getLogger('fwd_thread')
		log_file_header: logging.FileHandler = logging.FileHandler('log.log')
		log_file_header.setFormatter(logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s'))
		self.logger.setLevel(logging.INFO)
		self.logger.addHandler(log_file_header)
		self.logger.propagate = False

	@staticmethod
	def put_blacklist(request: BlackListForwardRequest) -> NoReturn:
		ForwardThread.put(ForwardRequest.from_super(configure.get_instance().blacklist, request))

	@staticmethod
	def put(request: ForwardRequest) -> NoReturn:
		ForwardThread.queue.put_nowait(request)

	@staticmethod
	def get() -> ForwardRequest:
		return ForwardThread.queue.get()

	@staticmethod
	def get_status() -> bool:
		return ForwardThread.switch

	def run(self) -> NoReturn:
		while self.get_status():
			request = self.get()
			try:
				r = request.msg.forward(request.target_id, True)
				self.checker.insert_log(r.chat.id, r.message_id, request.msg.chat.id,
					request.msg.message_id, get_msg_from(request.msg), get_forward_id(request.msg, -1))
				if request.log.need_log:
					self.logger.info(request.log.fmt_log, *request.log.fmt_args)
			except ProgrammingError:
				logger.exception("Got programming error in forward thread")
			except pyrogram.errors.exceptions.bad_request_400.MessageIdInvalid:
				pass
			except:
				if request.msg and request.target_id != self.configure.blacklist:
					print(repr(request.msg))
				#self.put(target_id, chat_id, msg_id, request.log, msg_raw)
				logger.exception('Got other exceptions in forward thread')
			time.sleep(0.5)


class set_status_thread(Thread):
	def __init__(self, client: Client, chat_id: int):
		Thread.__init__(self, daemon=True)
		self.switch: bool = True
		self.client: Client = client
		self.chat_id: int = chat_id
		self.start()

	def setOff(self) -> NoReturn:
		self.switch = False

	def run(self) -> NoReturn:
		while self.switch:
			self.client.send_chat_action(self.chat_id, 'TYPING')
			# After 5 seconds, chat action will canceled automatically
			time.sleep(4.5)
		self.client.send_chat_action(self.chat_id, 'CANCEL')


class get_history_process(Thread):

	def __init__(self, client: Client, chat_id: int, target_id:  Union[int, str], offset_id: int=0, dirty_run: bool=False):
		Thread.__init__(self, True)
		self.checker: checkfile = checkfile.get_instance()
		self.configure: configure = configure.get_instance()
		self.client: Client = client
		self.target_id: int = int(target_id)
		self.offset_id: int = offset_id
		self.chat_id: int = chat_id
		self.dirty_run: bool = dirty_run
		self.start()

	def run(self) -> NoReturn:
		checkfunc = self.checker.checkFile if not self.dirty_run else self.checker.checkFile_dirty
		photos, videos, docs = [], [], []
		msg_group = self.client.get_history(self.target_id, offset_id=self.offset_id)
		self.client.send_message(self.chat_id, 'Now process query {}, total {} messages{}'.format(self.target_id, msg_group.messages[0]['message_id'],
			' (Dirty mode)' if self.dirty_run else ''))
		status_thread = set_status_thread(self.client, self.chat_id)
		self.offset_id = msg_group.messages[0]['message_id']
		while self.offset_id > 1:
			for x in list(msg_group.messages):
				if x.photo:
					if not checkfunc((x.photo.sizes[-1].file_id,)): continue
					photos.append((is_bot(x), {'chat':{'id': self.target_id}, 'message_id': x['message_id']}))
				elif x.video:
					if not checkfunc((x.video.file_id,)): continue
					videos.append((is_bot(x), {'chat':{'id': self.target_id}, 'message_id': x['message_id']}))
				elif x.document:
					if '/' in x.document.mime_type and x.document.mime_type.split('/')[0] in ('image', 'video') and not checkfunc((x.document.file_id)):
						continue
					docs.append((is_bot(x), {'chat':{'id': self.target_id}, 'message_id': x['message_id']}))
			try:
				self.offset_id = msg_group.messages[-1]['message_id'] - 1
			except IndexError:
				logger.info('Query channel end by message_id %d', self.offset_id + 1)
				break
			try:
				msg_group = self.client.get_history(self.target_id, offset_id=self.offset_id)
			except pyrogram.errors.FloodWait as e:
				logger.warning('Got flood wait, sleep %d seconds', e.x)
				time.sleep(e.x)
		if not self.dirty_run:
			self.client.send_message(self.configure.query_photo, 'Begin {} forward'.format(self.target_id))
			self.client.send_message(self.configure.query_video, 'Begin {} forward'.format(self.target_id))
			self.client.send_message(self.configure.query_doc, 'Begin {} forward'.format(self.target_id))
			for x in reversed(photos):
				ForwardThread.put(ForwardRequest(self.configure.query_photo if not x[0] else self.configure.bot_for, x[1]))
			for x in reversed(videos):
				ForwardThread.put(ForwardRequest(self.configure.query_video if not x[0] else self.configure.bot_for, x[1]))
			for x in reversed(docs):
				ForwardThread.put(ForwardRequest(self.configure.query_doc if not x[0] else self.configure.bot_for, x[1]))
		status_thread.setOff()
		self.client.send_message(self.chat_id, 'Query completed {} photos, {} videos, {} docs{}'.format(len(photos), len(videos), len(docs), ' (Dirty mode)' if self.dirty_run else ''))
		logger.info('Query %d completed%s, total %d photos, %d videos, %d documents.', self.target_id, ' (Dirty run)' if self.dirty_run else '', len(photos), len(videos), len(docs))
		del photos, videos, docs

class UnsupportType(Exception): pass

class BotControler:
	def __init__(self):
		config = ConfigParser()
		config.read('config.ini')
		self.configure = configure.init_instance(config)
		self.app = Client(
			'inforward',
			config.get('account', 'api_id'),
			config.get('account', 'api_hash')
		)
		self.checker: checkfile = checkfile.init_instance(config.get('mysql', 'host'), config.get('mysql', 'username'), config.get('mysql', 'passwd'), config.get('mysql', 'database'))

		self.redis: redis.Redis = redis.Redis()
		self.redis_prefix: str = ''.join(random.choices(string.ascii_lowercase, k=5))
		self.redis.sadd(f'{self.redis_prefix}for_bypass', *self.checker.query_all_bypass())
		self.redis.sadd(f'{self.redis_prefix}for_blacklist', *self.checker.query_all_blacklist())
		self.redis.mset(self.checker.query_all_special_forward())
		self.redis.sadd(f'{self.redis_prefix}for_admin', *self.checker.query_all_admin())
		self.redis.sadd(f'{self.redis_prefix}for_admin', config.getint('account', 'owner'))

		self.ForwardThread: ForwardThread = ForwardThread()

		self.min_resolution: int = config.getint('forward', 'lowq_resolution', fallback=120)
		self.owner_group_id: int = config.getint('account', 'group_id', fallback=-1)

		self.echo_switch: bool = False
		self.detail_msg_switch: bool = False
		#self.delete_blocked_message_after_blacklist: bool = False
		self.func_blacklist: Callable[[], int] = None
		if self.configure.blacklist:
			self.func_blacklist = ForwardThread.put_blacklist
		self.custom_switch: bool = False

		self.init_handle()

		self.plugins: List[PluginLoader] = []
		self.load_plugins(config)

	def init_handle(self) -> NoReturn:
		self.app.add_handler(MessageHandler(self.get_msg_from_owner_group,			Filters.chat(self.owner_group_id) & Filters.reply))
		self.app.add_handler(MessageHandler(self.get_command_from_target,			Filters.chat(self.configure.predefined_group_list) & Filters.text & Filters.reply))
		self.app.add_handler(MessageHandler(self.pre_check, 						Filters.media & ~Filters.private & ~Filters.sticker & ~Filters.voice & ~Filters.web_page))
		self.app.add_handler(MessageHandler(self.handle_photo,						Filters.photo & ~Filters.private & ~Filters.chat([self.configure.photo, self.configure.lowq])))
		self.app.add_handler(MessageHandler(self.handle_video,						Filters.video & ~Filters.private & ~Filters.chat(self.configure.video)))
		self.app.add_handler(MessageHandler(self.handle_gif,						Filters.animation & ~Filters.private & ~Filters.chat(self.configure.gif)))
		self.app.add_handler(MessageHandler(self.handle_document,					Filters.document & ~Filters.private & ~Filters.chat(self.configure.doc)))
		self.app.add_handler(MessageHandler(self.handle_other,						Filters.media & ~Filters.private & ~Filters.sticker & ~Filters.voice & ~Filters.web_page))
		self.app.add_handler(MessageHandler(self.pre_private,						Filters.private))
		self.app.add_handler(MessageHandler(self.handle_add_bypass,					Filters.command('e') & Filters.private))
		self.app.add_handler(MessageHandler(self.process_query,						Filters.command('q') & Filters.private))
		self.app.add_handler(MessageHandler(self.handle_add_black_list,				Filters.command('b') & Filters.private))
		self.app.add_handler(MessageHandler(self.process_show_detail,				Filters.command('s') & Filters.private))
		self.app.add_handler(MessageHandler(self.set_forward_target_reply,			Filters.command('f') & Filters.reply & Filters.private))
		self.app.add_handler(MessageHandler(self.set_forward_target,				Filters.command('f') & Filters.private))
		self.app.add_handler(MessageHandler(self.add_user,							Filters.command('a') & Filters.private))
		self.app.add_handler(MessageHandler(self.change_code,						Filters.command('pw') & Filters.private))
		self.app.add_handler(MessageHandler(self.undo_blacklist_operation,			Filters.command('undo') & Filters.private))
		self.app.add_handler(MessageHandler(self.switch_detail2,					Filters.command('sd2') & Filters.private))
		self.app.add_handler(MessageHandler(self.switch_detail,						Filters.command('sd') & Filters.private))
		self.app.add_handler(MessageHandler(self.callstopfunc,						Filters.command('stop') & Filters.private))
		self.app.add_handler(MessageHandler(self.show_help_message,					Filters.command('help') & Filters.private))
		self.app.add_handler(MessageHandler(self.process_private,					Filters.private))

	def load_plugins(self, config: ConfigParser):
		try:
			for root, _dirs, filenames in os.walk('.'):
				if root != '.':
					continue
				for filename in filenames:
					if not (filename.startswith('Plugin') and filename.endswith('.py')):
						continue
					try:
						module_name = filename.split('.py')[0]
						mod = importlib.import_module(module_name)
						loader = PluginLoader(mod, module_name, self.app, config, checkfile).create_instace()
						loader.instance.plugin_pending_start()
						self.plugins.append(loader)
					except:
						logger.exception('Loading plugin: %s catch exception!', module_name)
					else:
						logger.info('Load plugin: %s successfully', module_name)
		except FileNotFoundError:
			pass

	def start_plugins(self):
		for x in self.plugins:
			try:
				x.instance.plugin_start()
			except:
				logger.error('Start %s plugin fail', x.module_name)

	def stop_plugins(self):
		for x in self.plugins:
			try:
				x.instance.plugin_stop()
			except:
				logger.error('Stop %s plugin fail', x.module_name)

	def pending_stop_plugins(self):
		for x in self.plugins:
			try:
				x.instance.plugin_pending_stop()
			except:
				logger.error('Pending stop %s plugin fail', x.module_name)

	def user_checker(self, msg: Message) -> bool:
		return self.redis.sismember(f'{self.redis_prefix}for_admin', msg.chat.id)

	def reply_checker_and_del_from_blacklist(self, client: Client, msg: Message) -> NoReturn:
		try:
			pending_del = None
			if msg.reply_to_message.text:
				r = re.match(r'^Add (-?\d+) to blacklist$', msg.reply_to_message.text)
				if r and msg.reply_to_message.from_user.id != msg.chat.id:
					pending_del = r.group(1)
			else:
				group_id = msg.forward_from.id if msg.forward_from else msg.forward_from_chat.id if msg.forward_from_chat else None
				if group_id and group_id in black_list:
					pending_del = group_id
			if pending_del is not None:
				if self.redis.srem(f'{self.redis_prefix}for_blacklist', pending_del):
					self.checker.remove_blacklist(pending_del)
				client.send_message(self.owner_group_id, 'Remove `{}` from blacklist'.format(group_id), parse_mode='markdown')
		except:
			if msg.reply_to_message.text: print(msg.reply_to_message.text)
			logger.exception('Catch!')

	def add_black_list(self, user_id: Union[int, dict], post_back_id=None) -> NoReturn:
		if isinstance(user_id, dict):
			self.app.send_message(self.owner_group_id, 'User id:`{}`\nFrom chat id:`{}`\nForward from id:`{}`'.format(
				user_id['from_user'], user_id['from_chat'], user_id['from_forward']), 'markdown')
			user_id = user_id['from_user']
		# Check is msg from authorized user
		if user_id is None or self.redis.sismember(f'{self.redis_prefix}for_admin', user_id):
			raise KeyError
		if self.redis.sadd(f'{self.redis_prefix}for_blacklist', user_id):
			self.checker.insert_blacklist(user_id)
		logger.info('Add %d to blacklist', user_id)
		if post_back_id is not None:
			self.app.send_message(post_back_id, 'Add `{}` to blacklist'.format(user_id),
				parse_mode='markdown')

	def del_message_by_id(self, client: Client, msg: Message, send_message_to: Optional[Union[int, str]]=None, forward_control: bool=True) -> NoReturn:
		if forward_control and self.configure.blacklist == '':
			logger.error('Request forward but blacklist channel not specified')
			return
		id_from_reply = get_forward_id(msg.reply_to_message)
		q = self.checker.query("SELECT * FROM `msg_detail` WHERE (`from_chat` = %s OR `from_user` = %s OR `from_forward` = %s) AND `to_chat` != %s",
			(id_from_reply, id_from_reply, id_from_reply, self.configure.blacklist))
		if send_message_to:
			_msg = client.send_message(send_message_to, f'Find {len(q)} message(s)')
		if forward_control:
			if send_message_to:
				typing = set_status_thread(client, send_message_to)
			#for x in q:
			#	ForwardThread.put_blacklist(x['to_chat'], x['to_msg'], msg_raw=build_log(
			#		x['from_chat'], x['from_id'], x['from_user'], x['from_forward']))
			#while not ForwardThread.queue.empty(): time.sleep(0.5)
			if send_message_to: typing.setOff()
		for x in q:
			try: client.delete_messages(x['to_chat'], x['to_msg'])
			except: pass
		self.checker.execute("DELETE FROM `msg_detail` WHERE (`from_chat` = %s OR `from_user` = %s OR `from_forward` = %s) AND `to_chat` != %s", (
			id_from_reply, id_from_reply, id_from_reply, self.configure.blacklist))
		if send_message_to:
			_msg.edit(f'Delete all message from `{id_from_reply}` completed.', 'markdown')

	def get_msg_from_owner_group(self, client: Client, msg: Message) -> NoReturn:
		try:
			if msg.text and msg.text == '/undo':
				self.reply_checker_and_del_from_blacklist(client, msg)
		except:
			# TODO: detail exception
			logger.exception('')

	def get_command_from_target(self, client: Client, msg: Message) -> NoReturn:
		if re.match(r'^\/(del(f)?|b|undo|print)$', msg.text):
			if msg.text == '/b':
				#client.delete_messages(msg.chat.id, msg.message_id)
				#for_id = get_forward_id(msg.reply_to_message)
				for_id = self.checker.query_forward_from(msg.chat.id, msg.reply_to_message.message_id)
				#for_id = get_forward_id(msg['reply_to_message'])
				self.add_black_list(for_id, self.owner_group_id)
				# To enable delete message, please add `delete other messages' privilege to bot
				call_delete_msg(30, client.delete_messages, msg.chat.id, (msg.message_id, msg.reply_to_message.message_id))
			elif msg.text == '/undo':
				group_id = msg.reply_to_message.message_id if msg.reply_to_message else None
				if group_id:
					try:
						if self.redis.srem(f'{self.redis_prefix}for_admin', group_id):
							self.checker.remove_admin(group_id)
						#black_list.remove(group_id)
						#self.config['forward']['black_list'] = repr(black_list)
						client.send_message(self.owner_group_id, f'Remove `{group_id}` from blacklist', 'markdown')
					except ValueError:
						client.send_message(self.owner_group_id, f'`{group_id}` not in blacklist', 'markdown')
			elif msg.text == '/print' and msg.reply_to_message is not None:
				print(msg.reply_to_message)
			else:
				call_delete_msg(20, client.delete_messages, msg.chat.id, msg.message_id)
				if get_forward_id(msg.reply_to_message):
					self.del_message_by_id(client, msg, self.owner_group_id, msg.text[-1] == 'f')

	@staticmethod
	def get_file_id(msg: Message, _type: str) -> str:
		return getattr(msg, _type).file_id

	@staticmethod
	def get_file_type(msg: Message) -> str:
		s = BotControler._get_file_type(msg)
		if s == 'error':
			raise UnsupportType()
		return s

	@staticmethod
	def _get_file_type(msg: Message) -> str:
		return 'photo' if msg.photo else \
			'video' if msg.video else \
			'animation' if msg.animation else \
			'sticker' if msg.sticker else \
			'voice' if msg.voice else \
			'document' if msg.document else \
			'audio' if msg.audio else \
			'contact' if msg.contact else 'error'

	def pre_check(self, _client: Client, msg: Message) -> NoReturn:
		try:
			if self.redis.sismember(f'{self.redis_prefix}for_bypass', msg.chat.id) or not self.checker.checkFile(self.get_file_id(msg, self.get_file_type(msg))):
				return
		except UnsupportType:
			pass
		else:
			raise ContinuePropagation

	def blacklist_checker(self, msg: Message) -> NoReturn:
		return self.redis.sismember(f'{self.redis_prefix}for_blacklist', msg.chat.id) or \
				(msg.from_user and self.redis.sismember(f'{self.redis_prefix}for_blacklist', msg.from_user.id)) or \
				(msg.forward_from and self.redis.sismember(f'{self.redis_prefix}for_blacklist', msg.forward_from.id)) or \
				(msg.forward_from_chat and self.redis.sismember(f'{self.redis_prefix}for_blacklist', msg.forward_from_chat.id))

	@staticmethod
	def do_nothing(*args):
		pass

	def forward_msg(self, msg: Message, to: int, what: str='photo') -> NoReturn:
		if self.blacklist_checker(msg):
			if msg.from_user and msg.from_user.id == 630175608: return
			self.func_blacklist(BlackListForwardRequest(msg, LogStruct(True, 'forward blacklist context %s from %s (id: %d)', what, msg.chat.title, msg.chat.id)))
			return
		forward_target = to
		#spec_target = None if what == 'other' else self.redis.get(f'{self.redis_prefix}{msg.chat.id}')
		spec_target = None if what == 'other' else self.redis.get(msg.chat.id)
		if spec_target is None:
			#spec_target = self.redis.get(f'{self.redis_prefix}{msg.forward_from_chat.id}')
			if msg.forward_from_chat:
				spec_target = self.redis.get(msg.forward_from_chat.id)
		if spec_target is not None:
			forward_target = getattr(self.configure, spec_target.decode())
		elif is_bot(msg):
			forward_target = self.configure.bot
		self.ForwardThread.put(ForwardRequest(forward_target, msg, LogStruct(True, 'forward %s from %s (id: %d)', what, msg.chat.title, msg.chat.id)))

	def handle_photo(self, _client: Client, msg: Message) -> NoReturn:
		self.forward_msg(msg, self.configure.photo if self.checker.check_photo(msg.photo) else self.configure.lowq)

	def handle_video(self, _client: Client, msg: Message) -> NoReturn:
		self.forward_msg(msg, self.configure.video, 'video')

	def handle_gif(self, _client: Client, msg: Message) -> NoReturn:
		self.forward_msg(msg, self.configure.gif, 'gif')

	def handle_document(self, _client: Client, msg: Message):
		if msg.document.file_name.split('.')[-1] in ('com', 'exe', 'bat', 'cmd'): return
		forward_target = self.configure.doc if '/' in msg.document.mime_type and msg.document.mime_type.split('/')[0] in ('image', 'video') else self.configure.other
		self.forward_msg(msg, forward_target, 'doc' if forward_target != self.configure.other else 'other')

	def handle_other(self, _client: Client, msg: Message) -> NoReturn:
		self.forward_msg(msg, self.configure.other, 'other')

	def pre_private(self, client: Client, msg: Message) -> NoReturn:
		if not self.user_checker(msg):
			client.send(api.functions.messages.ReportSpam(peer=client.resolve_peer(msg.chat.id)))
			return
		client.send(api.functions.messages.ReadHistory(peer=client.resolve_peer(msg.chat.id), max_id=msg.message_id))
		raise ContinuePropagation

	def handle_add_bypass(self, _client: Client, msg: Message) -> NoReturn:
		if len(msg.text) < 4:
			return
		if self.redis.sadd(f'{self.redis_prefix}for_bypass', msg.text[3:]):
			self.checker.insert_bypass(msg.text[3:])
		msg.reply('Add `{}` to bypass list'.format(msg.text[3:]), parse_mode='markdown')
		logger.info('add except id: %s', msg.text[3:])

	def process_query(self, client: Client, msg: Message) -> NoReturn:
		r = re.match(r'^\/q (-?\d+)(d)?$', msg.text)
		if r is None:
			return
		get_history_process(client, msg.chat.id, r.group(1), dirty_run=r.group(2) is not None)

	def handle_add_black_list(self, client: Client, msg: Message) -> NoReturn:
		try: self.add_black_list(msg.text[3:])
		except:
			client.send_message(msg.chat.id, "Check your input")
			logger.exception('Catch!')

	def process_show_detail(self, _client: Client, msg: Message) -> NoReturn:
		self.echo_switch = not self.echo_switch
		msg.reply('Set echo to {}'.format(self.echo_switch))

	def set_forward_target_reply(self, _client: Client, msg: Message) -> NoReturn:
		if msg.reply_to_message.text is not None: return
		r = re.match(r'^forward_from = (-\d+)$', msg.reply_to_message.text)
		r1 = re.match(r'^\/f (other|photo|bot|video|anime|gif|doc|lowq)$', msg.text)
		if r is None or r1 is None: return
		self._set_forward_target(r.group(1), r1.group(1), msg)
		#do_spec_forward.update({int(r.group(1)): r1.group(1)})
		#self.config['forward']['special'] = repr(do_spec_forward)
		#self.checker.update_forward_target(r1.group(1), r.group(1))
		#self._set_forward_target(r1.group)
		#msg.reply('Set group `{}` forward to `{}`'.format(r.group(1), r1.group(1)), parse_mode='markdown')

	def set_forward_target(self, _client: Client, msg: Message) -> NoReturn:
		r = re.match(r'^\/f (-?\d+) (other|photo|bot|video|anime|gif|doc|lowq)$', msg.text)
		if r is None:
			return
		self._set_forward_target(r.group(1), r.group(2), msg)

	def _set_forward_target(self, chat_id: int, target: str, msg: Message) -> NoReturn:
		#self.redis.set(f'{self.redis_prefix}{chat_id}', target)
		self.redis.set(chat_id, target)
		self.checker.update_forward_target(chat_id, target)
		msg.reply(f'Set group `{chat_id}` forward to `{target}`', parse_mode='markdown')

	def add_user(self, _client: Client, msg: Message) -> NoReturn:
		r = re.match(r'^/a (.+)$', msg.text)
		if r and r.group(1) == self.configure.authorized_code:
			if self.redis.sadd(f'{self.redis_prefix}for_admin', msg.chat.id):
				self.checker.insert_admin(msg.chat.id)
			msg.reply('Success add to authorized users.')

	def change_code(self, _client: Client, msg: Message) -> NoReturn:
		r = re.match(r'^/pw (.+)$', msg.text)
		if r:
			msg.reply('Success changed authorize code.')

	def undo_blacklist_operation(self, client: Client, msg: Message) -> NoReturn:
		self.reply_checker_and_del_from_blacklist(client, msg)

	def switch_detail2(self, _client: Client, msg: Message) -> NoReturn:
		self.custom_switch = not self.custom_switch
		msg.reply(f'Switch custom print to {self.custom_switch}')

	def switch_detail(self, _client: Client, msg: Message) -> NoReturn:
		self.detail_msg_switch = not self.detail_msg_switch
		msg.reply(f'Switch detail print to {self.detail_msg_switch}')

	def callstopfunc(self, _client: Client, msg: Message) -> NoReturn:
		#msg.reply('Exiting...')
		#Thread(target=process_exit.exit_process, args=(2,)).start()
		pass

	def show_help_message(self, _client: Client, msg: Message) -> NoReturn:
		msg.reply(""" Usage:
		/e <chat_id>            Add `chat_id' to bypass list
		/a <password>           Use the `password' to obtain authorization
		/q <chat_id>            Request to query one specific `chat_id'
		/b <chat_id>            Add `chat_id' to blacklist
		/s                      Toggle echo switch
		/f <chat_id> <target>   Add `chat_id' to specified forward rules
		/pw <new_password>      Change password to new password
		""", parse_mode='text')

	def process_private(self, _client: Client, msg: Message) -> NoReturn:
		if self.custom_switch:
			obj = getattr(msg, self.get_file_type(msg), None)
			if obj:
				msg.reply('```{}```\n{}'.format(str(obj), 'Resolution: `{}`'.format(msg.photo.file_size/(msg.photo.width * msg.photo.height)*1000) if msg.photo else ''), parse_mode='markdown')
		if self.echo_switch:
			msg.reply('forward_from = `{}`'.format(get_forward_id(msg, -1)), parse_mode='markdown')
			if self.detail_msg_switch: print(msg)
		if msg.text is None: return
		r = re.match(r'^Add (-?\d+) to blacklist$', msg.text)
		if r is None: return
		self.add_black_list(r.group(1), msg.chat.id)

	def start(self) -> NoReturn:
		self.app.start()
		self.ForwardThread.start()
		self.start_plugins()

	def idle(self) -> NoReturn:
		try:
			self.app.idle()
		except InterruptedError:
			pass

	def stop(self) -> NoReturn:
		ForwardThread.switch = False
		self.pending_stop_plugins()
		if not ForwardThread.queue.empty():
			time.sleep(0.5)
		self.app.stop()
		checkfile.close_instance()
		self.stop_plugins()


def call_delete_msg(interval: int, func, target_id: int, msg_: Message) -> NoReturn:
	_t = Timer(interval, func, (target_id, msg_))
	_t.daemon = True
	_t.start()

def main() -> NoReturn:
	bot = BotControler()
	bot.start()
	bot.idle()
	bot.stop()


if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(lineno)d - %(message)s')
	logging.getLogger('pyrogram').setLevel(logging.WARNING)
	main()
