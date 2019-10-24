import asyncio
import textwrap
from base64 import b64decode

async def write_message(writer, message):
    message = (message or '').encode()
    length = len(message)
    writer.write(length.to_bytes(8, 'big'))
    writer.write(message)
    await writer.drain()

async def read_message(reader):
    length = await reader.read(8)
    message = await reader.read(int.from_bytes(length, 'big'))
    return message.decode()

async def exec_async(code, scope=None):
    source = f'async def __f():\n{textwrap.indent(code, "    ")}'
    scope = dict() if scope is None else scope.copy()
    exec(source, scope)
    return await scope['__f']()

async def handle_request(reader, writer):
    loop = asyncio.get_running_loop()
    get_scope = getattr(loop, '_get_scope')
    quiet = getattr(loop, '_quiet')

    if not quiet:
        peername = writer.get_extra_info('peername')

    message = await read_message(reader)

    while message:
        if not quiet:
            print(f'Received from {peername}:\n {message}')

        if message in [r'\q']:
            setattr(loop, '_quit', True)
            break

        scope = get_scope()

        try:
            res = await exec_async(message, scope)
        except BaseException as error:
            res = f'An exception occurred: {error}'

        await write_message(writer, '' if res is None else str(res))
        message = await read_message(reader)

    if not quiet:
        print(f'Close the connection to {peername}')

    writer.close()
    await writer.wait_closed()

async def run_server(port=0, host='127.0.0.1', module=None, scope=None, quiet=False, exit=False, **kwargs):
    if module:
        import importlib
        mod = importlib.import_module(module)
        assert hasattr(mod, 'get_scope')
        get_scope = mod.get_scope
    else:
        scope = scope or {}
        get_scope = lambda: scope

    loop = asyncio.get_running_loop()
    setattr(loop, '_get_scope', get_scope)
    setattr(loop, '_quiet', quiet)
    setattr(loop, '_quit', False)

    server = await asyncio.start_server(handle_request, host, port)
    address = server.sockets[0].getsockname()

    if not quiet:
        print(f'Serving on {address}')

    async with server:
        while not exit or not getattr(loop, '_quit'):
            await asyncio.sleep(0.5)

async def connect(port, host='127.0.0.1', lines=None, interactive=False, quiet=False, base64=False, exit=False, **kwargs):
    def input_multiline():
        multiline = line = input(f'Send:\n')

        while line != '':
            if line in [r'\q']:
                return None

            if line in [r'\c']:
                multiline = line = input(f'Send:\n')
                continue

            line = input()
            multiline += '\n' + line

        return multiline

    reader, writer = await asyncio.open_connection(host, port)

    if lines and len(lines) != 0:
        if base64:
            lines = [b64decode(line).decode() for line in lines]

        message = '\n'.join(lines)
        await write_message(writer, message)
        res = await read_message(reader)

        if not quiet:
            print('Received:')

        print(res)

    if interactive:
        message = input_multiline()
        while message:
            await write_message(writer, message)
            res = await read_message(reader)

            if not quiet:
                print('Received:')

            print(res)
            message = input_multiline()

    if exit:
        await write_message(writer, r'\q')

    if not quiet:
        print('Close the connection')

    writer.close()
    await writer.wait_closed()

def main():
    import argparse
    parser = argparse.ArgumentParser(prog='execpy', description='Python interpreter server and client.', add_help=False)
    parser.add_argument('-s', '--server', help='run in server mode', action='store_true')
    parser.add_argument('-c', '--client', help='run in client mode', action='store_true')
    parser.add_argument('-h', '--host', help='host to connect to', nargs='?', default='127.0.0.1')
    parser.add_argument('-p', '--port', help='listening port', type=int, nargs='?', default=0)
    parser.add_argument('-i', '--interactive', help='run client in interactive mode', action='store_true')
    parser.add_argument('-m', '--module', help='module to import which defines get_scope() function that is used to construnct the globals argument for calls to exec', nargs='?')
    parser.add_argument('-b', '--base64', help='interpret lines of code argument as base64 encoded utf-8 string', action='store_true')
    parser.add_argument('-q', '--quiet', help='do not print any info messages', action='store_true')
    parser.add_argument('-e', '--exit', help='allow clients to stop the server', action='store_true')
    parser.add_argument('lines', help='lines of Python code to execute', nargs='*')
    args = parser.parse_args()
    asyncio.run((run_server if args.server else connect)(**vars(args)))

if __name__ == '__main__':
    main()
