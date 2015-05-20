# Copyright (c) 2015 Ian C. Good
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import asyncio
import email
from datetime import datetime, timezone

from pymap.parsing.primitives import *  # NOQA
from pymap.parsing.specials import DateTime
from pymap.interfaces import MessageInterface

__all__ = ['Message']


class Message(MessageInterface):

    def __init__(self, seq, uid, flags, data):
        super().__init__(seq, uid)
        self.flags = flags
        self.data = email.message_from_bytes(data)

    @asyncio.coroutine
    def get_message(self, full=True):
        return self.data

    @asyncio.coroutine
    def fetch_internal_date(self):
        return DateTime(datetime.now(timezone.utc))

    @asyncio.coroutine
    def fetch_flags(self):
        return List(self.flags)
