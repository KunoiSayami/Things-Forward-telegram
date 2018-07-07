# -*- coding: utf-8 -*-
# main.py
# Copyright (C) 2018 Too-Naive
#
# This module is part of things-forward-telegram and is released under
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
import re, os, time, json
from datetime import datetime
from queue import Queue, Empty
from libpy3.mysqldb import mysqldb
from configparser import ConfigParser
from pymysql.err import ProgrammingError
from threading import Thread, Lock, Timer
from pyrogram import Client, Filters, ChatAction, api

global app
config = ConfigParser()
config.read('config.ini')
bypass_list = [int(x) for x in eval(config['forward']['bypass_list'])]
black_list = [int(x) for x in eval(config['forward']['black_list'])]
do_spec_forward = eval(config['forward']['special'])
echo_switch = False
#black_list_listen_mode = False # Deprecated
delete_blocked_message_after_blacklist = False
authorized_users = eval(config['account']['auth_users'])
func_blacklist = None
pre_defined_list = [int(x) for x in [config['forward']['to_photo'], config['forward']['to_video'], config['forward']['to_other'],
	config['forward']['bot_for'], config['forward']['to_anime']]]

class checkfile(mysqldb):
	def __init__(self):
		mysqldb.__init__(self, 'localhost', config['mysql']['username'], config['mysql']['passwd'],
			config['mysql']['database'])
	def check(self, sql, exec_sql, args=()):
		if self.query1(sql, args) is None:
			self.execute(exec_sql, args)
			self.commit()
			return True
		else:
			return False
	def checkFile(self, args):
		assert isinstance(args, tuple)
		return self.check("SELECT `id` FROM `file_id` WHERE `id` = %s", 
			"INSERT INTO `file_id` (`id`,`timestamp`) VALUES (%s, CURRENT_TIMESTAMP())", args)
	def checkFile_dirty(self, args):
		assert isinstance(args, tuple)
		return self.query1("SELECT `id` FROM `file_id` WHERE `id` = %s", args) is None
	def insert_log(self, *args):
		self.execute("INSERT INTO `msg_detail` (`to_chat`, `to_msg`, `from_chat`, `from_id`, `from_user`, `from_forward`) \
			VALUES ({}, {}, {}, {}, {}, {})".format(*args))
		self.commit()

checker = checkfile()

class forward_thread(Thread):
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
	def __init__(self, client):
		Thread.__init__(self)
		self.daemon = True
		self.client = client
		self.start()
	@staticmethod
	def put_blacklist(from_chat, from_id, log_control=(False,), msg_raw=None):
		forward_thread.put(int(config['forward']['to_blacklist']), from_chat, from_id, log_control, msg_raw)
	@staticmethod
	def put(forward_to, from_chat, from_id, log_control=(False,), msg_raw=None):
		forward_thread.queue.put_nowait((forward_to, from_chat, from_id, log_control, msg_raw))
	@staticmethod
	def get():
		return forward_thread.queue.get()
	@staticmethod
	def getStatus():
		return forward_thread.switch
	def run(self):
		global checker
		while self.getStatus():
			target_id, chat_id, msg_id, Loginfo, msg_raw = self.get()
			try:
				r = self.client.forward_messages(target_id, chat_id, msg_id, True)
				assert r['chat']['id'] == target_id
				checker.insert_log(r['chat']['id'], r['message_id'], msg_raw['chat']['id'],
					msg_raw['message_id'], get_msg_from(msg_raw), get_the_fucking_id_ex(msg_raw, -1))
				if Loginfo[0]:
					Log.info(Loginfo[1], *Loginfo[2:])
			except ProgrammingError:
				Log.exc()
			except:
				if msg_raw is not None and target_id != int(config['forward']['to_blacklist']):
					print(msg_raw)
				Log.exc()
			time.sleep(0.5)

class set_status_thread(Thread):
	def __init__(self, client, chat_id):
		Thread.__init__(self)
		self.daemon = True
		self.switch = True
		self.client = client
		self.chat_id = chat_id
		self.start()
	def setOff(self):
		self.switch = False
	def run(self):
		while self.switch:
			self.client.send_chat_action(self.chat_id, ChatAction.TYPING)
			# After 5 seconds, chat action will canceled automatically
			time.sleep(4.5)
		self.client.send_chat_action(self.chat_id, ChatAction.CANCEL)

class get_history_process(Thread):
	def __init__(self, client, chat_id, target_id, offset_id=0, dirty_run=False):
		Thread.__init__(self)
		self.daemon = True
		self.client = client
		self.target_id = int(target_id)
		self.offset_id = offset_id
		self.chat_id = chat_id
		self.dirty_run = dirty_run
		self.start()
	def run(self):
		global checker
		checkfunc = checker.checkFile if not self.dirty_run else checker.checkFile_dirty
		photos, videos = [], []
		msg_group = self.client.get_history(self.target_id, offset_id=self.offset_id)
		self.client.send_message(self.chat_id, 'Now process query {}, total {} messages'.format(self.target_id, msg_group.messages[0]['message_id']))['message_id']
		status_thread = set_status_thread(self.client, self.chat_id)
		self.offset_id = msg_group.messages[0]['message_id']
		while self.offset_id > 1:
			for x in list(msg_group.messages):
				try:
					if not checkfunc((x['photo'][0]['file_id'],)):
						continue
					photos.append((is_bot(x), {'chat':{'id': self.target_id}, 'message_id': x['message_id']}))
					continue
				except (KeyError, TypeError):
					pass
				try:
					if not checkfunc((x['video']['file_id'],)):
						continue
					videos.append((is_bot(x), {'chat':{'id': self.target_id}, 'message_id': x['message_id']}))
					continue
				except (KeyError, TypeError):
					pass
			self.offset_id = msg_group.messages[-1]['message_id'] - 1
			msg_group = self.client.get_history(self.target_id, offset_id=self.offset_id)
		if not self.dirty_run:
			self.client.send_message(int(config['forward']['query_photo']), 'Begin {} forward'.format(self.target_id))
			self.client.send_message(int(config['forward']['query_video']), 'Begin {} forward'.format(self.target_id))
			for x in reversed(photos):
				forward_thread.put(int(config['forward']['query_photo']) if not x[0] else int(config['forward']['bot_for']), self.target_id, x[1]['message_id'], msg_raw=x[1])
			for x in reversed(videos):
				forward_thread.put(int(config['forward']['query_video']) if not x[0] else int(config['forward']['bot_for']), self.target_id, x[1]['message_id'], msg_raw=x[1])
		status_thread.setOff()
		self.client.send_message(self.chat_id, 'Query completed {} photos, {} videos'.format(len(photos), len(videos)))
		Log.info('Query {} completed{}, total {} photos, {} videos.', self.target_id, ' (Dirty run)' if self.dirty_run else '', len(photos), len(videos))
		del photos
		del videos

class process_exit(Thread):
	def __init__(self):
		Thread.__init__(self)
		self.daemon = True
		self.start()
	@staticmethod
	def exit_process(sleep=0):
		global app, checker
		time.sleep(sleep)
		with open('config.ini', 'w') as fout:
			config.write(fout)
		app.stop()
		checker.close()
		forward_thread.switch = False
		time.sleep(0.5)
		forward_list = []
		if not forward_thread.queue.empty():
			while not forward_thread.queue.empty():
				target_id, chat_id, msg_id, Loginfo, _ = forward_thread.queue.get_nowait()
				forward_list.append([target_id, chat_id, msg_id, list(Loginfo), None])
			with open('forward_list', 'w') as fout:
				fout.write(repr(forward_list))
		os._exit(0)
	def run(self):
		print("\rProgram is now running, type `exit\' to exit program")
		try:
			while input() != 'exit': pass
		except:
			pass
		self.exit_process()

def get_target(type_name):
	return {'other': config['forward']['to_other'], 'photo': config['forward']['to_photo'], 
		'bot': config['forward']['bot_for'], 'video': config['forward']['to_video'],
		'anime': config['forward']['to_anime']}[type_name] if type_name in ['other', 'photo', 'bot', 'video', 'anime'] else type_name

def forward_msg(client, msg, to, what='photo'):
	forward_msg_ex(client, json.loads(str(msg)), config['forward']['bot_for'] if is_bot(msg) else to, what)

def get_forward_target(msg):
	r = do_spec_forward.get(msg['chat']['id'])
	if r is None:
		try:
			r = do_spec_forward.get(msg['forward_from_chat']['id'])
		except (KeyError, TypeError):
			pass
	return r

def blacklist_checker(msg):
	return any((get_msg_key(msg, 'chat', 'id') in black_list, get_msg_key(msg, 'forward_from_chat', 'id') in black_list,
		get_msg_key(msg, 'forward_from', 'id') in black_list))

def forward_msg_ex(client, msg, to, what):
	if blacklist_checker(msg):
		func_blacklist(msg['chat']['id'], msg['message_id'], (True, 'forward blacklist context {} from {} (id: {})', what, msg['chat']['title'], msg['chat']['id']), msg)
		#Log.info('Jump over forward msg from {}', msg['chat']['id'])
		return
	r = get_forward_target(msg)
	if r is not None:
		forward_thread.put(int(get_target(r)), msg['chat']['id'], msg['message_id'], (True, 'forward {} from {} (id: {})', what, msg['chat']['title'], msg['chat']['id']), msg)
	else:
		forward_thread.put(int(to), msg['chat']['id'], msg['message_id'], (True, 'forward {} from {} (id: {})', what, msg['chat']['title'], msg['chat']['id']), msg)

def user_checker(msg):
	global authorized_users
	return msg['chat']['id'] in (authorized_users + [int(config['account']['owner'])])

def add_black_list(user_id, process_callback=None):
	global black_list
	if user_checker({'chat':{'id': user_id}}) or user_id is None:
		raise KeyError
	black_list.append(int(user_id))
	black_list = list(set(black_list))
	config['forward']['black_list'] = repr(black_list)
	Log.info('Add {} to blacklist', user_id)
	if process_callback is not None and process_callback[1] != -1:
		process_callback[0].send_message(process_callback[1], 'Add `{}` to blacklist'.format(user_id),
			parse_mode='Markdown')

def reply_checker_and_del_from_blacklist(client, msg):
	global black_list
	try:
		r = re.match(r'^Add (-?\d+) to blacklist$', msg['reply_to_message']['text'])
		if r and msg['reply_to_message']['from_user']['id'] != msg['chat']['id']:
			black_list.pop(int(r.group(1)))
			config['forward']['black_list'] = repr(black_list)
			client.send_message(msg['chat']['id'], 'Del {} from blacklist'.format(r.group(1)))
	except:
		pass

def build_log(chat_id, message_id, from_user_id, froward_from_id):
	return {'chat': {'id': chat_id}, 'message_id': message_id, 'from_user':{'id': from_user_id},
		'forward_from_chat': {'id': froward_from_id}}

def del_message_by_id(client, msg, send_message_to=None, forward_control=True):
	# This operation need `to_blacklist' channel
	# Maybe this practice will be abandoned in the future
	if forward_control and config['forward']['to_blacklist'] == '':
		Log.error('Request forward but blacklist channel not specified')
		return
	#global delete_blocked_message_after_blacklist
	#if msg.get('reply_to_message') is None:
	#	delete_blocked_message_after_blacklist = not delete_blocked_message_after_blacklist
	#	client.send_message(msg['chat']['id'], 'Set delete message after block to {}'.format(delete_blocked_message_after_blacklist))
	#	return
	#r = re.match(r'^Add (-?\d+) to blacklist$', msg['reply_to_message']['text'])
	#print('r is {}')
	#if r is not None:
	#print('request checker')
	id_from_reply = get_the_fucking_id_ex(msg['reply_to_message'])
	q = checker.query("SELECT * FROM `msg_detail` WHERE (`from_chat` = {} OR `from_user` = {} OR `from_forward` = {}) AND `to_chat` != {}".format(
		id_from_reply, id_from_reply, id_from_reply, int(config['forward']['to_blacklist'])))
	#print('send msg to {}'.format(msg['chat']['id']))
	if send_message_to:
		msg_ = client.send_message(int(send_message_to), 'Find {} message(s)'.format(len(q)))
		#typing = set_status_thread(client, int(send_message_to))
	#print(repr(q))
	if forward_control:
		if send_message_to:
			typing = set_status_thread(client, int(send_message_to))
		for x in q:
			forward_thread.put_blacklist(x['to_chat'], x['to_msg'], msg_raw=build_log(
				x['from_chat'], x['from_id'], x['from_user'], x['from_forward']))
		#print('Calling typing function')
		while not forward_thread.queue.empty(): time.sleep(0.5)
		if send_message_to: typing.setOff()
	for x in q:
		try:
			client.delete_messages(x['to_chat'], x['to_msg'])
		except:
			pass
	checker.execute("DELETE FROM `msg_detail` WHERE (`from_chat` = {} OR `from_user` = {} OR `from_forward` = {}) AND `to_chat` != {}".format(
		id_from_reply, id_from_reply, id_from_reply, int(config['forward']['to_blacklist'])))
	if send_message_to:
		client.edit_message_text(int(send_message_to), msg_['message_id'], 'Delete all message from `{}` completed.'.format(id_from_reply), 'markdown')

def get_predefined_group_list():
	return list(set([config['forward']['to_photo'], config['forward']['to_video'], config['forward']['to_other'],
		config['forward']['bot_for'], config['forward']['to_anime']]))

def call_delete_msg(interval, func, target_id, msg_):
	_t = Timer(interval, func, (target_id, msg_))
	_t.daemon = True
	_t.start()

def main():
	# Deprecated: Add forwarded message to blacklist
	# Forward spam message to group may let you get baned (even without any spam report)
	@app.on_message(Filters.chat(0) & Filters.chat(int(get_msg_key(config, 'account', 'group_id', 1))))
	def get_msg_from_owner_group(client, msg):
		#global black_list_listen_mode
		try:
			#if msg['text'] == '/b':
				#black_list_listen_mode = not black_list_listen_mode
				#client.send_message(msg['chat']['id'], 'Set blacklist listen mode to {}'.format(black_list_listen_mode))
			#	pass
			if msg['text'] == '/undo':
				reply_checker_and_del_from_blacklist(client, msg)
			elif msg['text'] == '/del':
				del_message_by_id(client, json.loads(str(msg)), msg['chat']['id'])
			return
		except:
			Log.exc()
		#if black_list_listen_mode:
		#	try:
		#		add_black_list(get_the_fucking_id_ex(msg))
		#		client.delete_messages(msg['chat']['id'], msg['message_id'])
		#		client.send_message(msg['chat']['id'], 'Add {} to blacklist'.format(get_the_fucking_id_ex(msg)))
		#	except:
		#		Log.exc()

	@app.on_message(Filters.chat([int(x) for x in get_predefined_group_list()]) & Filters.text & Filters.reply)
	def get_command_from_target(client, msg):
		#print('calling command')
		if re.match(r'^\/(del(f)?|b)$', msg['text']):
			if msg['text'] == '/b':
				#client.delete_messages(msg['chat']['id'], msg['message_id'])
				add_black_list(get_the_fucking_id_ex(msg['reply_to_message']),
					(client, int(get_msg_key(config, 'account', 'group_id', -1))))
				# To enable delete message, please add `delete other messages' privilege to bot
				call_delete_msg(60, client.delete_messages, msg['chat']['id'], (msg['message_id'], msg['reply_to_message']['message_id']))
			else:
			#if msg['text'] == '/del':
				call_delete_msg(30, client.delete_messages, msg['chat']['id'], msg['message_id'])
				#client.delete_messages(msg['chat']['id'], msg['message_id'])
				if get_the_fucking_id_ex(msg['reply_to_message']):
					del_message_by_id(client, msg, get_msg_key(config, 'account', 'group_id', None), msg['text'][-1] == 'f')
			#else:
				# Processing undo action
			#	reply_checker_and_del_from_blacklist(client, msg)

	@app.on_message(Filters.photo & ~Filters.private)
	def handle_photo(client, msg):
		if msg['chat']['id'] == int(config['forward']['to_photo']) or msg['chat']['id'] in bypass_list or \
			not checker.checkFile((msg['photo'][0]['file_id'],)):
			return
		forward_msg(client, msg, config['forward']['to_photo'])

	@app.on_message(Filters.video & ~Filters.private)
	def handle_video(client, msg):
		if msg['chat']['id'] == int(config['forward']['to_video']) or msg['chat']['id'] in bypass_list:
			return
		try:
			if not checker.checkFile((msg['video']['file_id'],)):
				return
		except KeyError:
			if not checker.checkFile((msg['DocumentAttributeVideo']['file_id'],)):
				return
		forward_msg(client, msg, config['forward']['to_video'], 'video')

	@app.on_message(Filters.media & ~Filters.private & ~Filters.sticker & ~Filters.voice)
	def handle_other(client, msg):
		forward_msg(client, msg, config['forward']['to_other'])

	@app.on_message(Filters.command("e"))
	def add_Except(client, msg):
		if len(msg['text']) < 4 or not user_checker(msg):
			return
		global bypass_list
		bypass_list.append(int(msg['text'][3:]))
		bypass_list = list(set(bypass_list))
		config['forward']['bypass_list'] = repr(bypass_list)
		Log.info('add except id:{}', msg['text'][3:])

	@app.on_message(Filters.command('q'))
	def process_query(client, msg):
		r = re.match(r'^\/q (-?\d+)(d)?$', msg['text'])
		if r is None or not user_checker(msg):
			return
		get_history_process(client, msg['chat']['id'], r.group(1), dirty_run=r.group(2) is not None)

	@app.on_message(Filters.command('b'))
	def add_BlackList(client, msg):
		#global black_list_listen_mode
		if not user_checker(msg):
			return
		global black_list
		#if len(msg['text']) == 2:
		#	black_list_listen_mode = not black_list_listen_mode
		#	client.send_message(msg['chat']['id'], 'Set blacklist listen mode to {}'.format(black_list_listen_mode))
		#	return
		try:
			add_black_list(msg['text'][3:])
		except:
			client.send_message(msg['chat']['id'], "Check your input")
			Log.exc(False)

	@app.on_message(Filters.command('s'))
	def process_show_detail(client, msg):
		if not user_checker(msg):
			return
		global echo_switch
		echo_switch = not echo_switch
		client.send_message(msg['chat']['id'], 'Set echo to {}'.format(echo_switch))
	
	@app.on_message(Filters.command('f'))
	def set_forward_target(client, msg):
		if not user_checker(msg):
			return
		r = re.match(r'^\/f (-?\d+) (other|photo|bot|video|anime)$', msg['text'])
		if r is None:
			return
		do_spec_forward.update({int(r.group(1)): r.group(2)})
		config['forward']['special'] = repr(do_spec_forward)
		client.send_message(msg['chat']['id'], 'Set group `{}` forward to `{}`'.format(
			r.group(1), r.group(2)), 'markdown')

	@app.on_message(Filters.command('a'))
	def add_user(client, msg):
		r = re.match(r'^/a (.+)$', msg['text'])
		if r and r.group(1) == config['account']['auth_code']:
			global authorized_users
			authorized_users.append(msg['chat']['id'])
			config['account']['auth_users'] = repr(list(set(authorized_users)))
			client.send_message(msg['chat']['id'], 'Success add to authorized users.')

	@app.on_message(Filters.command('pw'))
	def change_code(client, msg):
		if not user_checker(msg):
			return
		r = re.match(r'^/pw (.+)$', msg['text'])
		if r:
			config['account']['auth_code'] = r.group(1)
			client.send_message(msg['chat']['id'], 'Success changed authorize code.')

	@app.on_message(Filters.command('undo'))
	def undo_blacklist_operation(client, msg):
		reply_checker_and_del_from_blacklist(client, msg)

	@app.on_message(Filters.command('stop'))
	def callstopfunc(client, msg):
		if not user_checker(msg):
			return
		client.send_message(msg['chat']['id'], 'Exiting...')
		Thread(target=process_exit.exit_process, args=(2,)).start()

	#@app.on_message(Filters.command('del'))
	#def del_specified_blacklist_message(client, msg):
	#	del_message_by_id(client, json.loads(str(msg)))

	@app.on_message(Filters.group & Filters.text)
	def showid_process(client, msg):
		if not user_checker(msg): return
		global echo_switch
		if echo_switch and msg['text'] == '/getid':
			#print(msg['chat']['id'])
			client.send_message(msg['from_user']['id'], '{}'.format(msg['chat']['id']))

	@app.on_message(Filters.command('help'))
	def show_help_message(client, msg):
		if not user_checker(msg): return
		client.send_message(msg['chat']['id'], """ Usage:
		/e <chat_id>            Add `chat_id' to bypass list
		/a <password>           Use the `password' to obtain authorization
		/q <chat_id>            Request to query one specific `chat_id'
		/b <chat_id>            Add `chat_id' to blacklist
		/s                      Toggle echo switch
		/f <chat_id> <target>   Add `chat_id' to specified forward rules
		/pw <new_password>      Change password to new password
		/stop                   Stop bot
		/getid                  Group only: get group `chat_id' (Deprecated)
		""")

	@app.on_message(Filters.private)
	def process_private(client, msg):
		client.send(api.functions.messages.ReadHistory(client.resolve_peer(msg['chat']['id']), msg['message_id']))
		if not user_checker(msg):
			return
		global echo_switch, black_list #, black_list_listen_mode
		reply_checker_and_del_from_blacklist(client, msg)
		if echo_switch:
			client.send_message(msg['chat']['id'], 'forward_from = `{}`'.format(get_the_fucking_id_ex(msg, -1)),
				parse_mode='markdown')
			print(msg)
		#if black_list_listen_mode:
		#	add_black_list(get_the_fucking_id(msg))
		#	client.delete_messages(msg['chat']['id'], msg['message_id'])
		#	client.send_message(msg['chat']['id'], 'Add {} to blacklist'.format(get_the_fucking_id(msg)))

	@app.on_message()
	def passfunction(_, __):
		pass

	app.start()
	process_exit()
	app.idle()

def do_nothing(*args, **kwargs):
	Log.info('Jump over forward msg from {}', args[0])

def init():
	global app, func_blacklist

	assert isinstance(do_spec_forward, dict), 'do_spec_forward must be dict'

	# if there is any message not forward, put them to forward queue
	try:
		with open('forward_list') as fin:
			forward_list = eval(fin.read())
	except:
		forward_list = []
	finally:
		for x in forward_list:
			forward_thread.queue.put_nowait(tuple(x))

	if config['forward']['to_blacklist'] != '':
		func_blacklist = forward_thread.put_blacklist
	else:
		func_blacklist = do_nothing

	app = Client(session_name='inforward',
		api_id=config['account']['api_id'],
		api_hash=config['account']['api_hash'])

	forward_thread(app)

if __name__ == '__main__':
	init()
	main()