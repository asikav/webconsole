#!/usr/bin/env python

import threading
import asyncio
import websockets
import argparse
import os
import sys
import re

import http.server

http_port = 8000
shells = {}


def http_server(server_class=http.server.HTTPServer, handler_class=http.server.SimpleHTTPRequestHandler):
    print("serving at port: {}".format(http_port))
    server_address = ('', http_port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

def shell_start(shell_i):
    pid, fd = os.forkpty()

    if pid == 0:
        os.execv('/bin/bash', ['-i'])
        sys.exit(0)
    else:
        shells[shell_i] = {'pid': pid, 'fd': fd, 'rdata': asyncio.Queue(), 'history': bytearray(b'')}
        asyncio.get_event_loop().add_reader(fd, shell_data_avail, shell_i)

def shell_data_avail(shell_i):
    # print ('shell[{}] rdata'.format(shell_i))
    rdata = os.read(shells[shell_i]['fd'], 1024)
    if len(rdata) > 0:
        # shells[shell_i]['history'].extend(rdata)
        # shells[shell_i]['history'] = shells[shell_i]['history'][-1024*1024:]
        shells[shell_i]['rdata'].put_nowait(rdata)
    else:
        asyncio.get_event_loop().remove_reader(shells[shell_i]['fd'])
        shells[shell_i]['pid'] = 0
        shells[shell_i]['fd'] = 0

async def websocket_recv(websocket, shell_i):
    while True:
        rdata = await websocket.recv()
        os.write(shells[shell_i]['fd'], rdata.encode())
        os.fsync(shells[shell_i]['fd'])

async def websocket_send(websocket, shell_i):
    await websocket.send(bytes(shells[shell_i]['history']))
    while True:
        rdata = await shells[shell_i]['rdata'].get()
        await websocket.send(rdata)

async def websocket_handler(websocket, path):
    print (path)
    m = re.match('/+terminal/([0-9]+)', path)
    if not m:
        return
    shell_i = int(m.group(1))
    if shell_i not in shells:
        shell_start(shell_i)
    consumer_task = asyncio.ensure_future(
        websocket_recv(websocket, shell_i))
    producer_task = asyncio.ensure_future(
        websocket_send(websocket, shell_i))
    done, pending = await asyncio.wait(
        [consumer_task, producer_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

start_server = websockets.serve(websocket_handler, 'localhost', 8765)



asyncio.get_event_loop().run_until_complete(start_server)
threading.Thread(target=http_server).start()
# asyncio.get_event_loop().run_until_complete(asyncio.get_event_loop().create_task(http_server))
# asyncio.get_event_loop().run_until_complete(http_server)
asyncio.get_event_loop().run_forever()
