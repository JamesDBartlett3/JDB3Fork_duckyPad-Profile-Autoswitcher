# duckyPad Profile Auto-switcher

[Get duckyPad](https://duckypad.com) | [Official Discord](https://discord.gg/4sJCBx5)

This app allows your duckyPad to **switch profiles automatically** based on **current active window**.

![Alt text](resources/switch.gif)

## User Manual

### Download App: Windows

- 👉 [Download the latest release](https://github.com/dekuNukem/duckyPad-profile-autoswitcher/releases/latest)

Extract `.zip` file and launch the app by clicking `duckypad_autoprofile.exe`:

![Alt text](resources/app.png)

Windows might complain. Click `More info` and `Run anyway`.

Feel free to [review the files](./src), or run the source code directly with Python.

![Alt text](resources/defender.png)

### Download App: macOS / Linux

* 👉 [See instructions here](https://dekunukem.github.io/duckyPad-Pro/doc/linux_macos_notes.html)

#### Run from Source: macOS HID Setup

The app needs the pip **`hidapi`** package, which bundles the native hidapi library. Do **not** install the similarly-named **`hid`** package — it imports as `hid` too, but requires a system-installed hidapi library (`brew install hidapi`) and fails with `ImportError: Unable to load any of the following libraries: libhidapi.dylib ...` otherwise.

Homebrew's Python is externally managed (PEP 668) and refuses system-wide `pip install`, so run from source inside a virtual environment. Homebrew also splits tkinter out of Python — the app is a Tk GUI, so `python-tk` is required:

```bash
brew install python-tk@3.12                # tkinter is not bundled with Homebrew Python
cd src
$(brew --prefix)/bin/python3 -m venv .venv # use the Homebrew Python, not /usr/bin/python3
source .venv/bin/activate
pip install -r requirements.txt
python duckypad_autoprofile.py             # prefix with sudo if HID access is denied
```

If the app reports "duckyPad detected, but I need additional permissions", follow the [official macOS notes](https://dekunukem.github.io/duckyPad-Pro/doc/linux_macos_notes.html).

> **Virtual-machine note (Docker-OSX / Quickemu):** USB passthrough is fine for install, launch, and device enumeration, but HID command traffic (e.g. profile switch) can make the pad restart its USB session — and QEMU's `usb-host` does not follow the re-enumeration, so the device is lost until the VM restarts. Validate HID command behavior on real macOS hardware, not in a VM.

- **[LINUX ONLY]** Window detection not working? You might need to implement your own `get_list_of_all_windows()` and `get_active_window()` in `get_window.py`.
### Using the App

Your duckyPad should show up in the `Connection` section.

![Alt text](resources/empty.png)

Profile-Autoswitching is based on a list of _rules_.

To create a new rule, click `New rule...` button:

![Alt text](resources/rulebox.png)

A new window should pop up:

![Alt text](resources/new.png)

Each rule contains **Application name**, **Window Title**, and the **Profile** to switch to.

**`App name`** and **`Window Title`**:

- Type the keyword you want to match
- **NOT** case sensitive

**`Jump-to Profile`**:

- **Profile Name** to switch to when matched.
  - Full Name
  - **Case Sensitive**

Click `Save` when done.

Current active window and a list of all windows are provided for reference.

---

Back to the main window, duckyPad should now automatically switch profile once a rule is matched!

![Alt text](resources/active_rules.png)

- Rules are evaluated **from top to bottom**, and **stops at first match**!

- Currently matched rule will turn green.

- Select a rule and click `Move up` and `Move down` to rearrange priority.

- Click `On/Off` button to enable/disable a rule.

That's pretty much it! Just leave the app running and duckyPad will do its thing!

## System Tray Support

The app can minimize to the system tray instead of closing completely.

### Settings

The app includes a **Settings** section with the following options:

- **Close to tray**: When enabled, closing the window minimizes to the system tray instead of quitting. When disabled (default), closing the window exits the app.

- **Start minimized to tray**: When enabled, the app starts hidden in the system tray. _Note: The GUI window will still appear briefly before minimizing to the system tray._

- **Launch at startup** (Windows only): When enabled, the app automatically starts when Windows boots. If "Start minimized to tray" is also enabled, the app will start minimized to the system tray.

### System Tray Icon

- Click the system tray icon to show the window.

- Right-click the system tray icon and select "Quit" to exit the application completely.

- You can also click the **Quit** button in the Connection section of the main window.

### Command-Line Options

You can also start the app minimized to the system tray using the `--minimized` command-line argument:

**Windows:**

```
duckypad_autoprofile.exe --minimized
```

**macOS / Linux:**

```
python3 duckypad_autoprofile.py --minimized
```

This is useful for auto-starting the app on system boot without showing the window.

## RDP / VNC Support

Profile autoswitching can also work **inside a remote desktop session**. Run one copy of the app on each computer and let them talk to each other:

- **Remote instance** (the computer you are remotely controlling, inside the RDP/VNC session) runs as a **Sender**. It evaluates its autoswitch rules as usual, but sends the resulting profile name over the network instead of to a duckyPad.
- **Local instance** (the computer your duckyPad is plugged into) runs as a **Receiver**. While your RDP/VNC viewer is the active window, it switches the duckyPad to the profile requested by the remote instance. When the viewer loses focus, the normal local rules apply again.

### Setup

Click `Remote...` in the Dashboard on both computers.

**Remote computer (inside the session):**

1. Select **Sender**.
2. `Send to address`: the address of the local computer, as seen from the remote computer.
3. `Port`: must match the receiver's port (default `52007`).
4. Create autoswitch rules as usual (e.g. App name `code` → Profile `VS Code`).

**Local computer (duckyPad attached):**

1. Select **Receiver**.
2. `Listen address` / `Port`: where to listen for messages (default `0.0.0.0:52007`, i.e. all interfaces).
3. `Allowed senders` (optional): comma-separated IP addresses or CIDR networks, e.g. `192.168.1.20, 10.0.0.0/8`. Leave blank to accept anyone.
4. `Viewer app name contains` and/or `Viewer window title contains`: identify your RDP/VNC viewer, e.g. `mstsc` or `vncviewer`.

Optionally set the same **Shared secret** on both ends, so the receiver ignores messages that aren't signed with it.

### Notes

- The sender sends a message **immediately** whenever its focused window changes, then repeats it every few seconds as a heartbeat. The receiver ignores a sender that has been silent for more than 10 seconds, and when the sender has no matching rule.
- Messages are small UDP datagrams. The remote computer must be able to reach the local computer on the chosen port (check firewalls / NAT, or use a VPN / tunnel).
- Messages are **not encrypted**, and the shared secret does not protect against replayed messages. Only use this on networks you trust, and use `Allowed senders`.
- The sender does not need a duckyPad connected.
- Settings are stored in `config.txt` (`remote_*` keys).

## Debugging

If you encounter issues, a debug version of the app is included that shows a console window with diagnostic output:

**Windows:**

```
duckypad_autoprofile_debug.exe
```

This console window displays information about profile switches, settings changes, and any errors that occur.

## HID Command Protocol

You can also write your own program to control duckyPad.

[Click me for details](HID_details.md)!

## Questions or Comments?

Please feel free to [open an issue](https://github.com/dekuNukem/duckypad/issues), ask in the [official duckyPad discord](https://discord.gg/4sJCBx5), DM me on discord `dekuNukem#6998`, or email `dekuNukem`@`gmail`.`com` for inquires.
