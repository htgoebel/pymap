
import os.path
from argparse import Namespace, ArgumentDefaultsHelpFormatter
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Mapping, Dict, TypeVar, Type

from pkg_resources import resource_listdir, resource_stream
from pysasl import AuthenticationCredentials

from pymap.config import IMAPConfig
from pymap.exceptions import InvalidAuth
from pymap.interfaces.backend import BackendInterface
from pymap.parsing.specials.flag import Flag, Recent
from pymap.server import IMAPServer

from .mailbox import Message, MailboxData, MailboxSet
from ..session import BaseSession

__all__ = ['DictBackend', 'Config', 'Session']

_SessionT = TypeVar('_SessionT', bound='Session')


class DictBackend(IMAPServer, BackendInterface):
    """Defines a backend that uses an in-memory dictionary for example usage
    and integration testing.

    """

    @classmethod
    def add_subparser(cls, subparsers) -> None:
        parser = subparsers.add_parser(
            'dict', help='in-memory backend',
            formatter_class=ArgumentDefaultsHelpFormatter)
        parser.add_argument('-d', '--demo-data', action='store_true',
                            help='load initial demo data')
        parser.add_argument('-u', '--demo-user', default='demouser',
                            metavar='VAL', help='demo user ID')
        parser.add_argument('-p', '--demo-password', default='demopass',
                            metavar='VAL', help='demo user password')

    @classmethod
    async def init(cls, args: Namespace) -> 'DictBackend':
        return cls(Session.login, Config.from_args(args))


class Config(IMAPConfig):
    """The config implementation for the dict backend.

    Args:
        args: The command-line arguments.
        demo_data: Load the demo data, used by integration tests.

    """

    def __init__(self, args: Namespace, demo_data: bool, **extra: Any) -> None:
        super().__init__(args, **extra)
        self.demo_data = demo_data
        self.set_cache: Dict[str, MailboxSet] = {}

    @property
    def demo_user(self) -> str:
        """Used by the default :meth:`~Session.get_password` implementation
        to retrieve the ``--demo-user`` command-line argument, which defaults
        to ``demouser``.

        """
        return self.args.demo_user

    @property
    def demo_password(self) -> str:
        """Used by the default :meth:`~Session.get_password` implementation
        to retrieve the ``--demo-password`` command-line argument, which
        defaults to ``demopass``.

        """
        return self.args.demo_password

    @classmethod
    def parse_args(cls, args: Namespace, **extra: Any) -> Mapping[str, Any]:
        return super().parse_args(args, demo_data=args.demo_data, **extra)


class Session(BaseSession[Message]):
    """The session implementation for the dict backend."""

    resource = __name__

    def __init__(self, config: Config, mailbox_set: MailboxSet) -> None:
        super().__init__()
        self._config = config
        self._mailbox_set = mailbox_set

    @property
    def config(self) -> Config:
        return self._config

    @property
    def mailbox_set(self) -> MailboxSet:
        return self._mailbox_set

    @classmethod
    async def login(cls: Type[_SessionT],
                    credentials: AuthenticationCredentials,
                    config: Config) -> _SessionT:
        """Checks the given credentials for a valid login and returns a new
        session. The mailbox data is shared between concurrent and future
        sessions, but only for the lifetime of the process.

        """
        user = credentials.authcid
        password = await cls.get_password(config, user)
        if not password or not credentials.check_secret(password):
            raise InvalidAuth()
        mailbox_set = config.set_cache.get(user)
        if not mailbox_set:
            mailbox_set = MailboxSet()
            if config.demo_data:
                await cls._load_demo(mailbox_set)
            config.set_cache[user] = mailbox_set
        return cls(config, mailbox_set)

    @classmethod
    async def get_password(cls, config: Config, user: str) -> str:
        """If the given user ID exists, return its expected password. Override
        this method to implement custom login logic.

        Args:
            config: The dict config object.
            user: The expected user ID.

        Raises:
            InvalidAuth: The user ID was not valid.

        """
        expected_user: str = config.demo_user
        expected_password: str = config.demo_password
        if user == expected_user:
            return expected_password
        raise InvalidAuth()

    @classmethod
    async def _load_demo(cls, mailbox_set: MailboxSet) -> None:
        inbox = await mailbox_set.get_mailbox('INBOX')
        await cls._load_demo_mailbox('INBOX', inbox)
        mbx_names = sorted(resource_listdir(cls.resource, 'demo'))
        for name in mbx_names:
            if name != 'INBOX':
                mbx = await mailbox_set.add_mailbox(name)
                await cls._load_demo_mailbox(name, mbx)

    @classmethod
    async def _load_demo_mailbox(cls, name: str, mbx: MailboxData) -> None:
        path = os.path.join('demo', name)
        msg_names = sorted(resource_listdir(cls.resource, path))
        for msg_name in msg_names:
            if msg_name == '.readonly':
                mbx._readonly = True
                continue
            elif msg_name.startswith('.'):
                continue
            msg_path = os.path.join(path, msg_name)
            message_stream = resource_stream(cls.resource, msg_path)
            with closing(message_stream):
                flags_line = message_stream.readline()
                msg_timestamp = float(message_stream.readline())
                msg_data = message_stream.read()
                msg_dt = datetime.fromtimestamp(msg_timestamp, timezone.utc)
                msg_flags = {Flag(flag) for flag in flags_line.split()}
                if Recent in msg_flags:
                    msg_flags.remove(Recent)
                    msg_recent = True
                else:
                    msg_recent = False
                msg = Message.parse(0, msg_data, msg_flags, msg_dt)
            await mbx.add(msg, msg_recent)