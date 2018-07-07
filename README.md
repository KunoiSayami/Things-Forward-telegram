# Message-Forwarding Bot

Automatically forward the target message

## Note

This version is not incompatible with previous versions.

Technical support for previous versions is no longer provided.

## Operating Environment

Python 3.4 and above is required

The following libraries are required:

- pyrogram
- pymysql

## Feature

* Support any media except voice messges
* Use MySQL engine to check if the target media is duplicated (Documents and files are not supported currently)
* Collect all the videos and pictures from the target group or channel
* Customized forwarding methods including Blacklist
* The time interval for message forwarding is customized to avoid certain risks including banned accounts
* Logging function is supported
* Add blacklists in batches (Deprecated)
* If you have the authorized password, you can send authorized code to the bot account to get the permission
* By using command lines, users can delete all the messages from a certain user in the blacklist.

## How to use

* If you don't have `api_id` and `api_hash`, obtain them from [telegram](https://my.telegram.org/apps)
* Copy `config.ini.default` to `config.ini`
* Edit forward target
* Set up MySQL database and tables
* Run `main.py`

## License

[![](https://www.gnu.org/graphics/agplv3-155x51.png)](https://www.gnu.org/licenses/agpl-3.0.txt)

Copyright (C) 2018 Too-Naive

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
