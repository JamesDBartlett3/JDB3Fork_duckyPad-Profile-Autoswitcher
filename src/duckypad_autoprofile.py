import os
import time
from tkinter import *
from tkinter import messagebox
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()
import urllib.request
import tkinter.scrolledtext as ScrolledText
import traceback
import json
import webbrowser
import sys
import threading
from hid_common import *
import get_window
import check_update
import remote_link
from platformdirs import *
import subprocess
import argparse
import pystray
from PIL import Image, ImageDraw
if sys.platform == 'win32':
    import winreg

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APP_NAME = "duckyPad Autoswitcher"

def get_startup_enabled():
    """Check if launch at startup is enabled in Windows registry"""
    if sys.platform != 'win32':
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, STARTUP_APP_NAME)
        winreg.CloseKey(key)
        return True
    except WindowsError:
        return False

def set_startup_enabled(enable, start_minimized=False):
    """Enable or disable launch at startup in Windows registry"""
    if sys.platform != 'win32':
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            # Get the path to the executable
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            # Add --minimized flag only if start_minimized is enabled
            if start_minimized:
                winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}" --minimized')
            else:
                winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, STARTUP_APP_NAME)
            except WindowsError:
                pass
        winreg.CloseKey(key)
    except WindowsError as e:
        print(f"Failed to modify startup registry: {e}")

def open_url_safe(url):
    if 'linux' in sys.platform.lower() and os.geteuid() == 0:
        print(f"\nOpen this URL manually ------>   {url}\n")
        try:
            from tkinter import messagebox
            messagebox.showinfo(title="Info",message="Cannot open webbrowser as root.\n\nPlease click the link printed in your terminal manually.")
            return
        except Exception as e:
            print(e)
            return
    webbrowser.open(url)

def open_mac_linux_instruction():
    open_url_safe('https://dekunukem.github.io/duckyPad-Pro/doc/linux_macos_notes.html')

def ensure_dir(dir_path):
    os.makedirs(dir_path, exist_ok=1)

# Parse command-line arguments
parser = argparse.ArgumentParser(description='duckyPad Profile Autoswitcher')
parser.add_argument('--minimized', action='store_true', help='Start minimized to system tray')
args = parser.parse_args()

# Global variable for system tray
tray_icon = None

# xhost +;sudo python3 duckypad_autoprofile.py 

appname = 'duckypad_autoswitcher'
appauthor = 'dekuNukem'
save_path = user_data_dir(appname, appauthor, roaming=True)

ensure_dir(save_path)
save_filename = os.path.join(save_path, 'config.txt')

default_button_color = 'SystemButtonFace'
if 'linux' in sys.platform:
    default_button_color = 'grey'

myh = hid.device()

"""
0.0.8 2023 02 20
faster refresh rate 33ms
added HID busy check

0.1.0 2023 10 12
added queue to prevent dropping requests when duckypad is busy

0.2.0
updated window refresh method from pull request?
seems a bit laggy tho

0.3.0
quick edit to work on duckypad pro
switch profile by name instead of number
changed timing to make it less laggy, still feels roughly the same tho

0.4.0
Nov 21 2024
Now detects both duckyPad and duckyPad Pro
supports switching profiles by name or number
UI tweaks

0.4.1
Nov 23 2024
fixed wrong FW update URL

0.4.2
Dec 26 2024
Fixed UI button size for macOS
Updated macOS info URL
Added DUCKYPAD_UI_SCALE environment variable
Exits gracefully instead of crashing when not in sudo on macOS

0.4.3
Feb 23 2025
Cached HID path

1.0.0
Apr 4 2025
Multi duckyPad support
Switch by name only
double click to edit rule

1.0.1
June 16 2025
Relaxed overly strict text-entry checks

1.0.2
July 5 2025
Fixed retry not working when duckypad is busy

1.0.3
July 30 2025
Added timeout in HID read

1.1.0
Nov 16 2025
Sets RTC automatically
Better handling of switching to profiles that don't exist

1.1.1
Nov 27 2025
Added system tray functionality with --minimized option
Dec 25 2025
Bumped up max supported fw version for DSVM2

1.2.0
Jan 17 2026
HID commands all little endian
new PGV dump and write

1.2.1
Jan 28 2025
Fixed keyboard input not working when autoswitching is active on linux
Fixed url open not working when in linux sudo
Added retry delay when duckypad is busy
Fixed SSL certificate not found error

1.2.2
Apr 15 2026
Fixed prev/next profile buttons hanging UI when duckyPad is busy
Fixed connect button showing "not found" when duckyPad is busy
"""

UI_SCALE = float(os.getenv("DUCKYPAD_UI_SCALE", default=1))

def scaled_size(size: int) -> int:
    return int(size * UI_SCALE)

THIS_VERSION_NUMBER = '1.2.2'
MAIN_WINDOW_WIDTH = scaled_size(640)
MAIN_WINDOW_HEIGHT = scaled_size(720)
PADDING = 10

THIS_DUCKYPAD = dp_type()

MIN_DUCKYPAD_PRO_FIRMWARE_VERSION = "3.0.0"
MAX_DUCKYPAD_PRO_FIRMWARE_VERSION = "3.10.0"
MIN_DUCKYPAD_2020_FIRMWARE_VERSION = "3.0.0"
MAX_DUCKYPAD_2020_FIRMWARE_VERSION = "3.10.0"

print("\n\n--------------------------")
print("\n\nWelcome to duckyPad Autoswitcher!\n")
print("This window prints debug information.")

dp_model_lookup = {DP_MODEL_OG_DUCKYPAD:"duckyPad(2020)", DP_MODEL_DUCKYPAD_PRO:"duckyPad Pro"}

def ask_user_to_select_a_duckypad(dp_info_list):
    dp_select_window = Toplevel(root)
    dp_select_window.title("Select-a-duckyPad")
    dp_select_window.geometry(f"{scaled_size(360)}x{scaled_size(320)}")
    dp_select_window.resizable(width=FALSE, height=FALSE)
    dp_select_window.grab_set()

    dp_select_text_label = Label(master=dp_select_window, text="Multiple duckyPads detected!\nDouble click to select one")
    dp_select_text_label.place(x=scaled_size(90), y=scaled_size(10))

    dp_select_column_label = Label(master=dp_select_window, text=f"{'Model':<16}{'Serial':<10}Firmware", font='TkFixedFont')
    dp_select_column_label.place(x=scaled_size(50), y=scaled_size(50))
    selected_duckypad = IntVar()
    selected_duckypad.set(-1)

    def make_dp_info_str(dp_info_dict):
        try:
            dp_model_str = dp_model_lookup[dp_info_dict['dp_model']]
        except:
            dp_model_str = "Unknown"
        return f" {dp_model_str:<18}{dp_info_dict['serial']:<12}{dp_info_dict['fw_version']}"

    def dp_select_button_click(wtf=None):
        this_selection = dp_select_listbox.curselection()
        if len(this_selection) == 0:
            return
        selected_duckypad.set(this_selection[0])
        dp_select_window.destroy()

    dp_select_var = StringVar(value=[make_dp_info_str(x) for x in dp_info_list])
    dp_select_listbox = Listbox(dp_select_window, listvariable=dp_select_var, height=16, exportselection=0, font='TkFixedFont', selectmode='single')
    dp_select_listbox.place(x=scaled_size(20), y=scaled_size(70), width=scaled_size(320), height=scaled_size(200))
    dp_select_listbox.bind('<Double-Button>', dp_select_button_click)

    dp_select_button = Button(dp_select_window, text="Select", command=dp_select_button_click)
    dp_select_button.place(x=scaled_size(20), y=scaled_size(280), width=scaled_size(320))

    root.wait_window(dp_select_window)
    return selected_duckypad.get()

def duckypad_connect():
    all_dp_info_list = scan_duckypads()
    if all_dp_info_list is None:
        if 'darwin' in sys.platform and messagebox.askokcancel("Info", "duckyPad detected, but I need additional permissions!\n\nClick OK for instructions"):
            open_mac_linux_instruction()
        elif 'linux' in sys.platform:
            messagebox.showinfo("Info", "duckyPad detected, but please run me in sudo!")
        return False

    if all_dp_info_list == DP_SCAN_BUSY:
        messagebox.showerror("Error", "duckyPad is busy!\nEnsure no script is running,\nand not in settings menu.")
        return False

    if len(all_dp_info_list) == 0:
        connection_info_str.set("duckyPad not found")
        return False

    selected_index = -1
    if len(all_dp_info_list) == 1:
        selected_index = 0
    else:
        selected_index = ask_user_to_select_a_duckypad(all_dp_info_list)
    if selected_index == -1:
        return False
    
    user_selected_dp = all_dp_info_list[selected_index]
    print("user selected:", user_selected_dp)

    if dpp_is_fw_compatible(user_selected_dp) is False:
        return False
    if open_hid_path(user_selected_dp, myh) is False:
        return False
    
    duckypad_sync_rtc(myh)
    time.sleep(0.1)
    THIS_DUCKYPAD.device_type = user_selected_dp['dp_model']
    THIS_DUCKYPAD.info_dict = user_selected_dp
    connection_info_str.set(f"Connected!      Model: {dp_model_lookup.get(THIS_DUCKYPAD.device_type)}      Serial: {THIS_DUCKYPAD.info_dict.get('serial')}      Firmware: {THIS_DUCKYPAD.info_dict.get('fw_version')}")
    if 'linux' in sys.platform:
        myh.close()
    return True

def open_hid_path(dp_info_dict, hid_obj):
    hid_obj.close()
    try:
        hid_obj.open_path(dp_info_dict['hid_path'])
        return True
    except Exception as e:
        if "already open" in str(e).lower():
            return True
    return False

def update_windows(textbox):
    windows_str = 'Application' + ' '*14 + "Window Title\n"
    windows_str += "-------------------------------------\n"
    for item in get_window.get_list_of_all_windows():
        gap = 25 - len(item[0])
        windows_str += str(item[0]) + ' '*gap + str(item[1]) + '\n'
    textbox.config(state=NORMAL)
    textbox.delete(1.0, "end")
    textbox.insert(1.0, windows_str)
    textbox.config(state=DISABLED)

DP_WRITE_OK = 0
DP_WRITE_FAIL = 1
DP_WRITE_BUSY = 2

HID_COMMAND_GOTO_PROFILE_BY_NUMBER = 1
HID_COMMAND_PREV_PROFILE = 2
HID_COMMAND_NEXT_PROFILE = 3
HID_COMMAND_GOTO_PROFILE_BY_NAME = 23

def duckypad_write_with_retry(data_buf):
    try:
        # NEW: On Linux, open the path before writing
        if 'linux' in sys.platform:
            try:
                myh.open_path(THIS_DUCKYPAD.info_dict['hid_path'])
            except Exception as e:
                raise e # Force jump to the "SECOND TRY" block if open fails

        dp_response = hid_txrx(data_buf, myh)

        # NEW: On Linux, close immediately after writing
        if 'linux' in sys.platform:
            myh.close()

        if len(dp_response) != PC_TO_DUCKYPAD_HID_BUF_SIZE:
            return DP_WRITE_FAIL
        if dp_response[2] == 0:
            return DP_WRITE_OK
        if dp_response[2] == 2:
            return DP_WRITE_BUSY
        return DP_WRITE_FAIL
    except Exception as e:
        print("DP write first try:", e)
        # Clean up if Linux left it open during crash
        if 'linux' in sys.platform:
            try: myh.close()
            except: pass

    try:
        print("SECOND TRY")
        if duckypad_connect() is False:
            return DP_WRITE_FAIL
        
        # NEW: On Linux, open again (duckypad_connect closes it on exit)
        if 'linux' in sys.platform:
            myh.open_path(THIS_DUCKYPAD.info_dict['hid_path'])

        dp_response = hid_txrx(data_buf, myh)

        # NEW: On Linux, close immediately
        if 'linux' in sys.platform:
            myh.close()

        if len(dp_response) != PC_TO_DUCKYPAD_HID_BUF_SIZE:
            return DP_WRITE_FAIL
        if dp_response[2] == 0:
            return DP_WRITE_OK
        if dp_response[2] == 2:
            return DP_WRITE_BUSY
        return DP_WRITE_FAIL
    except Exception as e:
        print(e)
        if 'linux' in sys.platform:
            try:
                myh.close()
            except:
                pass

    print("FAILED")
    return DP_WRITE_FAIL
    
def _prof_click_worker(hid_command):
    buffff = get_empty_pc_to_duckypad_buf()
    buffff[2] = hid_command
    this_result = duckypad_write_with_retry(buffff)
    if this_result == DP_WRITE_BUSY:
        root.after(0, lambda: messagebox.showerror("Error", "duckyPad is busy!\nEnsure no script is running,\nand not in settings menu."))
    else:
        root.after(0, lambda: update_banner_text(this_result))

def prev_prof_click():
    threading.Thread(target=_prof_click_worker, args=(HID_COMMAND_PREV_PROFILE,), daemon=True).start()

def next_prof_click():
    threading.Thread(target=_prof_click_worker, args=(HID_COMMAND_NEXT_PROFILE,), daemon=True).start()

# System tray functionality
def create_tray_image():
    """Create a simple icon for the system tray"""
    try:
        # Get the base path - works for both development and PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            base_path = sys._MEIPASS
        else:
            # Running as script
            base_path = os.path.dirname(__file__)
        
        # Try to load the application icon
        icon_path = os.path.join(base_path, '_icon.ico')
        if os.path.exists(icon_path):
            return Image.open(icon_path)
    except Exception as e:
        print(f"Could not load icon file: {e}")
    
    # Fallback: create a simple programmatic icon
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), 'blue')
    dc = ImageDraw.Draw(image)
    dc.rectangle(
        [(width // 4, height // 4), (width * 3 // 4, height * 3 // 4)],
        fill='white'
    )
    return image

def show_window():
    """Show the main window and bring it to front"""
    root.deiconify()
    root.lift()
    root.focus_force()

def hide_window():
    """Hide the main window"""
    root.withdraw()

def quit_app(icon=None, item=None):
    """Quit the application"""
    global tray_icon
    if tray_icon is not None:
        tray_icon.stop()
    root.quit()

def on_closing():
    """Handle window close event - minimize to tray or quit based on setting"""
    if config_dict.get('close_to_tray', True):
        hide_window()
    else:
        quit_app()

def setup_tray_icon():
    """Setup the system tray icon"""
    global tray_icon
    icon_image = create_tray_image()
    menu = pystray.Menu(
        pystray.MenuItem('Show', show_window, default=True),
        pystray.MenuItem('Quit', quit_app)
    )
    tray_icon = pystray.Icon("duckyPad", icon_image, "duckyPad Autoswitcher", menu)
    
def run_tray_icon():
    """Run the system tray icon in a separate thread"""
    if tray_icon is not None:
        tray_icon.run()

root = Tk()
root.title("duckyPad autoswitcher " + THIS_VERSION_NUMBER)
root.geometry(f"{MAIN_WINDOW_WIDTH}x{MAIN_WINDOW_HEIGHT}")
root.resizable(width=FALSE, height=FALSE)
root.protocol("WM_DELETE_WINDOW", on_closing)

# --------------------

connection_info_str = StringVar()
connection_info_str.set("<--- Press Connect button")
connection_info_lf = LabelFrame(root, text="Connection", width=scaled_size(620), height=scaled_size(60))
connection_info_lf.place(x=scaled_size(PADDING), y=scaled_size(0)) 
connection_info_label = Label(master=connection_info_lf, textvariable=connection_info_str)
connection_info_label.place(x=scaled_size(110), y=scaled_size(5))

connection_button = Button(connection_info_lf, text="Connect", command=duckypad_connect)
connection_button.place(x=scaled_size(PADDING), y=scaled_size(5), width=scaled_size(90))

quit_button = Button(connection_info_lf, text="Quit", command=quit_app)
quit_button.place(x=scaled_size(540), y=scaled_size(5), width=scaled_size(65))

# --------------------

def open_user_manual():
    open_url_safe('https://github.com/dekuNukem/duckyPad-profile-autoswitcher/blob/master/README.md#user-manual')

def open_discord():
    open_url_safe("https://discord.gg/4sJCBx5")

def refresh_autoswitch():
    if config_dict['autoswitch_enabled']:
        autoswitch_status_var.set("Profile Autoswitch: ACTIVE     Click me to stop")
        autoswitch_status_label.config(fg='white', bg='green', cursor="hand2")
    else:
        autoswitch_status_var.set("Profile Autoswitch: STOPPED    Click me to start")
        autoswitch_status_label.config(fg='white', bg='orange red', cursor="hand2")

def toggle_autoswitch(whatever):
    config_dict['autoswitch_enabled'] = not config_dict['autoswitch_enabled']
    save_config()
    refresh_autoswitch()
    
def open_save_folder():
    messagebox.showinfo("Info", "* Copy config.txt elsewhere to make a backup!\n\n* Close the app then copy it back to restore.")
    if 'darwin' in sys.platform:
        subprocess.Popen(["open", save_path])
    elif 'linux' in sys.platform:
        subprocess.Popen(["xdg-open", save_path])
    else:
        open_url_safe(save_path)

dashboard_lf = LabelFrame(root, text="Dashboard", width=scaled_size(620), height=scaled_size(95))
dashboard_lf.place(x=scaled_size(PADDING), y=scaled_size(60)) 
prev_profile_button = Button(dashboard_lf, text="Prev Profile", command=prev_prof_click)
prev_profile_button.place(x=scaled_size(410), y=scaled_size(5), width=scaled_size(90))

next_profile_button = Button(dashboard_lf, text="Next Profile", command=next_prof_click)
next_profile_button.place(x=scaled_size(510), y=scaled_size(5), width=scaled_size(90))

user_manual_button = Button(dashboard_lf, text="User Manual", command=open_user_manual)
user_manual_button.place(x=scaled_size(PADDING), y=scaled_size(5), width=scaled_size(90))

discord_button = Button(dashboard_lf, text="Discord", command=open_discord)
discord_button.place(x=scaled_size(110), y=scaled_size(5), width=scaled_size(90))

discord_button = Button(dashboard_lf, text="Backup", command=open_save_folder)
discord_button.place(x=scaled_size(210), y=scaled_size(5), width=scaled_size(90))

remote_button = Button(dashboard_lf, text="Remote...", command=lambda: create_remote_window())
remote_button.place(x=scaled_size(310), y=scaled_size(5), width=scaled_size(90))

remote_status_var = StringVar()
remote_status_var.set("Remote (RDP/VNC): off")
remote_status_label = Label(master=dashboard_lf, textvariable=remote_status_var)
remote_status_label.place(x=scaled_size(10), y=scaled_size(65))

autoswitch_status_var = StringVar()
autoswitch_status_label = Label(master=dashboard_lf, textvariable=autoswitch_status_var, font='TkFixedFont', cursor="hand2")
autoswitch_status_label.place(x=scaled_size(10), y=scaled_size(40))
autoswitch_status_label.bind("<Button-1>", toggle_autoswitch)

# --------------------

def on_close_to_tray_change():
    config_dict['close_to_tray'] = close_to_tray_var.get()
    print(f"Setting changed: close_to_tray = {config_dict['close_to_tray']}")
    save_config()

def on_start_minimized_change():
    config_dict['start_minimized'] = start_minimized_var.get()
    print(f"Setting changed: start_minimized = {config_dict['start_minimized']}")
    save_config()
    # Update registry if launch at startup is enabled
    if launch_at_startup_var.get():
        print(f"Updating startup registry with start_minimized = {config_dict['start_minimized']}")
        set_startup_enabled(True, start_minimized_var.get())

def on_launch_at_startup_change():
    enable = launch_at_startup_var.get()
    print(f"Setting changed: launch_at_startup = {enable}")
    set_startup_enabled(enable, start_minimized_var.get())

settings_lf = LabelFrame(root, text="Settings", width=scaled_size(620), height=scaled_size(55))
settings_lf.place(x=scaled_size(PADDING), y=scaled_size(155))

close_to_tray_var = BooleanVar(value=True)
close_to_tray_checkbox = Checkbutton(settings_lf, text="Close to tray", variable=close_to_tray_var, command=on_close_to_tray_change)
close_to_tray_checkbox.place(x=scaled_size(10), y=scaled_size(5))

start_minimized_var = BooleanVar(value=False)
start_minimized_checkbox = Checkbutton(settings_lf, text="Start minimized to tray", variable=start_minimized_var, command=on_start_minimized_change)
start_minimized_checkbox.place(x=scaled_size(150), y=scaled_size(5))

launch_at_startup_var = BooleanVar(value=False)
if sys.platform == 'win32':
    launch_at_startup_checkbox = Checkbutton(settings_lf, text="Launch at startup", variable=launch_at_startup_var, command=on_launch_at_startup_change)
    launch_at_startup_checkbox.place(x=scaled_size(350), y=scaled_size(5))

# --------------------

current_app_name_var = StringVar()
current_app_name_var.set("Current app name:")

current_window_title_var = StringVar()
current_window_title_var.set("Current Window Title:")

PC_TO_DUCKYPAD_HID_BUF_SIZE = 64

def duckypad_goto_profile_by_name(profile_name):
    profile_name = str(profile_name)[:32]
    buffff = get_empty_pc_to_duckypad_buf()
    buffff[2] = HID_COMMAND_GOTO_PROFILE_BY_NAME
    for index, item in enumerate(profile_name):
        buffff[index+3] = ord(item)
    return duckypad_write_with_retry(buffff)

profile_switch_queue = []
last_switch = None

def update_banner_text(switch_result):
    if switch_result == DP_WRITE_OK:
        connection_info_label.place(x=scaled_size(110), y=scaled_size(5))
        connection_info_str.set(f"Connected!      Model: {dp_model_lookup.get(THIS_DUCKYPAD.device_type)}      Serial: {THIS_DUCKYPAD.info_dict.get('serial')}      Firmware: {THIS_DUCKYPAD.info_dict.get('fw_version')}")
    elif switch_result == DP_WRITE_BUSY:
        pass
        # print("DUCKYPAD IS BUSY! Retrying later")
    elif switch_result == DP_WRITE_FAIL:
        connection_info_label.place(x=scaled_size(130), y=scaled_size(5))
        connection_info_str.set(f"duckyPad Disappeared!")
    root.update()

def t1_worker():
    global last_switch
    while(1):
        time.sleep(0.033)
        if len(profile_switch_queue) == 0:
            continue
        queue_head = profile_switch_queue[0]
        result = duckypad_goto_profile_by_name(queue_head)
        update_banner_text(result)
        if result == DP_WRITE_OK:
            print("switch success")
            profile_switch_queue.pop(0)
        elif result == DP_WRITE_BUSY:
            print("duckyPad is busy! Retrying later")
            time.sleep(0.5)
        elif result == DP_WRITE_FAIL:
            print("duckyPad not found")
            profile_switch_queue.clear()
        last_switch = queue_head
            
def switch_queue_add(profile_target_name):
    global last_switch
    if profile_target_name is None or len(profile_target_name) == 0:
        return
    if profile_target_name == last_switch:
        return
    if len(profile_switch_queue) > 0 and profile_switch_queue[-1] == profile_target_name:
        return
    profile_switch_queue.append(profile_target_name)

WINDOW_CHECK_FREQUENCY_MS = 100

remote_sender = None
remote_receiver = None
remote_status_base = "Remote (RDP/VNC): off"

def remote_mode():
    return config_dict.get('remote_mode', remote_link.REMOTE_MODE_OFF)

def remote_stop():
    global remote_sender, remote_receiver
    if remote_sender is not None:
        remote_sender.stop()
        remote_sender = None
    if remote_receiver is not None:
        remote_receiver.stop()
        remote_receiver = None

def remote_apply_config():
    """(Re)starts the remote sender/receiver according to config. Returns an error message, or None on success."""
    global remote_sender, remote_receiver, remote_status_base
    remote_stop()
    mode = remote_mode()
    secret = config_dict.get('remote_secret', '')
    try:
        if mode == remote_link.REMOTE_MODE_SENDER:
            port = remote_link.parse_port(config_dict.get('remote_port', remote_link.DEFAULT_PORT))
            host = str(config_dict.get('remote_host', '')).strip()
            if len(host) == 0:
                raise ValueError("Destination address is empty")
            remote_sender = remote_link.RemoteSender(host, port, secret)
            remote_sender.start()
            remote_status_base = f"Remote (RDP/VNC): SENDING profile to {host}:{port}"
        elif mode == remote_link.REMOTE_MODE_RECEIVER:
            port = remote_link.parse_port(config_dict.get('remote_port', remote_link.DEFAULT_PORT))
            address = str(config_dict.get('remote_listen_address', remote_link.DEFAULT_LISTEN_ADDRESS)).strip()
            remote_receiver = remote_link.RemoteReceiver(address, port, config_dict.get('remote_allowlist', ''), secret)
            remote_receiver.start()
            remote_status_base = f"Remote (RDP/VNC): LISTENING on {address}:{port}"
        else:
            remote_status_base = "Remote (RDP/VNC): off"
    except Exception as e:
        remote_stop()
        remote_status_base = "Remote (RDP/VNC): ERROR, see Remote... settings"
        print("remote_apply_config:", e)
        remote_status_var.set(remote_status_base)
        return str(e)
    remote_status_var.set(remote_status_base)
    return None

def get_remote_profile_to_apply(app_name, window_title):
    """Profile requested by the remote instance, only while the RDP/VNC viewer is the active local window."""
    if remote_receiver is None:
        return None
    if not remote_link.viewer_matches(app_name, window_title, config_dict.get('remote_viewer_app', ''), config_dict.get('remote_viewer_title', '')):
        return None
    return remote_receiver.get_profile()

def update_remote_status(applied_remote_profile):
    new_status = remote_status_base
    if applied_remote_profile is not None:
        new_status += f"  [applying remote profile: {applied_remote_profile}]"
    if remote_status_var.get() != new_status:
        remote_status_var.set(new_status)

last_remote_window = None

def update_current_app_and_title():
    global last_remote_window

    root.after(WINDOW_CHECK_FREQUENCY_MS, update_current_app_and_title)

    app_name, window_title = get_window.get_active_window()
    current_app_name_var.set("App name:      " + str(app_name))
    current_window_title_var.set("Window title:  " + str(window_title))

    if rule_window is not None and rule_window.winfo_exists():
        return
    focus_changed = (app_name, window_title) != last_remote_window
    last_remote_window = (app_name, window_title)
    if config_dict['autoswitch_enabled'] is False:
        if remote_sender is not None:
            remote_sender.set_profile('', focus_changed)
        return

    highlight_index = None
    remote_profile = get_remote_profile_to_apply(app_name, window_title)
    if remote_profile is not None:
        switch_queue_add(remote_profile)
    else:
        matched_profile = None
        for index, item in enumerate(config_dict['rules_list']):
            if item['enabled'] is False:
                continue
            app_name_condition = True
            if len(item['app_name']) > 0:
                app_name_condition = item['app_name'].lower() in app_name.lower()
            window_title_condition = True
            if len(item['window_title']) > 0:
                window_title_condition = item['window_title'].lower() in window_title.lower()
            if app_name_condition and window_title_condition:
                matched_profile = '' if item['switch_to'] is None else str(item['switch_to'])
                highlight_index = index
                break
        if remote_sender is not None:
            remote_sender.set_profile(matched_profile, focus_changed)
        elif matched_profile is not None:
            switch_queue_add(matched_profile)
    update_remote_status(remote_profile)

    for index, item in enumerate(config_dict['rules_list']):
        if index == highlight_index:
            profile_lstbox.itemconfig(index, fg='white', bg='green')
        else:
            profile_lstbox.itemconfig(index, fg='black', bg='white')

# ----------------

app_name_entrybox = None
window_name_entrybox = None
switch_to_entrybox = None
config_dict = {}
config_dict['rules_list'] = []
config_dict['autoswitch_enabled'] = True
config_dict['close_to_tray'] = False
config_dict['start_minimized'] = False
config_dict['remote_mode'] = remote_link.REMOTE_MODE_OFF
config_dict['remote_host'] = ''
config_dict['remote_port'] = remote_link.DEFAULT_PORT
config_dict['remote_listen_address'] = remote_link.DEFAULT_LISTEN_ADDRESS
config_dict['remote_allowlist'] = ''
config_dict['remote_viewer_app'] = ''
config_dict['remote_viewer_title'] = ''
config_dict['remote_secret'] = ''

def clean_input(str_input):
    return str_input.strip()

def make_rule_str(rule_dict):
    rule_str = ''
    if rule_dict['enabled']:
        rule_str += "  * "
    else:
        rule_str += "    "
    if len(rule_dict['app_name']) > 0:
        rule_str += "     " + rule_dict['app_name']
    else:
        rule_str += "     " + "[Any]"

    next_item = rule_dict['window_title']
    if len(next_item) <= 0:
        next_item = "[Any]"
    gap = 26 - len(rule_str)
    rule_str += ' '*gap + next_item

    gap = 50 - len(rule_str)
    rule_str += ' '*gap + str(rule_dict['switch_to'])

    return rule_str

def update_rule_list_display():
    profile_var.set([make_rule_str(x) for x in config_dict['rules_list']])

def save_config():
    try:
        ensure_dir(save_path)
        with open(save_filename, 'w', encoding='utf8') as save_file:
            save_file.write(json.dumps(config_dict, sort_keys=True))
    except Exception as e:
        messagebox.showerror("Error", "Save failed!\n\n"+str(traceback.format_exc()))

def save_rule_click(window, this_rule):
    if this_rule is None:
        rule_dict = {}
        rule_dict["app_name"] = clean_input(app_name_entrybox.get())
        rule_dict["window_title"] = clean_input(window_name_entrybox.get())
        rule_dict["switch_to"] = clean_input(switch_to_entrybox.get())
        rule_dict["enabled"] = True
        if rule_dict not in config_dict['rules_list']:
            config_dict['rules_list'].append(rule_dict)
            update_rule_list_display()
            save_config()
            window.destroy()
    elif this_rule is not None:
        this_rule["app_name"] = clean_input(app_name_entrybox.get())
        this_rule["window_title"] = clean_input(window_name_entrybox.get())
        this_rule["switch_to"] = clean_input(switch_to_entrybox.get())
        update_rule_list_display()
        save_config()
        window.destroy()

rule_window = None
RULE_WINDOW_WIDTH = scaled_size(640)
RULE_WINDOW_HEIGHT = scaled_size(510)

def create_rule_window(existing_rule=None):
    global rule_window
    global app_name_entrybox
    global window_name_entrybox
    global switch_to_entrybox
    rule_window = Toplevel(root)
    rule_window.title("Edit rules")
    rule_window.geometry(f"{RULE_WINDOW_WIDTH}x{RULE_WINDOW_HEIGHT}")
    rule_window.resizable(width=FALSE, height=FALSE)
    rule_window.grab_set()

    rule_edit_lf = LabelFrame(rule_window, text="Rules", width=scaled_size(620), height=scaled_size(130))
    rule_edit_lf.place(x=scaled_size(10), y=scaled_size(5))

    app_name_label = Label(master=rule_window, text="IF App Name Contains:")
    app_name_label.place(x=scaled_size(20), y=scaled_size(25))
    app_name_entrybox = Entry(rule_window)
    app_name_entrybox.place(x=scaled_size(250), y=scaled_size(25), width=scaled_size(200))
    
    window_name_label = Label(master=rule_window, text="AND Window Title Contains:")
    window_name_label.place(x=scaled_size(20), y=scaled_size(50))
    window_name_entrybox = Entry(rule_window)
    window_name_entrybox.place(x=scaled_size(250), y=scaled_size(50), width=scaled_size(200))

    switch_to_label = Label(master=rule_window, text="THEN Jump to Profile (Case Sensitive):")
    switch_to_label.place(x=scaled_size(20), y=scaled_size(75))
    switch_to_entrybox = Entry(rule_window)
    switch_to_entrybox.place(x=scaled_size(250), y=scaled_size(75), width=scaled_size(200))

    if existing_rule is not None:
        app_name_entrybox.insert(0, existing_rule["app_name"])
        window_name_entrybox.insert(0, existing_rule["window_title"])
        if existing_rule["switch_to"] is None:
            switch_to_entrybox.insert(0, "")
        else:
            switch_to_entrybox.insert(0, str(existing_rule["switch_to"]))

    rule_done_button = Button(rule_edit_lf, text="Save", command=lambda:save_rule_click(rule_window, existing_rule))
    rule_done_button.place(x=scaled_size(30), y=scaled_size(80), width=scaled_size(550))

    match_all_label = Label(master=rule_window, text="(leave blank to match all)")
    match_all_label.place(x=scaled_size(470), y=scaled_size(25))
    match_all_label2 = Label(master=rule_window, text="(leave blank to match all)")
    match_all_label2.place(x=scaled_size(470), y=scaled_size(50))
    match_all_label3 = Label(master=rule_window, text="(leave blank for no action)")
    match_all_label3.place(x=scaled_size(470), y=scaled_size(75))

    current_window_lf = LabelFrame(rule_window, text="Active window", width=scaled_size(620), height=scaled_size(80))
    current_window_lf.place(x=scaled_size(PADDING), y=scaled_size(140))

    current_app_name_label = Label(master=current_window_lf, textvariable=current_app_name_var, font='TkFixedFont')
    current_app_name_label.place(x=scaled_size(10), y=scaled_size(5))
    current_window_title_label = Label(master=current_window_lf, textvariable=current_window_title_var, font='TkFixedFont')
    current_window_title_label.place(x=scaled_size(10), y=scaled_size(30))

    window_list_lf = LabelFrame(rule_window, text="All windows", width=scaled_size(620), height=scaled_size(270))
    window_list_lf.place(x=scaled_size(PADDING), y=scaled_size(195+30)) 
    window_list_fresh_button = Button(window_list_lf, text="Refresh", command=lambda:update_windows(windows_list_text_area))
    window_list_fresh_button.place(x=scaled_size(30), y=scaled_size(220), width=scaled_size(550))
    windows_list_text_area = ScrolledText.ScrolledText(window_list_lf, wrap='none', width=scaled_size(73), height=scaled_size(13))
    windows_list_text_area.place(x=scaled_size(5), y=scaled_size(5))
    root.update()
    update_windows(windows_list_text_area)

def delete_rule_click():
    selection = profile_lstbox.curselection()
    if len(selection) <= 0:
        return
    config_dict['rules_list'].pop(selection[0])
    update_rule_list_display()
    save_config()

def edit_rule_click(dummy=None):
    selection = profile_lstbox.curselection()
    if len(selection) <= 0:
        return
    create_rule_window(config_dict['rules_list'][selection[0]])

def toggle_rule_click():
    selection = profile_lstbox.curselection()
    if len(selection) <= 0:
        return
    config_dict['rules_list'][selection[0]]['enabled'] = not config_dict['rules_list'][selection[0]]['enabled']
    update_rule_list_display()
    save_config()

def rule_shift_up():
    selection = profile_lstbox.curselection()
    if len(selection) <= 0 or selection[0] == 0:
        return
    source = selection[0]
    destination = selection[0] - 1
    config_dict['rules_list'][destination], config_dict['rules_list'][source] = config_dict['rules_list'][source], config_dict['rules_list'][destination]
    update_rule_list_display()
    profile_lstbox.selection_clear(0, len(config_dict['rules_list']))
    profile_lstbox.selection_set(destination)
    update_rule_list_display()
    save_config()

def rule_shift_down():
    selection = profile_lstbox.curselection()
    if len(selection) <= 0 or selection[0] == len(config_dict['rules_list']) - 1:
        return
    source = selection[0]
    destination = selection[0] + 1
    config_dict['rules_list'][destination], config_dict['rules_list'][source] = config_dict['rules_list'][source], config_dict['rules_list'][destination]
    update_rule_list_display()
    profile_lstbox.selection_clear(0, len(config_dict['rules_list']))
    profile_lstbox.selection_set(destination)
    update_rule_list_display()
    save_config()

remote_window = None
REMOTE_WINDOW_WIDTH = scaled_size(560)
REMOTE_WINDOW_HEIGHT = scaled_size(440)

def save_remote_click(window, fields):
    mode = fields['mode'].get()
    new_config = {'remote_mode': mode, 'remote_secret': fields['secret'].get().strip()}
    try:
        if mode == remote_link.REMOTE_MODE_SENDER:
            new_config['remote_host'] = fields['host'].get().strip()
            if len(new_config['remote_host']) == 0:
                raise ValueError("Please enter the address of the local computer.")
            new_config['remote_port'] = remote_link.parse_port(fields['sender_port'].get())
        elif mode == remote_link.REMOTE_MODE_RECEIVER:
            new_config['remote_port'] = remote_link.parse_port(fields['receiver_port'].get())
            new_config['remote_listen_address'] = fields['listen_address'].get().strip() or remote_link.DEFAULT_LISTEN_ADDRESS
            new_config['remote_allowlist'] = fields['allowlist'].get().strip()
            remote_link.parse_allowlist(new_config['remote_allowlist'])
            new_config['remote_viewer_app'] = clean_input(fields['viewer_app'].get())
            new_config['remote_viewer_title'] = clean_input(fields['viewer_title'].get())
            if len(new_config['remote_viewer_app']) == 0 and len(new_config['remote_viewer_title']) == 0:
                raise ValueError("Please enter the app name and/or window title of your RDP/VNC viewer.")
    except ValueError as e:
        messagebox.showerror("Error", f"Invalid settings:\n\n{e}", parent=window)
        return
    config_dict.update(new_config)
    save_config()
    error = remote_apply_config()
    if error is not None:
        messagebox.showerror("Error", f"Could not start remote mode:\n\n{error}", parent=window)
        return
    if mode == remote_link.REMOTE_MODE_SENDER:
        connection_info_str.set("Remote sender mode: duckyPad not used on this computer")
    elif THIS_DUCKYPAD.info_dict is None:
        duckypad_connect()
    window.destroy()

def create_remote_window():
    global remote_window
    if remote_window is not None and remote_window.winfo_exists():
        remote_window.lift()
        return
    remote_window = Toplevel(root)
    remote_window.title("Remote (RDP/VNC)")
    remote_window.geometry(f"{REMOTE_WINDOW_WIDTH}x{REMOTE_WINDOW_HEIGHT}")
    remote_window.resizable(width=FALSE, height=FALSE)
    remote_window.grab_set()

    fields = {}
    fields['mode'] = StringVar(value=remote_mode())
    Radiobutton(remote_window, text="Off", variable=fields['mode'], value=remote_link.REMOTE_MODE_OFF).place(x=scaled_size(20), y=scaled_size(5))
    Radiobutton(remote_window, text="Sender: this app runs INSIDE the RDP/VNC session", variable=fields['mode'], value=remote_link.REMOTE_MODE_SENDER).place(x=scaled_size(20), y=scaled_size(30))
    Radiobutton(remote_window, text="Receiver: the duckyPad is connected to THIS computer", variable=fields['mode'], value=remote_link.REMOTE_MODE_RECEIVER).place(x=scaled_size(20), y=scaled_size(55))

    sender_lf = LabelFrame(remote_window, text="Sender", width=scaled_size(540), height=scaled_size(60))
    sender_lf.place(x=scaled_size(10), y=scaled_size(90))
    Label(sender_lf, text="Send to address:").place(x=scaled_size(10), y=scaled_size(5))
    fields['host'] = Entry(sender_lf)
    fields['host'].place(x=scaled_size(150), y=scaled_size(5), width=scaled_size(200))
    fields['host'].insert(0, str(config_dict.get('remote_host', '')))
    Label(sender_lf, text="Port:").place(x=scaled_size(370), y=scaled_size(5))
    fields['sender_port'] = Entry(sender_lf)
    fields['sender_port'].place(x=scaled_size(420), y=scaled_size(5), width=scaled_size(80))
    fields['sender_port'].insert(0, str(config_dict.get('remote_port', remote_link.DEFAULT_PORT)))

    receiver_lf = LabelFrame(remote_window, text="Receiver", width=scaled_size(540), height=scaled_size(180))
    receiver_lf.place(x=scaled_size(10), y=scaled_size(160))
    Label(receiver_lf, text="Listen address:").place(x=scaled_size(10), y=scaled_size(5))
    fields['listen_address'] = Entry(receiver_lf)
    fields['listen_address'].place(x=scaled_size(150), y=scaled_size(5), width=scaled_size(200))
    fields['listen_address'].insert(0, str(config_dict.get('remote_listen_address', remote_link.DEFAULT_LISTEN_ADDRESS)))
    Label(receiver_lf, text="Port:").place(x=scaled_size(370), y=scaled_size(5))
    fields['receiver_port'] = Entry(receiver_lf)
    fields['receiver_port'].place(x=scaled_size(420), y=scaled_size(5), width=scaled_size(80))
    fields['receiver_port'].insert(0, str(config_dict.get('remote_port', remote_link.DEFAULT_PORT)))
    Label(receiver_lf, text="Allowed senders:").place(x=scaled_size(10), y=scaled_size(35))
    fields['allowlist'] = Entry(receiver_lf)
    fields['allowlist'].place(x=scaled_size(150), y=scaled_size(35), width=scaled_size(200))
    fields['allowlist'].insert(0, str(config_dict.get('remote_allowlist', '')))
    Label(receiver_lf, text="IPs or CIDRs, blank = any").place(x=scaled_size(360), y=scaled_size(35))
    Label(receiver_lf, text="Viewer app name contains:").place(x=scaled_size(10), y=scaled_size(65))
    fields['viewer_app'] = Entry(receiver_lf)
    fields['viewer_app'].place(x=scaled_size(240), y=scaled_size(65), width=scaled_size(110))
    fields['viewer_app'].insert(0, str(config_dict.get('remote_viewer_app', '')))
    Label(receiver_lf, text="Viewer window title contains:").place(x=scaled_size(10), y=scaled_size(95))
    fields['viewer_title'] = Entry(receiver_lf)
    fields['viewer_title'].place(x=scaled_size(240), y=scaled_size(95), width=scaled_size(110))
    fields['viewer_title'].insert(0, str(config_dict.get('remote_viewer_title', '')))
    Label(receiver_lf, text="e.g. mstsc, vncviewer").place(x=scaled_size(360), y=scaled_size(65))
    Label(receiver_lf, text="Remote profiles apply only while the viewer is the active window.").place(x=scaled_size(10), y=scaled_size(130))

    Label(remote_window, text="Shared secret (optional, same on both ends):").place(x=scaled_size(20), y=scaled_size(355))
    fields['secret'] = Entry(remote_window, show='*')
    fields['secret'].place(x=scaled_size(380), y=scaled_size(355), width=scaled_size(160))
    fields['secret'].insert(0, str(config_dict.get('remote_secret', '')))

    Button(remote_window, text="Save", command=lambda: save_remote_click(remote_window, fields)).place(x=scaled_size(10), y=scaled_size(390), width=scaled_size(540))

rules_lf = LabelFrame(root, text="Autoswitch rules", width=scaled_size(620), height=scaled_size(410))
rules_lf.place(x=scaled_size(PADDING), y=scaled_size(215)) 

profile_var = StringVar()
profile_lstbox = Listbox(rules_lf, listvariable=profile_var, height=scaled_size(20), exportselection=0)
profile_lstbox.place(x=scaled_size(PADDING), y=scaled_size(30), width=scaled_size(500))
profile_lstbox.config(font='TkFixedFont')
# profile_lstbox.bind('<FocusOut>', lambda e: profile_lstbox.selection_clear(0, END))
profile_lstbox.bind('<Double-Button>', edit_rule_click)

rule_header_label = Label(master=rules_lf, text="Enabled   App              Window                 Profile", font='TkFixedFont')
rule_header_label.place(x=scaled_size(5), y=scaled_size(5))

new_rule_button = Button(rules_lf, text="New rule...", command=create_rule_window)
new_rule_button.place(x=scaled_size(520), y=scaled_size(30), width=scaled_size(90))

edit_rule_button = Button(rules_lf, text="Edit rule...", command=edit_rule_click)
edit_rule_button.place(x=scaled_size(520), y=scaled_size(70), width=scaled_size(90))

move_up_button = Button(rules_lf, text="Move up", command=rule_shift_up)
move_up_button.place(x=scaled_size(520), y=scaled_size(150), width=scaled_size(90))

toggle_rule_button = Button(rules_lf, text="On/Off", command=toggle_rule_click)
toggle_rule_button.place(x=scaled_size(520), y=scaled_size(190), width=scaled_size(90))

move_down_button = Button(rules_lf, text="Move down", command=rule_shift_down)
move_down_button.place(x=scaled_size(520), y=scaled_size(230), width=scaled_size(90))

delete_rule_button = Button(rules_lf, text="Delete rule", command=delete_rule_click)
delete_rule_button.place(x=scaled_size(520), y=scaled_size(300), width=scaled_size(90))

try:
    with open(save_filename) as json_file:
        temp = json.load(json_file)
        if isinstance(temp, list):
            config_dict['rules_list'] = temp
        elif isinstance(temp, dict):
            # Merge loaded config with defaults to handle missing keys
            loaded_config = temp
            for key in loaded_config:
                config_dict[key] = loaded_config[key]
        else:
            raise ValueError("not a valid config file")
    update_rule_list_display()
except Exception as e:
    print(traceback.format_exc())

# Apply loaded settings to checkboxes
close_to_tray_var.set(config_dict.get('close_to_tray', True))
start_minimized_var.set(config_dict.get('start_minimized', False))
launch_at_startup_var.set(get_startup_enabled())

refresh_autoswitch()

# ------------------

def fw_update_click(event, dp_info_dict):
    if dp_info_dict['dp_model'] == DP_MODEL_OG_DUCKYPAD:
        open_url_safe("https://github.com/dekuNukem/duckyPad/blob/master/firmware_updates_and_version_history.md")
    elif dp_info_dict['dp_model'] == DP_MODEL_DUCKYPAD_PRO:
        open_url_safe('https://dekunukem.github.io/duckyPad-Pro/doc/fw_update.html')

def app_update_click(event=None):
    open_url_safe('https://github.com/dekuNukem/duckyPad-profile-autoswitcher/releases/latest')

def print_fw_update_label(dp_info_dict):
    this_version = dp_info_dict["fw_version"]
    fw_result = check_update.get_firmware_update_status(dp_info_dict)
    if fw_result == 0:
        dp_fw_update_label.config(text=f'Firmware ({this_version}): Up to date', fg='black', bg=default_button_color)
        dp_fw_update_label.unbind("<Button-1>")
    elif fw_result == 1:
        dp_fw_update_label.config(text=f'Firmware ({this_version}): Update available! Click me!', fg='black', bg='orange', cursor="hand2")
        dp_fw_update_label.bind("<Button-1>", lambda event: fw_update_click(event, dp_info_dict))
    else:
        dp_fw_update_label.config(text='Firmware: Unknown', fg='black', bg=default_button_color)
        dp_fw_update_label.unbind("<Button-1>")
    return this_version

FW_OK = 0
FW_TOO_LOW = 1
FW_TOO_HIGH = 2
FW_UNKNOWN = 3

def is_dp_fw_valid(dp_info_dict):
    current_fw_str = dp_info_dict["fw_version"]
    
    if dp_info_dict['dp_model'] == DP_MODEL_DUCKYPAD_PRO:
        min_fw = MIN_DUCKYPAD_PRO_FIRMWARE_VERSION
        max_fw = MAX_DUCKYPAD_PRO_FIRMWARE_VERSION
    elif dp_info_dict['dp_model'] == DP_MODEL_OG_DUCKYPAD:
        min_fw = MIN_DUCKYPAD_2020_FIRMWARE_VERSION
        max_fw = MAX_DUCKYPAD_2020_FIRMWARE_VERSION
    else:
        return FW_UNKNOWN
    
    if check_update.versiontuple(current_fw_str) < check_update.versiontuple(min_fw):
        if messagebox.askokcancel("Info", f"duckyPad firmware too old!\n\nCurrent: {current_fw_str}\nSupported: Between {min_fw} and {max_fw}.\n\nSee how to update it?"):
            fw_update_click(None, dp_info_dict)
        return FW_TOO_LOW
    if check_update.versiontuple(current_fw_str) > check_update.versiontuple(max_fw):
        if messagebox.askokcancel("Info", f"duckyPad firmware too new!\n\nCurrent: {current_fw_str}\nSupported: Between {min_fw} and {max_fw}.\n\nSee how to update this app?"):
            app_update_click()
        return FW_TOO_HIGH
    return FW_OK

def dpp_is_fw_compatible(dp_info_dict):
    print_fw_update_label(dp_info_dict)
    if is_dp_fw_valid(dp_info_dict) != FW_OK:
        return False
    return True

updates_lf = LabelFrame(root, text="Updates", width=scaled_size(620), height=scaled_size(80))
updates_lf.place(x=scaled_size(PADDING), y=scaled_size(625))

pc_app_update_label = Label(master=updates_lf)
pc_app_update_label.place(x=scaled_size(5), y=scaled_size(5))
update_stats = check_update.get_pc_app_update_status(THIS_VERSION_NUMBER)

if update_stats == 0:
    pc_app_update_label.config(text='This app (' + str(THIS_VERSION_NUMBER) + '): Up to date', fg='black', bg=default_button_color)
    pc_app_update_label.unbind("<Button-1>")
elif update_stats == 1:
    pc_app_update_label.config(text='This app (' + str(THIS_VERSION_NUMBER) + '): Update available! Click me!', fg='black', bg='orange', cursor="hand2")
    pc_app_update_label.bind("<Button-1>", app_update_click)
else:
    pc_app_update_label.config(text='This app (' + str(THIS_VERSION_NUMBER) + '): Unknown', fg='black', bg=default_button_color)
    pc_app_update_label.unbind("<Button-1>")

dp_fw_update_label = Label(master=updates_lf, text="duckyPad firmware: Unknown")
dp_fw_update_label.place(x=scaled_size(5), y=scaled_size(30))

# ------------------

root.update()
remote_apply_config()
if remote_mode() != remote_link.REMOTE_MODE_SENDER:
    duckypad_connect()
else:
    connection_info_str.set("Remote sender mode: duckyPad not used on this computer")

def contains_jump_by_number():
    for item in config_dict['rules_list']:
        try:
            int(item['switch_to'])
            return True
        except:
            continue
    return False

t1 = threading.Thread(target=t1_worker, daemon=True)
t1.start()

if contains_jump_by_number():
    messagebox.showinfo("Info", "Profiles are now referenced BY NAME (case sensitive) instead of number.\n\nMake sure to update the rules.")

# Setup system tray icon
setup_tray_icon()
tray_thread = threading.Thread(target=run_tray_icon, daemon=True)
tray_thread.start()

# Start minimized if requested via command line or config setting
if args.minimized or config_dict.get('start_minimized', False):
    root.withdraw()  # Hide window on startup
else:
    root.deiconify()  # Show window normally

RTC_SYNC_FREQ_SECONDS = 30

def sync_rtc():
    root.after(RTC_SYNC_FREQ_SECONDS*1000, sync_rtc)
    if remote_mode() == remote_link.REMOTE_MODE_SENDER:
        return
    try:
        if THIS_DUCKYPAD.info_dict is not None:
            # NEW: On Linux, open before sync
            if 'linux' in sys.platform:
                myh.open_path(THIS_DUCKYPAD.info_dict['hid_path'])
            
            duckypad_sync_rtc(myh)
            
            # NEW: On Linux, close after sync
            if 'linux' in sys.platform:
                myh.close()
        return
    except Exception as e:
        print("sync_rtc:", e)
        if 'linux' in sys.platform:
            try:
                myh.close()
            except:
                pass
            
    update_banner_text(DP_WRITE_FAIL)
    if duckypad_connect():
        update_banner_text(DP_WRITE_OK)
root.after(WINDOW_CHECK_FREQUENCY_MS, update_current_app_and_title)
root.after(RTC_SYNC_FREQ_SECONDS*1000, sync_rtc)
root.mainloop()
