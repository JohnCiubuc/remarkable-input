#!/bin/env python
# Evan Widloski - 2019-02-23
# Use reMarkable as mouse input

import argparse
import logging
import os
import sys
import struct
from getpass import getpass
from multiprocessing import Process, Manager, Value, Queue, cpu_count, current_process
import paramiko
import paramiko.agent
from queue import Queue 
logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)
import time

import socket
import sys


def monitorComms(args, default_address):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((default_address, 13337))
    # s.sendall('Hello, world')
    while True:
        time.sleep(1)
        data = s.recv(1024)
    # s.close()
        if data != 0:
            # print('Received', data)
            if data == b'':
                break
            
            code, message = struct.unpack('H256s', data)
            message = message[:message.find(0)].decode('utf-8')
            # if code == 1:
            #     os.system("xdg-open " + message)
            # elif code == 2:
            #     os.system(message)
                
            by = bytes("this is a test\0", "utf-8")
            by += b"0" * (256 - len(by))
            # print(by)
            var = struct.pack('H256s', 5, by)
            s.send(var)
            print("sent:")
        
def main():
    try:
        # M.join()
        #10.11.99.1
# 192.168.1.238
        default_address = '10.11.99.1'
        default_address = '192.168.1.244'
        parser = argparse.ArgumentParser(description="use reMarkable tablet as a mouse input")
        parser.add_argument('--debug', action='store_true', default=False, help="enable debug messages")
        parser.add_argument('--key', type=str, metavar='PATH', help="ssh private key")
        parser.add_argument('--password', default=None, type=str, help="ssh password")
        parser.add_argument('--address', default=default_address, type=str, help="device address")
        parser.add_argument('--mode', default='fill', choices=['fit', 'fill'], help="scale setting")
        parser.add_argument('--orientation', default='right', choices=['top', 'left', 'right', 'bottom'], help="position of tablet buttons")
        parser.add_argument('--monitor', default=0, type=int, metavar='NUM', help="monitor to output to")
        parser.add_argument('--threshold', metavar='THRESH', default=600, type=int, help="stylus pressure threshold (default 600)")
        parser.add_argument('--evdev', action='store_true', default=False, help="use evdev to support pen pressure (requires root, Linux only)")

        args = parser.parse_args()
        
        
        M = Process(target=monitorComms, args=(args, default_address))
        M.start()

        # os.system('mkdir /tmp/remarkable')
        # os.system("sshfs root@10.11.99.1:/ /tmp/remarkable")  
        # w = Watcher()
      
    # w.run()
        # remote_device_fingers = open_remote_device(args)
        # remote_device = open_remote_device(args, '/dev/input/event0')
        if args.debug:
            logging.getLogger('').setLevel(logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.info('Debugging enabled...')
        else:
            log.setLevel(logging.INFO)

        if args.evdev:
            from remarkable_mouse.evdev import create_local_device, pipe_device

            try:
                local_device = create_local_device()
                log.info("Created virtual input device '{}'".format(local_device.devnode))
            except PermissionError:
                log.error('Insufficient permissions for creating a virtual input device')
                log.error('Make sure you run this program as root')
                sys.exit(1)

            pipe_device(args, remote_device, local_device)

        else:
            from rmpynput import read_tablet, read_tablet_fingers
          
        
            d = Manager().dict()
            d['pen_is_active'] = False
            d['set_pen_active'] = True
            d['pen_exit_event'] = False
            p1 = Process(target=read_tablet, args=(args,d))
            p2 = Process(target=read_tablet_fingers, args=(args,d))
            p1.start()
            p2.start()
            p1.join()
            p2.join()
    except KeyboardInterrupt:
        pass
    except EOFError:
        pass

if __name__ == '__main__':
    main()
