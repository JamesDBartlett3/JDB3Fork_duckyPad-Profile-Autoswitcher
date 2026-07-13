"""
duckyPad HID example: HID read AND write

https://github.com/dekuNukem/duckyPad-profile-autoswitcher/blob/master/HID_details.md
"""

import hid
import time

PC_TO_DUCKYPAD_HID_BUF_SIZE = 64
DUCKYPAD_TO_PC_HID_BUF_SIZE = 64

h = hid.device()

duckypad_pid = 0xd11c
duckypad_pro_pid = 0xd11d
DUCKYPAD_VID = 0x0483
DUCKYPAD_COUNTED_BUF_USAGE_ID = 58

def get_path_by_pid(my_pid):
    path_dict = {}
    for device_dict in hid.enumerate():
        if device_dict['vendor_id'] != DUCKYPAD_VID:
            continue
        if device_dict['product_id'] != my_pid:
            continue
        if device_dict['usage'] != DUCKYPAD_COUNTED_BUF_USAGE_ID:
            continue
        return device_dict['path']
    return None

def get_duckypad_path():
    dpp_path = get_path_by_pid(duckypad_pro_pid)
    if dpp_path is not None:
        return dpp_path
    dp_path = get_path_by_pid(duckypad_pid)
    if dp_path is not None:
        return dp_path
    return None

def duckypad_hid_write(hid_buf_64b):
	if len(hid_buf_64b) != PC_TO_DUCKYPAD_HID_BUF_SIZE:
		raise ValueError('PC-to-duckyPad buffer wrong size, should be exactly 64 Bytes')
	duckypad_path = get_duckypad_path()
	if duckypad_path is None:
		raise OSError('duckyPad Not Found!')
	h.open_path(duckypad_path)
	h.write(hid_buf_64b)
	result = h.read(DUCKYPAD_TO_PC_HID_BUF_SIZE)
	h.close()
	return result

pc_to_duckypad_buf = [0] * PC_TO_DUCKYPAD_HID_BUF_SIZE
pc_to_duckypad_buf[0] = 5	# HID Usage ID, always 5
pc_to_duckypad_buf[1] = 0	# Reserved
pc_to_duckypad_buf[2] = 0x19	# Command type: Write PGV
pc_to_duckypad_buf[3] = 9+128    # PGV index
pc_to_duckypad_buf[4] = 0xaa
pc_to_duckypad_buf[5] = 0xbb
pc_to_duckypad_buf[6] = 0xcc
pc_to_duckypad_buf[7] = 0xdd

print("\n\nSending to duckyPad:\n", pc_to_duckypad_buf)
duckypad_to_pc_buf = duckypad_hid_write(pc_to_duckypad_buf)
print("\nduckyPad response:\n", duckypad_to_pc_buf)
hex_list = [f"{n:02x}" for n in duckypad_to_pc_buf]
print("\nduckyPad response hex:\n", hex_list)