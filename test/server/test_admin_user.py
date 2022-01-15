
import pytest
from grpclib.testing import ChannelFor
from pymapadmin.grpc.admin_grpc import UserStub
from pymapadmin.grpc.admin_pb2 import SUCCESS, FAILURE, \
    GetUserRequest, SetUserRequest, DeleteUserRequest, UserData

from pymap.admin.handlers.user import UserHandlers

from .base import TestBase


class TestMailboxHandlers(TestBase):

    admin_token = 'MDAwZWxvY2F0aW9uIAowMDEwaWRlbnRpZmllciAKMDAxNWNpZCB0eXBl' \
        'ID0gYWRtaW4KMDAyZnNpZ25hdHVyZSBTApt6-KNq85_1TeSmQyqTZjWPfHCYPY8EIG' \
        'q6NMqv4go'
    metadata = {'auth-token': admin_token}

    @pytest.fixture
    def overrides(self):
        return {'admin_key': b'testadmintoken'}

    async def test_get_user(self, backend) -> None:
        handlers = UserHandlers(backend)
        request = GetUserRequest(user='testuser')
        async with ChannelFor([handlers]) as channel:
            stub = UserStub(channel)
            response = await stub.GetUser(request, metadata=self.metadata)
        assert SUCCESS == response.result.code
        assert 'testuser' == response.username
        assert 'testpass' == response.data.password

    async def test_get_user_not_found(self, backend) -> None:
        handlers = UserHandlers(backend)
        request = GetUserRequest(user='baduser')
        async with ChannelFor([handlers]) as channel:
            stub = UserStub(channel)
            response = await stub.GetUser(request, metadata=self.metadata)
        assert FAILURE == response.result.code
        assert 'UserNotFound' == response.result.key

    async def test_set_user(self, backend, imap_server) -> None:
        handlers = UserHandlers(backend)
        data = UserData(password='newpass', params={'key': 'val'})
        request = SetUserRequest(user='testuser', data=data)
        async with ChannelFor([handlers]) as channel:
            stub = UserStub(channel)
            response = await stub.SetUser(request, metadata=self.metadata)
        assert SUCCESS == response.result.code
        assert 'testuser' == response.username

        transport = self.new_transport(imap_server)
        transport.push_login(password=b'newpass')
        transport.push_select(b'INBOX')
        transport.push_logout()
        await self.run(transport)

    async def test_delete_user(self, backend) -> None:
        handlers = UserHandlers(backend)
        request = DeleteUserRequest(user='testuser')
        async with ChannelFor([handlers]) as channel:
            stub = UserStub(channel)
            response = await stub.DeleteUser(request, metadata=self.metadata)
        assert SUCCESS == response.result.code
        assert 'testuser' == response.username

    async def test_delete_user_not_found(self, backend) -> None:
        handlers = UserHandlers(backend)
        request = DeleteUserRequest(user='baduser')
        async with ChannelFor([handlers]) as channel:
            stub = UserStub(channel)
            response = await stub.DeleteUser(request, metadata=self.metadata)
        assert FAILURE == response.result.code
        assert 'UserNotFound' == response.result.key
