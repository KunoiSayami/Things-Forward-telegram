# -*- coding: utf-8 -*-
# getitem.py
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
def get_msg_key(msg, key1, key2, f=None):
	try:
		return msg[key1][key2]
	except:
		return f

def get_the_fucking_id(msg):
	r = get_the_fucking_id_ex(msg)
	return r if r is not None else msg['chat']['id']

def get_the_fucking_id_ex(msg, f=None):
	try:
		return msg['forward_from_chat']['id']
	except (TypeError, KeyError):
		pass
	try:
		return msg['forward_from']['id']
	except (TypeError, KeyError):
		return f

def get_msg_from(msg):
	try:
		return msg['from_user']['id']
	except (TypeError, KeyError):
		return msg['chat']['id']

def is_bot(msg):
	return any((get_msg_key(msg, 'from_user', 'is_bot'),
		get_msg_key(msg, 'forward_from', 'is_bot')))
