# -*- coding: utf-8 -*-
# inject_pyrogram.py
# Copyright (C) 2018 Too-Naive
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
from libpy3 import Log
from pyrogram.client.types.bots import *
from pyrogram.api.types import (
    KeyboardButtonUrl, KeyboardButtonCallback,
    KeyboardButtonSwitchInline
)

class inject_inline_keyboard_button(InlineKeyboardButton):
	@staticmethod
	def read(b, *args):
		if isinstance(b, KeyboardButtonUrl):
			return InlineKeyboardButton(
				text=b.text,
				url=b.url
			)

		if isinstance(b, KeyboardButtonCallback):
			return InlineKeyboardButton(
				text=b.text,
				callback_data=b.data.decode(errors='ignore')
			)

		if isinstance(b, KeyboardButtonSwitchInline):
			if b.same_peer:
				return InlineKeyboardButton(
					text=b.text,
					switch_inline_query_current_chat=b.query
				)
			else:
				return InlineKeyboardButton(
					text=b.text,
					switch_inline_query=b.query
				)
