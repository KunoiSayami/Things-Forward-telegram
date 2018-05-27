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


global app
config = ConfigParser()
bypass_list = ()

def main():
	@app.on_message(eval(config['forward']['filter']))
	def handle_media(client, msg):
		if msg['chat']['id'] == int(config['forward']['to']) or msg['chat']['id'] in bypass_list:
			return
		client.forward_messages(int(config['forward']['to']), msg['chat']['id'], msg['message_id'], True)
		print('[{}] forward from {} (id:{})'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
			msg['chat']['title'], msg['chat']['id']))
	@app.on_message()
	def passfunction(_, __):
		pass
	app.start()
	app.idle()

def init():
	global app
	config.read('config.ini')
	#print(config['account']['forward_to'])
	app = Client(session_name='inforward',
		api_id=config['account']['api_id'],
		api_hash=config['account']['api_hash'])
	bypass_list = eval(config['forward']['bypass_list'])

if __name__ == '__main__':
	init()
	main()