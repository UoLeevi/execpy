import importlib
import asyncio
import argparse
import textwrap

mod = None

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
    global mod
    scope = None if mod is None else mod.get_scope()
    peername = writer.get_extra_info('peername')
    message = await read_message(reader)

    while message:
        print(f'Received from {peername}:\n {message}')

        try:
            res = await exec_async(message, scope)
        except BaseException as error:
            res = f'An exception occurred: {error}'

        await write_message(writer, '' if res is None else str(res))
        message = await read_message(reader)

    print('Close the connection')
    writer.close()
    await writer.wait_closed()

async def server(host, port, module, **kwargs):
    if module:
        global mod
        mod = importlib.import_module(module)
        assert hasattr(mod, 'get_scope')

    server = await asyncio.start_server(handle_request, host, port)
    address = server.sockets[0].getsockname()

    print(f'Serving on {address}')

    async with server:
        await server.serve_forever()

async def client(host, port, lines, interactive, **kwargs):
    def input_multiline():
        multiline = line = input(f'Send:\n ')

        while line != '':
            if line in [r'\q']:
                return None

            if line in [r'\c']:
                multiline = line = input(f'Send:\n ')
                continue

            line = input(f' ')
            multiline += '\n' + line

        return multiline

    reader, writer = await asyncio.open_connection(host, port)

    if len(lines) != 0:
        message = '\n'.join(lines)
        await write_message(writer, message)
        res = await read_message(reader)
        print(f'Received:\n {res}')

    if interactive:
        message = input_multiline()
        while message:
            await write_message(writer, message)
            res = await read_message(reader)
            print(f'Received:\n {res}')
            message = input_multiline()

    print('Close the connection')
    writer.close()
    await writer.wait_closed()

def main():
    parser = argparse.ArgumentParser(prog='execpy', description='Python interpreter server and client.', add_help=False)
    parser.add_argument('-s', '--server', help='run in server mode', action='store_true')
    parser.add_argument('-c', '--client', help='run in client mode', action='store_true')
    parser.add_argument('-h', '--host', help='host to connect to', nargs='?', default='127.0.0.1')
    parser.add_argument('-p', '--port', help='listening port', type=int, nargs='?', default=0)
    parser.add_argument('-i', '--interactive', help='run client in interactive mode', action='store_true')
    parser.add_argument('-m', '--module', help='module to import which defines get_scope() function that is used to construnct the globals argument for calls to exec', nargs='?')
    parser.add_argument('lines', help='lines of Python code to execute', nargs='*')
    args = parser.parse_args()
    asyncio.run((server if args.server else client)(**vars(args)))

if __name__ == '__main__':
    main()
