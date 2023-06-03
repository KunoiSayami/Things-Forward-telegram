# -*- coding: utf-8 -*-
# configure.py
# Copyright (C) 2020-2023 KunoiSayami
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
from __future__ import annotations

from configparser import ConfigParser
from typing import Optional


class Configure:
    def __init__(self, config: ConfigParser):
        self._to_photo = config.getint("forward", "to_photo")
        self._to_video = config.getint("forward", "to_video")
        self._to_other = config.getint("forward", "to_other")
        self._to_anime = config.getint("forward", "to_anime")
        self._to_doc = config.getint("forward", "to_doc")
        self._to_gif = config.getint("forward", "to_gif")
        self._to_lowq = config.getint("forward", "to_lowq")
        self._bot_for = config.getint("forward", "bot_for")
        self._to_blacklist = config.getint("forward", "to_blacklist", fallback=None)

        self._query_photo = config.getint("forward", "query_photo", fallback=-1)
        self._query_video = config.getint("forward", "query_video", fallback=-1)
        self._query_doc = config.getint("forward", "query_doc", fallback=-1)

        self._authorized_code = config.get("account", "auth_code", fallback=None)

    @property
    def photo(self) -> int:
        return self._to_photo

    @property
    def video(self) -> int:
        return self._to_video

    @property
    def other(self) -> int:
        return self._to_other

    @property
    def anime(self) -> int:
        return self._to_anime

    @property
    def doc(self) -> int:
        return self._to_doc

    @property
    def gif(self) -> int:
        return self._to_gif

    @property
    def lowq(self) -> int:
        return self._to_lowq

    @property
    def bot_for(self) -> int:
        return self._bot_for

    @property
    def query_photo(self) -> int:
        return self._query_photo

    @property
    def query_video(self) -> int:
        return self._query_video

    @property
    def query_doc(self) -> int:
        return self._query_doc

    @property
    def bot(self) -> int:
        return self._bot_for

    @property
    def authorized_code(self) -> Optional[str]:
        return self._authorized_code

    @property
    def predefined_group_list(self) -> list[int]:
        return [
            self.photo,
            self.video,
            self.other,
            self.anime,
            self.doc,
            self.gif,
            self.lowq,
            self.bot_for,
        ]

    _instance = None

    @classmethod
    def get_instance(cls) -> Configure:
        return cls._instance  # type: ignore

    @classmethod
    def init_instance(cls, config: ConfigParser) -> Configure:
        cls._instance = cls(config)
        return cls._instance
