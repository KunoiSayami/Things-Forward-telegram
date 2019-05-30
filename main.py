# -*- coding: utf-8 -*-
# main.py
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
from getitem import *
from libpy3 import Log
import re, os, time, base64
from queue import Queue
from libpy3.mysqldb import mysqldb
from configparser import ConfigParser
from pymysql.err import ProgrammingError
from threading import Thread, Lock, Timer
from pyrogram import Client, Filters, api, Message, PhotoSize
import pyrogram.errors

global app
config = ConfigParser()
config.read('config.ini')
bypass_list = [int(x) for x in eval(config['forward']['bypass_list'])]
black_list = [int(x) for x in eval(config['forward']['black_list'])]
do_spec_forward = eval(config['forward']['special'])
echo_switch = False
detail_msg_switch = False
#black_list_listen_mode = False # Deprecated
delete_blocked_message_after_blacklist = False
authorized_users = eval(config['account']['auth_users'])
func_blacklist = None
min_resolution = eval(config['forward']['lowq_resolution']) if config.has_option('forward', 'lowq_resolution') else 120
custom_switch = False
#blacklist_keyword = eval(config['forward']['blacklist_keyword'])
restart_require = False

class checkfile(mysqldb):
	def __init__(self):
		mysqldb.__init__(self, 'localhost', config['mysql']['username'], config['mysql']['passwd'],
			config['mysql']['database'])
	def check(self, sql, exec_sql, args=()):
		try:
			if self.query1(sql, args) is None:
				self.execute(exec_sql, args)
				self.commit()
				return True
			else:
				return False
		except:
			Log.exc()
			return False
	def checkFile(self, args):
		return self.check("SELECT `id` FROM `file_id` WHERE `id` = %s",
			"INSERT INTO `file_id` (`id`,`timestamp`) VALUES (%s, CURRENT_TIMESTAMP())", args)
	def checkFile_dirty(self, args):
		return self.query1("SELECT `id` FROM `file_id` WHERE `id` = %s", args) is None
	def insert_log(self, *args):
		self.execute("INSERT INTO `msg_detail` (`to_chat`, `to_msg`, `from_chat`, `from_id`, `from_user`, `from_forward`) \
			VALUES ({}, {}, {}, {}, {}, {})".format(*args))
		self.commit()
	@staticmethod
	def check_photo(photo: PhotoSize):
		return not (photo.file_size / (photo.width * photo.height) * 1000 < min_resolution or photo.file_size < 40960)

checker = checkfile()

class forward_thread(Thread):
	class id_obj(object):
		def __init__(self, _id: int):
			self.id = _id
	class build_msg(object):
		def __init__(self, chat_id: int, msg_id: int, from_user_id: int = -1, forward_from_id = -1):
			self.chat = forward_thread.id_obj(chat_id)
			self.message_id = msg_id
			self.from_user = forward_thread.id_obj(from_user_id)
			self.forward_from = forward_thread.id_obj(forward_from_id)
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
	def __init__(self, client: Client):
		Thread.__init__(self, daemon=True)
		self.client = client
		self.cut_switch = config.has_option('forward', 'cut_long_text') and config['forward']['cut_long_text'] == 'True'
		self.start()
	@staticmethod
	def put_blacklist(from_chat: int, from_id: int, log_control: tuple = (False,), msg_raw: Message or None = None):
		forward_thread.put(int(config['forward']['to_blacklist']), from_chat, from_id, log_control, msg_raw)
	@staticmethod
	def put(forward_to: int, from_chat: int, from_id: int, log_control: tuple = (False,), msg_raw: Message or None = None):
		forward_thread.queue.put_nowait((forward_to, from_chat, from_id, log_control, msg_raw))
	@staticmethod
	def get():
		return forward_thread.queue.get()
	@staticmethod
	def getStatus():
		return forward_thread.switch
	def get_forward_function(self, msg: Message):
		return self.client.send_photo if msg.photo else self.client.send_video if msg.video else self.client.send_document if msg.document else self.client.send_animation if msg.animation else None
	@staticmethod
	def get_file_id(msg: Message):
		return msg.photo.sizes[-1].file_id if msg.photo else msg.video.file_id if msg.video else msg.document.file_id if msg.document else msg.animation.file_id if msg.animation else None
	#@staticmethod
	#def anti_spam(msg):
	#	_msg = json.loads(msg)
	#	if any((_properties in msg for _properties in ('caption', 'text'))):
	#		for x in blacklist_keyword:
	#			pass
	def run(self):
		global checker
		while not self.client.is_started: time.sleep(1)
		while self.getStatus():
			target_id, chat_id, msg_id, Loginfo, msg_raw = self.get()
			try:
				# Drop long text function
				if self.cut_switch and target_id != int(config['forward']['to_blacklist']) and \
					target_id not in (int(config['forward']['bot_for']), int(config['forward']['to_anime'])):
					function = self.get_forward_function(msg_raw)
					from_id = get_forward_id(msg_raw, get_msg_from(msg_raw))
					#if function is None or from_id is None: raise RuntimeWarning("Can't find message sender")
					if function is None: continue
					if from_id is None: raise RuntimeWarning("Can't find message sender")
					r = function(target_id, self.get_file_id(msg_raw), base64.standard_b64encode(str(from_id).encode()).decode(), disable_notification=True)
				else:
					r = self.client.forward_messages(target_id, chat_id, msg_id, True)
				if msg_raw is None: msg_raw = self.build_msg(chat_id, msg_id)
				checker.insert_log(r.chat.id, r.message_id, msg_raw.chat.id,
					msg_raw.message_id, get_msg_from(msg_raw), get_forward_id(msg_raw, -1))
				if Loginfo[0]:
					Log.info(Loginfo[1], *Loginfo[2:])
			except ProgrammingError:
				Log.exc()
			except pyrogram.errors.exceptions.bad_request_400.MessageIdInvalid:
				pass
			except:
				print(target_id, chat_id, msg_id, None if msg_raw is None else 'NOT_NONE' , Loginfo)
				if msg_raw is not None and target_id != int(config['forward']['to_blacklist']):
					print(msg_raw)
				#self.put(target_id, chat_id, msg_id, Loginfo, msg_raw)
				Log.exc()
			time.sleep(0.5)

class set_status_thread(Thread):
	def __init__(self, client: Client, chat_id: int):
		Thread.__init__(self, daemon=True)
		self.switch = True
		self.client = client
		self.chat_id = chat_id
		self.start()
	def setOff(self):
		self.switch = False
	def run(self):
		while self.switch:
			self.client.send_chat_action(self.chat_id, 'TYPING')
			# After 5 seconds, chat action will canceled automatically
			time.sleep(4.5)
		self.client.send_chat_action(self.chat_id, 'CANCEL')

class get_history_process(Thread):
	def __init__(self, client: Client, chat_id: int, target_id:  int or str, offset_id: int = 0, dirty_run: bool = False):
		Thread.__init__(self, True)
		self.client = client
		self.target_id = int(target_id)
		self.offset_id = offset_id
		self.chat_id = chat_id
		self.dirty_run = dirty_run
		self.start()
	def run(self):
		global checker
		checkfunc = checker.checkFile if not self.dirty_run else checker.checkFile_dirty
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
				Log.notify('Query channel end by message_id {}', self.offset_id + 1)
				break
			try:
				msg_group = self.client.get_history(self.target_id, offset_id=self.offset_id)
			except pyrogram.errors.exceptions.flood_420.FloodWait:
				Log.exc()
				time.sleep(10)
		if not self.dirty_run:
			self.client.send_message(int(config['forward']['query_photo']), 'Begin {} forward'.format(self.target_id))
			self.client.send_message(int(config['forward']['query_video']), 'Begin {} forward'.format(self.target_id))
			self.client.send_message(int(config['forward']['query_doc']), 'Begin {} forward'.format(self.target_id))
			for x in reversed(photos):
				forward_thread.put(int(config['forward']['query_photo']) if not x[0] else int(config['forward']['bot_for']), self.target_id, x[1]['message_id'], msg_raw=x[1])
			for x in reversed(videos):
				forward_thread.put(int(config['forward']['query_video']) if not x[0] else int(config['forward']['bot_for']), self.target_id, x[1]['message_id'], msg_raw=x[1])
			for x in reversed(docs):
				forward_thread.put(int(config['forward']['query_doc']) if not x[0] else int(config['forward']['bot_for']), self.target_id, x[1]['message_id'], msg_raw=x[1])
		status_thread.setOff()
		self.client.send_message(self.chat_id, 'Query completed {} photos, {} videos, {} docs{}'.format(len(photos), len(videos), len(docs), ' (Dirty mode)' if self.dirty_run else ''))
		Log.info('Query {} completed{}, total {} photos, {} videos.', self.target_id, ' (Dirty run)' if self.dirty_run else '', len(photos), len(videos), len(docs))
		del photos, videos, docs

class save_config_Thread(Thread):
	lock_obj = Lock()
	def __init__(self, config: ConfigParser):
		Thread.__init__(self)
		self.config = config
		self.start()
	def run(self):
		with save_config_Thread.lock_obj:
			with open('config.ini', 'w') as fout: self.config.write(fout)
		Log.info('Save configure to file successful')

class process_exit(Thread):
	def __init__(self):
		Thread.__init__(self, daemon=True)
		self.start()
	@staticmethod
	def exit_process(sleep: int = 0):
		global app, checker, config
		print('Processing exit... wait {} second(s)'.format(sleep))
		time.sleep(sleep)
		forward_thread.switch = False
		time.sleep(0.5)
		app.stop()
		save_config_Thread(config).join()
		try: checker.close()
		except:	Log.exc()
		forward_list = []
		if not forward_thread.queue.empty():
			print('Processing forward list')
			while not forward_thread.queue.empty():
				target_id, chat_id, msg_id, Loginfo, _ = forward_thread.queue.get_nowait()
				forward_list.append([target_id, chat_id, msg_id, list(Loginfo), None])
			with open('forward_list', 'w') as fout:
				fout.write(repr(forward_list))
		print('Exiting...')
		os._exit(0)
	def run(self):
		print("Program is now running, type `exit\' to exit program")
		while True:
			try:
				while input() != 'exit': pass
				break
			except:	pass
		self.exit_process()

class log_track_thread(Thread):
	def __init__(self, client: Client):
		Thread.__init__(self, daemon=True)
		self.client = client
		self.start()
	@staticmethod
	def get_log():
		log = Log.LOG_QUEUE.get()
		return log if 'Traceback' not in log else [x for x in log.splitlines() if x != ''][-1]
	def run(self):
		import traceback
		Log.info('Log track thread start successful')
		while True:
			try:
				msg = self.get_log()
				time.sleep(1)
				while not Log.LOG_QUEUE.empty(): msg += '\n{}'.format(self.get_log())
				self.client.send_message(int(config['account']['owner']) if 'InterfaceError' in msg else int(config['account']['group_id']), msg, disable_web_page_preview=True)
			except:
				traceback.print_exc()
				self.client.send_message(int(config['account']['owner']), 'Log thread failure in process, please check console')
				time.sleep(60)

def get_target(type_name: int or None):
	if type_name is None: return 0
	return {
		'other': config['forward']['to_other'],
		'photo': config['forward']['to_photo'],
		'bot': config['forward']['bot_for'],
		'video': config['forward']['to_video'],
		'gif': config['forward']['to_gif'],
		'anime': config['forward']['to_anime'],
		'doc': config['forward']['to_doc'],
		'low': config['forward']['to_lowq']
		}[type_name] if type_name in ['other', 'photo', 'bot', 'video', 'anime', 'gif', 'doc', 'low'] else type_name

def get_predefined_group_list():
	return [int(x) for x in list(set([
		config['forward']['to_photo'],
		config['forward']['to_video'],
		config['forward']['to_other'],
		config['forward']['bot_for'],
		config['forward']['to_anime'],
		config['forward']['to_gif'],
		config['forward']['to_doc'],
		config['forward']['to_lowq']]
		))
	]

def get_real_forward_target(msg: Message, origin_target: str or int):
	r = do_spec_forward.get(msg.chat.id)
	if r is None and msg.forward_from_chat:
		r = do_spec_forward.get(msg.forward_from_chat.id)
	return (config['forward']['bot_for'] if is_bot(msg) else origin_target) if r is None else get_target(r)

def blacklist_checker(msg: Message):
	return any((
		msg.forward_from and msg.forward_from.id in black_list,
		msg.forward_from_chat and msg.forward_from_chat.id in black_list,
		msg.from_user and msg.from_user.id in black_list,
		msg.chat.id in black_list
		))

def forward_msg(msg: Message, to: int or str, what: str = 'photo'):
	if blacklist_checker(msg):
		if msg.from_user is not None and msg.from_user.id == 630175608: return
		func_blacklist(msg.chat.id, msg.message_id, (True, 'forward blacklist context {} from {} (id: {})', what, msg['chat']['title'], msg.chat.id), msg)
		return
	forward_thread.put(int((config['forward']['bot_for'] if is_bot(msg) else to) if what == 'other' else get_real_forward_target(msg, to)),
		msg.chat.id, msg.message_id, (True, 'forward {} from {} (id: {})', what, msg['chat']['title'], msg['chat']['id']), msg)

def user_checker(msg: Message or dict):
	global authorized_users
	return msg['chat']['id'] in (authorized_users + [int(config['account']['owner'])])

def add_black_list(user_id: int or str, process_callback=None):
	global black_list
	# Check is msg from authorized user
	if user_checker({'chat':{'id': int(user_id)}}) or user_id is None: raise KeyError
	if int(user_id) in black_list: return
	if isinstance(user_id, bytes): user_id = user_id.decode()
	black_list.append(int(user_id))
	black_list = list(set(black_list))
	config['forward']['black_list'] = repr(black_list)
	Log.info('Add {} to blacklist', user_id)
	save_config_Thread(config)
	if process_callback is not None and process_callback[1] != -1:
		process_callback[0].send_message(process_callback[1], 'Add `{}` to blacklist'.format(user_id),
			parse_mode='Markdown')

def reply_checker_and_del_from_blacklist(client: Client, msg: Message):
	global black_list
	try:
		if msg.reply_to_message.text:
			r = re.match(r'^Add (-?\d+) to blacklist$', msg.reply_to_message.text)
			if r and msg['reply_to_message']['from_user']['id'] != msg.chat.id:
				black_list.remove(int(r.group(1)))
				config['forward']['black_list'] = repr(black_list)
				client.send_message(msg.chat.id, 'Del {} from blacklist'.format(r.group(1)))
		else:
			group_id = msg.forward_from.id if msg.forward_from else msg.forward_from_chat.id if msg.forward_from_chat else None
			if group_id and group_id in black_list:
				black_list.remove(group_id)
				config['forward']['black_list'] = repr(black_list)
				client.send_message(int(config['account']['group_id'] if config.has_option('account', 'group_id') else config['account']['owner']),
					'Remove `{}` from blacklist'.format(group_id), parse_mode='markdown')
		save_config_Thread(config)
	except:
		if msg.reply_to_message.text: print(msg.reply_to_message.text)
		Log.exc()

def build_log(chat_id: int, message_id: int, from_user_id: int, froward_from_id: int):
	return {'chat': {'id': chat_id}, 'message_id': message_id, 'from_user':{'id': from_user_id},
		'forward_from_chat': {'id': froward_from_id}}

def del_message_by_id(client: Client, msg: Message, send_message_to : int or str = None, forward_control: bool = True):
	if forward_control and config['forward']['to_blacklist'] == '':
		Log.error('Request forward but blacklist channel not specified')
		return
	id_from_reply = get_forward_id(msg['reply_to_message'])
	q = checker.query("SELECT * FROM `msg_detail` WHERE (`from_chat` = %s OR `from_user` = %s OR `from_forward` = %s) AND `to_chat` != %s",
		(id_from_reply, id_from_reply, id_from_reply, int(config['forward']['to_blacklist'])))
	if send_message_to:
		msg_ = client.send_message(int(send_message_to), 'Find {} message(s)'.format(len(q)))
	if forward_control:
		if send_message_to:
			typing = set_status_thread(client, int(send_message_to))
		for x in q:
			forward_thread.put_blacklist(x['to_chat'], x['to_msg'], msg_raw=build_log(
				x['from_chat'], x['from_id'], x['from_user'], x['from_forward']))
		while not forward_thread.queue.empty(): time.sleep(0.5)
		if send_message_to: typing.setOff()
	for x in q:
		try: client.delete_messages(x['to_chat'], x['to_msg'])
		except: pass
	checker.execute("DELETE FROM `msg_detail` WHERE (`from_chat` = {} OR `from_user` = {} OR `from_forward` = {}) AND `to_chat` != {}".format(
		id_from_reply, id_from_reply, id_from_reply, int(config['forward']['to_blacklist'])))
	if send_message_to:
		client.edit_message_text(int(send_message_to), msg_['message_id'], 'Delete all message from `{}` completed.'.format(id_from_reply), 'markdown')

def call_delete_msg(interval: int, func, target_id: int, msg_: Message):
	_t = Timer(interval, func, (target_id, msg_))
	_t.daemon = True
	_t.start()

def main():
	# Deprecated: Add forwarded message to blacklist
	# Forward spam message to group may let you get baned (even without any spam report)
	@app.on_message(Filters.chat(int(get_msg_key(config, 'account', 'group_id', -1))) & Filters.reply)
	def get_msg_from_owner_group(client: Client, msg: Message):
		try:
			if msg.text and msg.text == '/undo':
				reply_checker_and_del_from_blacklist(client, msg)
		except:
			Log.exc()

	@app.on_message(Filters.chat(get_predefined_group_list()) & Filters.text & Filters.reply)
	def get_command_from_target(client: Client, msg: Message):
		if re.match(r'^\/(del(f)?|b|undo|print)$', msg.text):
			if msg.text == '/b':
				#client.delete_messages(msg.chat.id, msg.message_id)
				for_id = get_forward_id(msg['reply_to_message'])
				add_black_list(base64.b64decode(msg.reply_to_message.caption.encode()).decode() if for_id is None else for_id,
					(client, int(get_msg_key(config, 'account', 'group_id', -1))))
				# To enable delete message, please add `delete other messages' privilege to bot
				call_delete_msg(30, client.delete_messages, msg.chat.id, (msg['message_id'], msg['reply_to_message']['message_id']))
			elif msg.text == '/undo':
				group_id = msg.reply_to_message.message_id if msg.reply_to_message else None
				if group_id:
					try:
						black_list.remove(group_id)
						config['forward']['black_list'] = repr(black_list)
						client.send_message(int(get_msg_key(config, 'account', 'group_id', -1)), 'Remove `{}` from blacklist'.format(group_id), parse_mode='markdown')
					except ValueError:
						client.send_message(int(get_msg_key(config, 'account', 'group_id', -1)), '`{}` not in blacklist'.format(group_id), parse_mode='markdown')
			elif msg.text == '/print' and msg.reply_to_message is not None:
				print(msg.reply_to_message)
			else:
				call_delete_msg(20, client.delete_messages, msg.chat.id, msg['message_id'])
				if get_forward_id(msg['reply_to_message']):
					del_message_by_id(client, msg, get_msg_key(config, 'account', 'group_id', None), msg.text[-1] == 'f')

	@app.on_message(Filters.photo & ~Filters.private & ~Filters.chat([int(config['forward']['to_photo']), int(config['forward']['to_lowq'])]))
	def handle_photo(client: Client, msg: Message):
		if msg.chat.id in bypass_list or not checker.checkFile((msg.photo.sizes[-1].file_id,)):
			return
		forward_msg(msg, config['forward']['to_photo'] if checker.check_photo(msg.photo.sizes[-1]) else config['forward']['to_lowq'])

	@app.on_message(Filters.video & ~Filters.private & ~Filters.chat(int(config['forward']['to_video'])))
	def handle_video(client: Client, msg: Message):
		if msg.chat.id in bypass_list or not checker.checkFile((msg.video.file_id,)):
			return
		forward_msg(msg, config['forward']['to_video'], 'video')

	@app.on_message(Filters.animation & ~Filters.private & ~Filters.chat(int(config['forward']['to_gif'])))
	def handle_gif(client: Client, msg: Message):
		if msg.chat.id in bypass_list or not checker.checkFile((msg.animation.file_id,)):
			return
		forward_msg(msg, config['forward']['to_gif'], 'gif')

	@app.on_message(Filters.document & ~Filters.private & ~Filters.chat(int(config['forward']['to_doc'])))
	def handle_document(client: Client, msg: Message):
		if msg.chat.id in bypass_list or not checker.checkFile((msg.document.file_id,)):
			return
		forward_target = config['forward']['to_doc'] if '/' in msg.document.mime_type and msg.document.mime_type.split('/')[0] in ('image', 'video') else config['forward']['to_other']
		forward_msg(msg, forward_target, 'doc' if forward_target != config['forward']['to_other'] else 'other')

	@app.on_message(Filters.chat(get_predefined_group_list()))
	def throw_func(*_): pass

	@app.on_message(Filters.media & ~Filters.private & ~Filters.sticker & ~Filters.voice)
	def handle_other(client: Client, msg: Message):
		forward_msg(msg, config['forward']['to_other'], 'other')

	@app.on_message(Filters.command("e") & Filters.private)
	def add_Except(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if len(msg.text) < 4 or not user_checker(msg):
			return
		global bypass_list
		bypass_list.append(int(msg.text[3:]))
		bypass_list = list(set(bypass_list))
		config['forward']['bypass_list'] = repr(bypass_list)
		client.send_message(msg.chat.id, 'Add `{}` to bypass list'.format(msg.text[3:]), parse_mode='markdown')
		Log.info('add except id:{}', msg.text[3:])

	@app.on_message(Filters.command('q') & Filters.private)
	def process_query(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		r = re.match(r'^\/q (-?\d+)(d)?$', msg.text)
		if r is None or not user_checker(msg):
			return
		get_history_process(client, msg.chat.id, r.group(1), dirty_run=r.group(2) is not None)

	@app.on_message(Filters.command('b') & Filters.private)
	def add_BlackList(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg): return
		global black_list
		try: add_black_list(msg.text[3:])
		except:
			client.send_message(msg.chat.id, "Check your input")
			Log.exc(False)

	@app.on_message(Filters.command('s') & Filters.private)
	def process_show_detail(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg): return
		global echo_switch
		echo_switch = not echo_switch
		client.send_message(msg.chat.id, 'Set echo to {}'.format(echo_switch))

	@app.on_message(Filters.command('f') & Filters.reply & Filters.private)
	def set_forward_target_reply(client: Client, msg: Message):
		if not user_checker(msg) and msg.reply_to_message.text is not None: return
		r = re.match(r'^forward_from = (-\d+)$', msg.reply_to_message.text)
		r1 = re.match(r'^\/f (other|photo|bot|video|anime|gif|doc|lowq)$', msg.text)
		if r is None or r1 is None: return
		do_spec_forward.update({int(r.group(1)): r1.group(1)})
		config['forward']['special'] = repr(do_spec_forward)
		client.send_message(msg.chat.id, 'Set group `{}` forward to `{}`'.format(
			r.group(1), r1.group(1)), 'markdown')

	@app.on_message(Filters.command('f') & Filters.private)
	def set_forward_target(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg):
			return
		r = re.match(r'^\/f (-?\d+) (other|photo|bot|video|anime|gif|doc|lowq)$', msg.text)
		if r is None:
			return
		do_spec_forward.update({int(r.group(1)): r.group(2)})
		config['forward']['special'] = repr(do_spec_forward)
		save_config_Thread(config)
		client.send_message(msg.chat.id, 'Set group `{}` forward to `{}`'.format(
			r.group(1), r.group(2)), 'markdown')

	@app.on_message(Filters.command('a') & Filters.private)
	def add_user(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		r = re.match(r'^/a (.+)$', msg.text)
		if r and r.group(1) == config['account']['auth_code']:
			global authorized_users
			authorized_users.append(msg.chat.id)
			config['account']['auth_users'] = repr(list(set(authorized_users)))
			save_config_Thread(config)
			client.send_message(msg.chat.id, 'Success add to authorized users.')

	@app.on_message(Filters.command('pw') & Filters.private)
	def change_code(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg):
			return
		r = re.match(r'^/pw (.+)$', msg.text)
		if r:
			config['account']['auth_code'] = r.group(1)
			save_config_Thread(config)
			client.send_message(msg.chat.id, 'Success changed authorize code.')

	@app.on_message(Filters.command('undo') & Filters.private)
	def undo_blacklist_operation(client: Client, msg: Message):
		reply_checker_and_del_from_blacklist(client, msg)

	@app.on_message(Filters.command('sd2') & Filters.private)
	def switch_detail2(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg): return
		global custom_switch
		custom_switch = not custom_switch
		client.send_message(msg.chat.id, 'Switch custom print to {}'.format(custom_switch))

	@app.on_message(Filters.command('sd') & Filters.private)
	def switch_detail(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg): return
		global detail_msg_switch
		detail_msg_switch = not detail_msg_switch
		client.send_message(msg.chat.id, 'Switch detail print to {}'.format(detail_msg_switch))

	@app.on_message(Filters.command('stop') & Filters.private)
	def callstopfunc(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg):
			return
		client.send_message(msg.chat.id, 'Exiting...')
		Thread(target=process_exit.exit_process, args=(2,)).start()

	@app.on_message(Filters.command('help') & Filters.private)
	def show_help_message(client: Client, msg: Message):
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		if not user_checker(msg): return
		client.send_message(msg.chat.id, """ Usage:
		/e <chat_id>            Add `chat_id' to bypass list
		/a <password>           Use the `password' to obtain authorization
		/q <chat_id>            Request to query one specific `chat_id'
		/b <chat_id>            Add `chat_id' to blacklist
		/s                      Toggle echo switch
		/f <chat_id> <target>   Add `chat_id' to specified forward rules
		/pw <new_password>      Change password to new password
		/stop                   Stop bot
		""", parse_mode='text')

	@app.on_message(Filters.private)
	def process_private(client: Client, msg: Message):
		if not user_checker(msg):
			client.send(api.functions.messages.ReportSpam(peer = client.resolve_peer(msg.chat.id)))
			return
		client.send(api.functions.messages.ReadHistory(peer = client.resolve_peer(msg.chat.id), max_id = msg.message_id))
		global echo_switch, black_list
		if custom_switch:
			obj = msg.photo.sizes[-1] if msg.photo else msg.video if msg.video else msg.document if msg.document else msg.animation if msg.animation else msg.voice if msg.voice else msg.contact if msg.contact else msg.audio if msg.audio else None
			if obj:
				client.send_message(msg.chat.id, '```{}```\n{}'.format(str(obj),'Resolution: `{}`'.format(msg.photo.sizes[-1].file_size/(msg.photo.sizes[-1].width * msg.photo.sizes[-1].height)*1000) if msg.photo else ''), parse_mode='markdown')
		if echo_switch:
			client.send_message(msg.chat.id, 'forward_from = `{}`'.format(get_forward_id(msg, -1)), parse_mode='markdown')
			if detail_msg_switch: print(msg)
		if msg.text is None: return
		r = re.match(r'^Add (-?\d+) to blacklist$', msg.text)
		if r is None: return
		add_black_list(r.group(1), (client, msg.chat.id))

	@app.on_message()
	def passfunction(_, __):
		pass

	app.start()
	process_exit()
	log_track_thread(app)
	app.idle()
	if restart_require:
		time.sleep(10) # wait to restart

def do_nothing(*args, **kwargs):
	Log.info('Jump over forward msg from {}', args[0])

def init():
	global app, func_blacklist

	assert isinstance(do_spec_forward, dict), 'do_spec_forward must be dict'

	# if there is any message not forward, put them to forward queue
	try:
		with open('forward_list') as fin:
			forward_list = eval(fin.read())
		os.remove('forward_list')
	except: forward_list = []
	finally:
		for x in forward_list:
			forward_thread.queue.put_nowait(tuple(x))

	func_blacklist = forward_thread.put_blacklist if config['forward']['to_blacklist'] != '' else do_nothing

	app = Client(
		session_name = 'inforward',
		api_id = config['account']['api_id'],
		api_hash = config['account']['api_hash']
	)

	forward_thread(app)

if __name__ == '__main__':
	init()
	main()