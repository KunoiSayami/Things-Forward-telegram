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
from configparser import ConfigParser
from pyrogram import Client, Filters, ChatAction
from datetime import datetime
from threading import Thread, Lock
import os
import pymysql.cursors
import traceback
import Log, time
from queue import Queue, Empty
import re

global app
config = ConfigParser()
config.read('config.ini')
bypass_list = [int(x) for x in eval(config['forward']['bypass_list'])]
black_list = [int(x) for x in eval(config['forward']['black_list'])]
mysql_connection = pymysql.connect(host='localhost', user=config['mysql']['username'],
	password=config['mysql']['passwd'], db=config['mysql']['database'], charset='utf8', cursorclass=pymysql.cursors.DictCursor)
do_spec_forward = eval(config['forward']['special'])
echo_switch = False

class checkfile:
	def __init__(self):
		self.cursor = mysql_connection.cursor()
		self.lock = Lock()
	def commit(self):
		with self.lock:
			self.cursor.close()
			mysql_connection.commit()
			self.cursor = mysql_connection.cursor()
	def query(self, sql, args=()):
		self.execute(sql, args)
		return self.cursor.fetchall()
	def query1(self, sql, args=()):
		self.execute(sql, args)
		return self.cursor.fetchone()
	def execute(self, sql, args=()):
		with self.lock:
			self.cursor.execute(sql, args)
	def close(self):
		with self.lock:
			self.cursor.close()
			mysql_connection.commit()
	def check(self, sql, exec_sql, args=()):
		if self.query1(sql, args) is None:
			self.execute(exec_sql, args)
			self.commit()
			return True
		else:
			return False
	def checkFile(self, args):
		assert isinstance(args, tuple)
		return self.check("SELECT `id` FROM `file_id` WHERE id = %s", 
			"INSERT INTO `file_id` (`id`,`timestamp`) VALUES (%s, CURRENT_TIMESTAMP())", args)
	def checkFile_dirty(self, args):
		assert isinstance(args, tuple)
		return self.query1("SELECT `id` FROM `file_id` WHERE id = %s", args) is None

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
	def put(forward_to, from_chat, from_id, log_control=(False,), msg_raw=None):
		forward_thread.queue.put_nowait((forward_to, from_chat, from_id, log_control, msg_raw))
	@staticmethod
	def get():
		return forward_thread.queue.get()
	@staticmethod
	def getStatus():
		return forward_thread.switch
	def run(self):
		while self.getStatus():
			target_id, chat_id, msg_id, Loginfo, msg_raw = self.get()
			try:
				self.client.forward_messages(target_id, chat_id, msg_id, True)
			except Exception:
				if msg_raw is not None:
					print(msg_raw)
				traceback.print_exc()
			if Loginfo[0]:
				Log.info(Loginfo[1], *Loginfo[2:])
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
					photos.append((x['message_id'],is_bot(x)))
					continue
				except (KeyError, TypeError):
					pass
				try:
					if not checkfunc((x['video']['file_id'],)):
						continue
					videos.append((x['message_id'], is_bot(x)))
					continue
				except (KeyError, TypeError):
					pass
			self.offset_id = msg_group.messages[-1]['message_id'] - 1
			msg_group = self.client.get_history(self.target_id, offset_id=self.offset_id)
		#msg_id_group = [x['message_id'] for x in msg_group.messages]
		#print(msg_id_group[1], msg_id_group[-1])
		#msg_id = self.client.send_message(self.chat_id, 'Forwarding from {}'.format(self.target_id))['message_id']
		if not self.dirty_run:
			self.client.send_message(int(config['forward']['query_photo']), 'Begin {} forward'.format(self.target_id))
			self.client.send_message(int(config['forward']['query_video']), 'Begin {} forward'.format(self.target_id))
			for x in reversed(photos):
				forward_thread.put(int(config['forward']['query_photo']) if not x[1] else int(config['forward']['bot_for']), self.target_id, x[0])
				#time.sleep(0.5)
			#self.client.edit_message_text(self.chat_id, msg_id, 'Forwarding from {}\nPhotos forward finished'.format(self.target_id))
			for x in reversed(videos):
				forward_thread.put(int(config['forward']['query_video']) if not x[1] else int(config['forward']['bot_for']), self.target_id, x[0])
				#time.sleep(0.5)
			#self.client.edit_message_text(self.chat_id, msg_id, 'Puted all message to queue, query {} finished.'.format(self.target_id))
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
	def run(self):
		r = ''
		print("\rProgram is now running, type `exit\' to exit program")
		while r != 'exit':
			try:
				r = input()
			except EOFError:
				pass
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

def is_bot(msg):
	try:
		return msg['from_user']['is_bot']
	except Exception:
		return False

def get_target(type_name):
	return {'other': config['forward']['to_other'], 'photo': config['forward']['to_photo'], 
		'bot': config['forward']['bot_for'], 'video': config['forward']['to_video'],
		'anime': config['forward']['to_anime']}[type_name] if type_name in ['other', 'photo', 'bot', 'video', 'anime'] else type_name

def forward_msg(client, msg, to, what='photo'):
	forward_msg_ex(client, msg, config['forward']['bot_for'] if is_bot(msg) else to, what)

def forward_msg_ex(client, msg, to, what):
	if do_spec_forward.get(msg['chat']['id']) is not None:
		forward_thread.put(int(get_target(do_spec_forward[msg['chat']['id']])), msg['chat']['id'], msg['message_id'], (True, 'forward {} from {} (id: {})', what, msg['chat']['title'], msg['chat']['id']), msg)
	else:
		forward_thread.put(int(to), msg['chat']['id'], msg['message_id'], (True, 'forward {} from {} (id: {})', what, msg['chat']['title'], msg['chat']['id']), msg)

def main():
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

	#@app.on_message(Filters.media & ~Filters.private & ~Filters.sticker & ~Filters.voice)
	#def handle_bot(client, msg):
	#	forward_msg_ex(client, msg, config['forward']['bot_for'], 'bot message')

	@app.on_message(Filters.command("e"))
	def add_Except(client, msg):
		if msg['chat']['id'] != int(config['account']['owner']):
			return
		global bypass_list
		bypass_list.append(int(msg['text'][3:]))
		bypass_list = list(set(bypass_list))
		config['forward']['bypass_list'] = repr(bypass_list)
		Log.info('add except id:{}', msg['text'][3:])

	@app.on_message(Filters.command('q'))
	def process_query(client, msg):
		if msg['chat']['id'] != int(config['account']['owner']):
			return
		r = re.match(r'^\/q (-?\d+)(d)?$', msg['text'])
		get_history_process(client, msg['chat']['id'], r.group(1), dirty_run=r.group(2) is not None)

	@app.on_message(Filters.command('b'))
	def add_BlackList(client, msg):
		if msg['chat']['id'] != int(config['account']['owner']):
			return
		global black_list
		black_list.append(int(msg['text'][3:]))
		black_list = list(set(black_list))
		config['forward']['black_list'] = repr(black_list)
		Log.info('Add {} to black list', msg['text'][3:])
	#app.on_message(Filters.command("q"))
	#ef hand_query(client, msg):
	#	if msg['chat']['id'] != int(config['account']['owner']):
	#		return
	#	client.get_history()

	@app.on_message(Filters.command('s'))
	def process_show_detail(client, msg):
		if msg['chat']['id'] != int(config['account']['owner']):
			return
		global echo_switch
		echo_switch = False if echo_switch else True
		client.send_message(msg['chat']['id'], 'Set echo to {}'.format(echo_switch))
	
	@app.on_message(Filters.command('f'))
	def set_forward_target(client, msg):
		if msg['chat']['id'] != int(config['account']['owner']):
			return
		r = re.match(r'^\/f (-?\d+) (other|photo|bot|video|anime)$', msg['text'])
		if r is None:
			return
		do_spec_forward.update({r.group(1): r.group(2)})
		config['forward']['special'] = repr(do_spec_forward)
		client.send_message(msg['chat']['id'], 'Set group {} forward to {}'.format(r.group(1), r.group(2)))

	@app.on_message(Filters.group & Filters.text)
	def showid_process(client, msg):
		global echo_switch
		if echo_switch and msg['text'] == '/getid':
			#client.send_message(msg['chat']['id'], str(msg['chat']['id']))
			print(msg['chat']['id'])

	@app.on_message(Filters.private)
	def process_private(client, msg):
		global echo_switch
		if echo_switch:
			#client.send_message(msg['chat']['id'], '```\n{}\n```'.format(repr(msg)), parse_mode='MARKDOWN')
			print(str(msg))

	@app.on_message()
	def passfunction(_, __):
		pass

	app.start()
	process_exit()
	app.idle()

def init():
	global app

	assert isinstance(do_spec_forward, dict), 'do_spec_forward must be dict'

	# if there is any message not forward, put them to forward queue
	try:
		with open('forward_list') as fin:
			forward_list = eval(fin.read())
	except Exception:
		forward_list = []
	finally:
		for x in forward_list:
			forward_thread.queue.put_nowait(tuple(x))

	app = Client(session_name='inforward',
		api_id=config['account']['api_id'],
		api_hash=config['account']['api_hash'])

	forward_thread(app)

if __name__ == '__main__':
	init()
	main()