
import struct
import math
import threading
import time
import os
from threading import Timer
from python_mpv_jsonipc import MPV

# Use MPV that is running and connected to /tmp/mpv-socket.
mpv = MPV(start_mpv=False, ipc_socket="/tmp/mpv-socket")

def re_init():
    # Use MPV that is running and connected to /tmp/mpv-socket.
    mpv = MPV(start_mpv=False, ipc_socket="/tmp/mpv-socket")
    
def mpv_debug():
    """
    Open a remote input device via SSH.

    Args:
        args: argparse arguments
        file (str): path to the input device on the device
    Returns:
        (paramiko.ChannelFile): read-only stream of input events
    """
    mpv.volume = 20 
