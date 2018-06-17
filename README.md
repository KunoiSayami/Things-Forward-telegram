# Forward message bot

Forward message what you need.

## Notice

This version is not incompatible with previous versions.

## Runtime environment

In principle, need python 3.4.x interpreter

The following libraries are required:

- pyrogram

## Feature

* Full support any media
* Using MySQL engine to check file is duplicated (document and file is not support now)
* Can query entire group or channel
* Blacklist and special forwrad support
* Using forward system to control forward action, custom time interval
* Log to file supported

## How to use

* Copy `config.ini.default` to `config.ini`
* Parse api id and api hash from [telegram](https://my.telegram.org/apps)
* Edit forward target
* Run `main.py`

## License

[![](https://www.gnu.org/graphics/agplv3-155x51.png)](https://www.gnu.org/licenses/agpl-3.0.txt)

Copyright (C) 2018 Too-Naive

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

### This program also uses the following open source programs

Pyrogram, Copyright (C) 2017-2018 Dan Tès <https://github.com/delivrance>

Licensed under the terms of the GNU Lesser General Public License v3 or later (LGPLv3+)