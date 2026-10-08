"""
Network link between two autoswitcher instances, used for RDP / VNC sessions.

* The remote instance (inside the RDP/VNC session) runs as a ``RemoteSender``
  and periodically sends the profile its rules selected.
* The local instance (the one with the physical duckyPad) runs a
  ``RemoteReceiver`` and applies the latest received profile, but only while
  the RDP/VNC viewer is the active local window.

Messages are small JSON datagrams sent over UDP. They are re-sent periodically
(heartbeat) so that lost packets are harmless, and so that the receiver knows
the remote instance is still alive.
"""

import hmac
import hashlib
import ipaddress
import json
import socket
import threading
import time

REMOTE_MODE_OFF = 'off'
REMOTE_MODE_SENDER = 'sender'
REMOTE_MODE_RECEIVER = 'receiver'
REMOTE_MODES = (REMOTE_MODE_OFF, REMOTE_MODE_SENDER, REMOTE_MODE_RECEIVER)

DEFAULT_PORT = 52007
DEFAULT_LISTEN_ADDRESS = '0.0.0.0'

HEARTBEAT_SECONDS = 2.0
STALE_SECONDS = 10.0
MAX_PROFILE_NAME_LENGTH = 32
PROTOCOL_VERSION = 1
MAX_DATAGRAM_SIZE = 1024

def _sign(secret, profile):
    return hmac.new(secret.encode('utf8'), profile.encode('utf8'), hashlib.sha256).hexdigest()

def encode_message(profile, secret=''):
    profile = str(profile or '')[:MAX_PROFILE_NAME_LENGTH]
    message = {'v': PROTOCOL_VERSION, 'profile': profile}
    if secret:
        message['sig'] = _sign(secret, profile)
    return json.dumps(message).encode('utf8')

def decode_message(data, secret=''):
    """Returns the profile name ('' means "no rule matched"), or raises ValueError."""
    if len(data) > MAX_DATAGRAM_SIZE:
        raise ValueError("message too large")
    try:
        message = json.loads(data.decode('utf8'))
    except Exception:
        raise ValueError("not a valid message")
    if not isinstance(message, dict) or message.get('v') != PROTOCOL_VERSION:
        raise ValueError("unsupported message")
    profile = message.get('profile')
    if not isinstance(profile, str) or len(profile) > MAX_PROFILE_NAME_LENGTH:
        raise ValueError("invalid profile")
    if secret:
        sig = message.get('sig')
        if not isinstance(sig, str) or not hmac.compare_digest(sig, _sign(secret, profile)):
            raise ValueError("bad signature")
    return profile

def parse_allowlist(allowlist_str):
    """Parses a comma/space separated list of IP addresses or CIDR networks. Raises ValueError if invalid."""
    networks = []
    for item in str(allowlist_str or '').replace(',', ' ').split():
        networks.append(ipaddress.ip_network(item, strict=False))
    return networks

def is_address_allowed(address, networks):
    """An empty allowlist allows everybody."""
    if len(networks) == 0:
        return True
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip.version == net.version and ip in net for net in networks)

def viewer_matches(app_name, window_title, viewer_app, viewer_title):
    """Same matching semantics as autoswitch rules. At least one filter must be set."""
    viewer_app = str(viewer_app or '').strip().lower()
    viewer_title = str(viewer_title or '').strip().lower()
    if len(viewer_app) == 0 and len(viewer_title) == 0:
        return False
    if len(viewer_app) > 0 and viewer_app not in str(app_name).lower():
        return False
    if len(viewer_title) > 0 and viewer_title not in str(window_title).lower():
        return False
    return True

def parse_port(port_value):
    port = int(str(port_value).strip())
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return port

class RemoteSender:
    def __init__(self, host, port, secret=''):
        self.host = host
        self.port = port
        self.secret = secret
        self._profile = ''
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._last_error = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wakeup.set()

    def set_profile(self, profile):
        """Cheap and non-blocking, safe to call from the UI thread. Sends immediately when changed."""
        profile = str(profile or '')
        with self._lock:
            if profile == self._profile:
                return
            self._profile = profile
        self._wakeup.set()

    def _run(self):
        sock = None
        while not self._stop.is_set():
            self._wakeup.wait(HEARTBEAT_SECONDS)
            self._wakeup.clear()
            if self._stop.is_set():
                break
            with self._lock:
                profile = self._profile
            try:
                if sock is None:
                    family = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_DGRAM)[0][0]
                    sock = socket.socket(family, socket.SOCK_DGRAM)
                sock.sendto(encode_message(profile, self.secret), (self.host, self.port))
                self._last_error = None
            except Exception as e:
                if str(e) != self._last_error:
                    print("remote sender:", e)
                self._last_error = str(e)
                if sock is not None:
                    sock.close()
                    sock = None
        if sock is not None:
            sock.close()

class RemoteReceiver:
    def __init__(self, address, port, allowlist_str='', secret=''):
        self.address = address
        self.port = port
        self.secret = secret
        self.allowlist = parse_allowlist(allowlist_str)
        self._profile = ''
        self._received_at = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._sock = None

    def start(self):
        """Binds the socket (raises OSError on failure) and starts listening in the background."""
        family = socket.AF_INET6 if ':' in self.address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            sock.bind((self.address, self.port))
        except OSError:
            sock.close()
            raise
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
        if self._sock is not None:
            self._sock.close()

    def _run(self):
        while not self._stop.is_set():
            try:
                data, source = self._sock.recvfrom(MAX_DATAGRAM_SIZE + 1)
            except socket.timeout:
                continue
            except OSError:
                break
            self.handle_datagram(data, source[0])

    def handle_datagram(self, data, source_address, now=None):
        if not is_address_allowed(source_address, self.allowlist):
            return False
        try:
            profile = decode_message(data, self.secret)
        except ValueError:
            return False
        with self._lock:
            self._profile = profile
            self._received_at = time.monotonic() if now is None else now
        return True

    def get_profile(self, now=None):
        """Latest profile sent by the remote instance, or None if there is none or it has gone silent."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._received_at is None or now - self._received_at > STALE_SECONDS:
                return None
            return self._profile if len(self._profile) > 0 else None
