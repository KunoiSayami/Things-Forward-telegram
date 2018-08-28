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

def get_forward_id(msg, f=None):
	if msg.forward_from_chat: return msg.forward_from_chat.id
	if msg.forward_from: return msg.forward_from.id
	return f

def get_msg_from(msg):
	return msg.from_user.id if msg.from_user else msg.chat.id

def is_bot(msg):
	return any((
		msg.from_user and msg.from_user.is_bot,
		msg.forward_from and msg.forward_from.is_bot
		))
