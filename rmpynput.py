import logging
import struct
import math
from screeninfo import get_monitors
import threading
import time

from queue import Queue 
logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)

# evtype_sync = 0
# evtype_key = 1
e_type_abs = 3

# evcode_stylus_distance = 25
# evcode_stylus_xtilt = 26
# evcode_stylus_ytilt = 27
e_code_stylus_xpos = 1
e_code_stylus_ypos = 0
e_code_stylus_pressure = 24
e_code_stylus_present = 320
evcode_finger_xpos = 53
evcode_finger_ypos = 54
evcode_finger_touch = 57
evcode_finger_pressure = 58


# wacom digitizer dimensions
wacom_width = 15725
wacom_height = 20967
# touchscreen dimensions
finger_width = 767
finger_height = 1023


c = threading.Condition()
pen_is_active = False
from getpass import getpass
from multiprocessing import Process, Value, Queue, cpu_count, current_process
import paramiko
import paramiko.agent

logging.basicConfig(format='%(message)s')
log = logging.getLogger(__name__)

class CancellationToken:
   def __init__(self):
       self.is_active = False

   def active(self):
       self.is_active = True
   def deactive(self):
       self.is_active = False

def open_remote_device(args, file='/dev/input/event1'):
    """
    Open a remote input device via SSH.

    Args:
        args: argparse arguments
        file (str): path to the input device on the device
    Returns:
        (paramiko.ChannelFile): read-only stream of input events
    """
    log.info("Connecting to input '{}' on '{}'".format(file, args.address))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = None
    password = None

    agent = paramiko.agent.Agent()

    if args.key is not None:
        password = None
        try:
            pkey = paramiko.RSAKey.from_private_key_file(os.path.expanduser(args.key))
        except paramiko.ssh_exception.PasswordRequiredException:
            passphrase = getpass(
                "Enter passphrase for key '{}': ".format(os.path.expanduser(args.key))
            )
            pkey = paramiko.RSAKey.from_private_key_file(
                os.path.expanduser(args.key),
                password=passphrase
            )
    elif args.password:
        password = args.password
        pkey = None
    elif not agent.get_keys():
        password = getpass(
            "Password for '{}': ".format(args.address)
        )
        pkey = None

    client.connect(
        args.address,
        username='root',
        password=password,
        pkey=pkey,
        look_for_keys=False 
    )

    session = client.get_transport().open_session()

    paramiko.agent.AgentRequestHandler(session)

    # Start reading events
    _, stdout, _ = client.exec_command('cat ' + file)

    print("connected to", args.address)

    return stdout


def calculateDistance(x1,y1,x2,y2):  
     dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)  
     return dist  

# remap wacom coordinates to screen coordinates
def remap(x, y, wacom_width, wacom_height, monitor_width,
          monitor_height, mode, orientation):

    if orientation == 'bottom':
        y = wacom_height - y
    elif orientation == 'right':
        x, y = wacom_height - y, wacom_width - x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'left':
        x, y = y, x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'top':
        x = wacom_width - x

    ratio_width, ratio_height = monitor_width / wacom_width, monitor_height / wacom_height

    if mode == 'fill':
        scaling = max(ratio_width, ratio_height)
    elif mode == 'fit':
        scaling = min(ratio_width, ratio_height)
    else:
        raise NotImplementedError

    return (
        scaling * (x - (wacom_width - monitor_width / scaling) / 2),
        scaling * (y - (wacom_height - monitor_height / scaling) / 2)
    )

def remap_finger(x, y, finger_width, finger_height, monitor_width,
          monitor_height, mode, orientation):

    if orientation == 'bottom':
        y = finger_height - y
    elif orientation == 'right':
        x, y = finger_height-y, x
        finger_width, finger_height = finger_height, finger_width
    elif orientation == 'left':
        x, y = y, x
        finger_width, finger_height = finger_height, finger_width
    elif orientation == 'top':
        x = finger_width - x

    ratio_width, ratio_height = monitor_width / finger_width, monitor_height / finger_height

    if mode == 'fill':
        scaling = max(ratio_width, ratio_height)
    elif mode == 'fit':
        scaling = min(ratio_width, ratio_height)
    else:
        raise NotImplementedError

    return (
        scaling * (x - (finger_width - monitor_width / scaling) / 2),
        scaling * (y - (finger_height - monitor_height / scaling) / 2)
    )

def read_tablet(args, q):
    """Loop forever and map evdev events to mouse"""

    from pynput.mouse import Button, Controller
    global pen_is_active

    remote_device = open_remote_device(args, '/dev/input/event0')
    lifted = True
    new_x = new_y = False

    mouse = Controller()

    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', remote_device.read(16))

        if e_code == e_code_stylus_present:
            
            # c.acquire()
            pen_is_active = True if e_value == 1 else False
            q.value =pen_is_active            
        elif e_type == e_type_abs:
            
            # handle x direction
            if e_code == e_code_stylus_xpos:
                log.debug(e_value)
                x = e_value
                new_x = True

            # handle y direction
            if e_code == e_code_stylus_ypos:
                log.debug('\t{}'.format(e_value))
                y = e_value
                new_y = True

            # handle draw
            if e_code == e_code_stylus_pressure:
                log.debug('\t\t{}'.format(e_value))
                if e_value > args.threshold:
                    if lifted:
                        log.debug('PRESS')
                        lifted = False
                        mouse.press(Button.left)
                else:
                    if not lifted:
                        log.debug('RELEASE')
                        lifted = True
                        mouse.release(Button.left)


            # only move when x and y are updated for smoother mouse
            if new_x and new_y:
                mapped_x, mapped_y = remap(
                    x, y,
                    wacom_width, wacom_height,
                    monitor.width, monitor.height,
                    args.mode, args.orientation
                )
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
                new_x = new_y = False

def read_tablet_fingers(args, q):
    """Loop forever and map evdev events to mouse"""
    global pen_is_active
    import pynput
    print("read_tablet_fingers")
    remote_device = open_remote_device(args, '/dev/input/event1')
    # from pynput.mouse import Button, Controller
    # from pynput.keyboard import Key, KeyCode, Controller

    lifted = True
    new_x = new_y = False

    mouse = pynput.mouse.Controller()
    key =  pynput.keyboard.Controller()

    monitor = get_monitors()[args.monitor]
    log.debug('Chose monitor: {}'.format(monitor))

    x = 0
    y = 0
    fingers = 0
    old_y = 0
    finger_id = 0
    finger_one = (0,0)
    finger_two = (0,0)
    distance = 0
    initial_zoom = True
    read_block = 10
    UseMouse = False
    MaxFingers = 0;
    while True:
        _, _, e_type, e_code, e_value = struct.unpack('2IHHi', remote_device.read(16))

# 53 = Y
# 54 = X
# 58 = pressure
# 57 increment counter for touch. -1 when no more touch
# 47 = finger id
        # print("%d = %d" % (e_code, e_value))
        
        # c.acquire()
        # print("read_tablet_fingers",pen_is_active)
        # pen_is_active = q.get()
        # q.task_done()
        # print(q.value, bool(q.value) == False)
        # print("read_tablet_fingers",pen_is_active)
        if bool(q.value) is False:
    
            # continue
            if e_code == 47:
                # if e_value == 0:
                finger_id = e_value 
                # else:
                    # finger_id = 2
                continue
            # if e_code == 54:
                
            #     print("%s: %d = %d" % (finger_id,e_code, e_value));
            # if e_code == 3:
            #     print("%s: %d = %d" % (finger_id,e_code, e_value));
                # print("%d = %d" % (e_code, e_value));
            # if e_code == 54 or e_code == 53 or e_code == 0 or e_code == 58:
            #     continue;
            # else:
            #     continue;
            #     print("%d = %d" % (e_code, e_value));
           
            if e_type == e_type_abs:
    
                if read_block < 3:
                    read_block = read_block + 1
                # handle fingers
                if e_code == evcode_finger_touch:
                    log.debug(e_value)
                    read_block = 0
                    # finger removed
                    if e_value == -1:
                        fingers = fingers - 1
                        if fingers == 0:
                            old_y = 0
                            distance = 0
                            initial_zoom = True
                            # if MaxFingers == 1:
                            #     key.press(' ')
                            #     key.release(' ')
                            # if MaxFingers == 2:
                            #     key.press('2')
                            #     key.release('2')
                            # if MaxFingers == 3:
                            #     key.press('3')
                            #     key.release('3')
                            # if MaxFingers == 4:
                            #     key.press('4')
                            #     key.release('4')
                            # if MaxFingers == 5:
                            #     key.press('1')
                            #     key.release('1')
                        
                    # finger added
                    else:
                        fingers = fingers + 1
                        MaxFingers = fingers
                    if fingers > 2:
                        UseMouse = not UseMouse
                    continue
                
                # handle x direction
                if e_code == evcode_finger_xpos:
                    log.debug(e_value)
                    x = e_value
                    new_x = True
                    if finger_id == 0:
                        finger_one = (x, finger_one[1])
                    elif finger_id == 1:
                        finger_two = (x, finger_two[1])
    
                # handle y direction
                if e_code == evcode_finger_ypos:
                    log.debug('\t{}'.format(e_value))
                    y = e_value
                    new_y = True
                    if finger_id == 0:
                        finger_one = (finger_one[0], y)
                    elif finger_id == 1:
                        finger_two = (finger_one[0], y)
    
                # handle draw
                if e_code == e_code_stylus_pressure:
                    log.debug('\t\t{}'.format(e_value))
                    if e_value > args.threshold:
                        if lifted:
                            log.debug('PRESS')
                            lifted = False
                            mouse.press(Button.left)
                    else:
                        if not lifted:
                            log.debug('RELEASE')
                            lifted = True
                            mouse.release(Button.left)
    
    
            #     # only move when x and y are updated for smoother mouse
                if new_x or new_y:    
                    if fingers == 2:         
                        if read_block < 3:
                            continue
                        new_distance = calculateDistance(finger_one[0], finger_one[1], finger_two[0], finger_two[1])
                        # print("Distance = %f" %new_distance)
                        if distance == 0:
                            distance = new_distance
                        else:
                            diff = new_distance - distance;
                            if initial_zoom:
                                # print("Distance = %f, %f" %(new_distance,distance))
                                zoom_threshold = 200
                            else:
                                zoom_threshold = 200
                            if diff > zoom_threshold:
                                initial_zoom = False
                                distance = new_distance;
                                print("BIG")
                                key.press(pynput.keyboard.Key.ctrl)
                                key.press('+')
                                key.release('+')
                                key.press('+')
                                key.release('+')
                                key.release(pynput.keyboard.Key.ctrl)
                            elif diff < -zoom_threshold:
                                initial_zoom = False
                                distance = new_distance;
                                print("SMALL")
                                key.press(pynput.keyboard.Key.ctrl)
                                key.press('-')
                                key.release('-')
                                key.press('-')
                                key.release('-')
                                key.release(pynput.keyboard.Key.ctrl)
                        continue
                        
    
                    if fingers == 1:
                        mapped_x, mapped_y = remap_finger(
                        x, y,
                        finger_width, finger_height,
                        monitor.width, monitor.height,
                        args.mode, args.orientation)
                    #     mapped_x, mapped_y = remap_finger(
                    #     x, y,
                    #     finger_width, finger_height,
                    #     monitor.width, monitor.height,
                    #     args.mode, args.orientation
                    #     )
                        if UseMouse:
                            mouse.move(
                                monitor.x + mapped_x - mouse.position[0],
                                monitor.y + mapped_y - mouse.position[1]
                            )
                            new_x = new_y = False
                    # elif finger_id == 1:
                        
                        else:
        
                            if old_y == 0:
                                old_y = mapped_y
                                continue
                            y_displace = (mapped_y - old_y);
                            if y_displace > 50:
                                # print("Pos %d", y_displace);
                                mouse.scroll(0, 1)
                                old_y = mapped_y
                            elif y_displace < -50:
                                # print("Neg %d", y_displace);
                                mouse.scroll(0, -1)
                                old_y = mapped_y
                        