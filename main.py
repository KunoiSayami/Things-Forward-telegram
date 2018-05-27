# -*- coding: utf-8 -*-
# main.py
# Copyright (C) 2018 Too-Naive
#
# This module is part of libpy and is released under
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
from pyrogram import Client, Filters
from datetime import datetime
from threading import Thread
import os

global app
config = ConfigParser()
config.read('config.ini')
bypass_list = [int(x) for x in eval(config['forward']['bypass_list'])]

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
		os._exit(0)

def main():
	@app.on_message(eval(config['forward']['filter']))
	def handle_media(client, msg):
		if msg['chat']['id'] == int(config['forward']['to']) or msg['chat']['id'] in bypass_list:
			return
		client.forward_messages(int(config['forward']['to']), msg['chat']['id'], msg['message_id'], True)
		print('[{}] forward from {} (id:{})'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
			msg['chat']['title'], msg['chat']['id']))
	
	@app.on_message(Filters.command("e"))
	def add_Except(Client, msg):
		if msg['chat']['id'] != int(config['account']['owner']):
			return
		global bypass_list
		bypass_list.append(int(msg['text'][3:]))
		bypass_list = list(set(bypass_list))
		config['forward']['bypass_list'] = repr(bypass_list)
		print('[{}] add except id:{}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
			msg['text'][3:]))

	@app.on_message()
	def passfunction(_, __):
		pass
	
	app.start()
	process_exit()
	app.idle()

def init():
	global app
	#print(config['account']['forward_to'])
	app = Client(session_name='inforward',
		api_id=config['account']['api_id'],
		api_hash=config['account']['api_hash'])

if __name__ == '__main__':
	init()
	main()