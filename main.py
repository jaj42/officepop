#!/usr/bin/env python3
import asyncio
import ssl
import base64
import exchangelib as ex


class o365:
    def __init__(self, username, password):
        if isinstance(username, bytes):
            username = username.decode()
        if isinstance(password, bytes):
            password = password.decode()
        self.credentials = ex.Credentials(username, password)
        self.config = ex.Configuration(
            server='outlook.office365.com',
            credentials=self.credentials)
        self.account = ex.Account(
            primary_smtp_address=username,
            config=self.config,
            autodiscover=False,
            access_type=ex.DELEGATE)
        self._inbox_all = []

    @property
    def inbox(self):
        return self.account.inbox

    @property
    def inbox_all(self):
        if not self._inbox_all:
            self._inbox_all = list(self.inbox.filter(is_read=False).order_by('-datetime_received'))
        return self._inbox_all

    @property
    def unread(self):
        return self.inbox.unread_count


async def handle_connection(reader, writer):
    print("Got connection")
    state = {
        'username': None,
        'addr':  writer.get_extra_info('peername')[0],
    }

    def _rwrite(message):
        if not message.endswith('\r\n'):
            message += '\r\n'
        print("{} -->\t{!r}".format(state['addr'], message))
        writer.write(message.encode())

    def _write(fmt, **kwargs):
        line = (fmt + '\r\n').format(**kwargs)
        _rwrite(line)

    _write('+OK POP3 server ready')
    await writer.drain()

    while True:
        bline = await reader.readline()

        if not bline:
            break

        if not bline.startswith(b'PASS'):  # Probs don't print passwords
            print("{} <--\t{!r}".format(state['addr'], bline))

        parts = bline.decode().rstrip().split(' ')
        command = parts[0]
        if len(parts) > 1:
            params = parts[1:]
        else:
            params = []

        if command == 'CAPA':
            _write('+OK Capability list follows')
            _write('USER')
            _write('LOGIN-DELAY 900')
            _write('EXPIRE NEVER')
            _write('UIDL')
            _write('TOP')
            _write('.')
        elif command == 'USER':
            state['username'] = params[0]
            _write('+OK')
        elif command == 'PASS':
            if state['username']:
                state['o365'] = o365(state['username'], params[0])
                _write('+OK')
            else:
                _write('-ERR Who are you?')
        elif command == 'NOOP':
            _write('+OK')
        elif command == 'QUIT':
            _write('+OK')
            break

        # Are we authenticated?
        if not 'o365' in state:
            continue

        if command == 'STAT':
            _write('+OK {count}', count=state['o365'].unread)
        elif command == 'RETR':
            msg = state['o365'].inbox_all[int(params[0]) - 1]
            _write('+OK {size} octets', size=len(msg.text_body))
            for line in msg.text_body.splitlines():
                if line.startswith('.'):
                    line = "." + line # Byte stuff the terminator
                _rwrite(line)
            _write('.')
        elif command == 'DELE':
            oid = int(params[0])
            msg = state['o365'].inbox_all[oid - 1]
            msg.is_read = True
            msg.save()
            _write('+OK message {oid} deleted', oid=oid)

        await writer.drain()

    writer.close()
    print('Server client closed for {}'.format(state['addr']))


if __name__ == '__main__':
    sc = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    sc.load_cert_chain('localhost.crt', 'localhost.key')

    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(handle_connection, '127.0.0.1', 9000, ssl=sc, loop=loop)
    server = loop.run_until_complete(coro)

    print('Serving on {}'.format(server.sockets[0].getsockname()))
    loop.run_forever()