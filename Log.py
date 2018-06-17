# -*- coding: utf-8 -*-
# Log.py
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
import inspect, datetime, traceback, tempfile, time
from threading import Lock
from queue import Queue
from configparser import ConfigParser
import sys,os

'''
;config.ini
[log]
; OFF/FATAL/ERROR/WARN/INFO/DEBUG/ALL
log_level = 
; Absolute path or relative path
log_file = 
; Absolute path or relative path also (stderr/stdout)
pre_print =
'''

__currentcwdlen = len(os.getcwd()) + 1

def init_log():
	def _get_target(target):
		try:
			return {'stderr': sys.stderr, 'stdout': sys.stdout}[target]
		except KeyError:
			return open(target, 'a')
	config = ConfigParser()
	config.read('config.ini')
	return config['log']['log_level'], open(config['log']['log_file'], 'a'), _get_target(config['log']['pre_print'])

LOG_LOCK = Lock()
LOG_LEVEL_LIST = ['OFF', 'FATAL', 'ERROR', 'WARN', 'INFO', 'DEBUG', 'ALL']
LOG_LEVEL_DICT = {LOG_LEVEL_LIST[x]:x  for x in range(0, len(LOG_LEVEL_LIST))}
LOG_LEVEL_NUM_DICT = {v:k for k,v in LOG_LEVEL_DICT.items()}
LOG_LEVEL, LOG_FILE, LOG_PRE_PRINT = init_log()
LOG_LEVEL_NUM = LOG_LEVEL_DICT[LOG_LEVEL]
LOG_QUEUE = Queue()

def get_func_name():
	currentFrame = inspect.currentframe()
	outerFrame = inspect.getouterframes(currentFrame)
	returnStr = '{}.{}][{}'.format(outerFrame[3][1][__currentcwdlen:-3].replace('\\','.').replace('/','.'),
		outerFrame[3][3], outerFrame[3][2])
	del outerFrame
	del currentFrame
	return returnStr[1:] if returnStr[0] == '.' else returnStr
#@staticmethod
def reopen():
	global LOG_FILE, LOG_PRE_PRINT, LOG_LEVEL
	LOG_FILE.close()
	if LOG_PRE_PRINT not in (sys.stderr, sys.stdout):
		LOG_PRE_PRINT.close()
	LOG_LEVEL, LOG_FILE, LOG_PRE_PRINT = init_log()

#@staticmethod
def log(log_level, s, start='', end='\n', pre_print=True, need_put_queue=True):
	global LOG_LOCK, LOG_LEVEL_DICT, LOG_PRE_PRINT, LOG_QUEUE, LOG_FILE, LOG_LEVEL_NUM
	log_text = '{}[{}] [{}]\t[{}] {}{}'.format(start, time.strftime('%Y-%m-%d %H:%M:%S'),
		log_level, get_func_name(), s, end)
	if  0 < LOG_LEVEL_DICT.get(log_level, 6) < 4:
		LOG_QUEUE.put(log_text)
	LOG_LOCK.acquire()
	try:
		if pre_print and LOG_PRE_PRINT:
			LOG_PRE_PRINT.write(log_text)
			LOG_PRE_PRINT.flush()
		if LOG_LEVEL_NUM >= LOG_LEVEL_DICT.get(log_level, 6) and LOG_FILE:
			LOG_FILE.write(log_text)
			LOG_FILE.flush()
	finally:
		LOG_LOCK.release()
#@staticmethod
def fatal(fmt, *args, **kwargs):
	log('FATAL', fmt.format(*args), **kwargs)
#@staticmethod
def error(fmt, *args, **kwargs):
	log('ERROR', fmt.format(*args), **kwargs)
#@staticmethod
def warn(fmt, *args, **kwargs):
	log('WARN', fmt.format(*args), **kwargs)
#@staticmethod
def info(fmt, *args, **kwargs):
	log('INFO', fmt.format(*args), **kwargs)
#@staticmethod
def custom(level, fmt, *args, **kwargs):
	log(level, fmt.format(*args), **kwargs)
