import os
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import remote_link


class MessageTests(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(remote_link.decode_message(remote_link.encode_message("VS Code")), "VS Code")

    def test_empty_profile_means_no_match(self):
        self.assertEqual(remote_link.decode_message(remote_link.encode_message(None)), "")

    def test_signature(self):
        data = remote_link.encode_message("VS Code", "s3cret")
        self.assertEqual(remote_link.decode_message(data, "s3cret"), "VS Code")
        with self.assertRaises(ValueError):
            remote_link.decode_message(data, "wrong")
        with self.assertRaises(ValueError):
            remote_link.decode_message(remote_link.encode_message("VS Code"), "s3cret")

    def test_garbage_rejected(self):
        for data in (b"", b"\xff\xfe", b"[]", b'{"v": 2, "profile": "x"}', b'{"v": 1, "profile": 5}', b"x" * 5000):
            with self.assertRaises(ValueError):
                remote_link.decode_message(data)


class AllowlistTests(unittest.TestCase):
    def test_empty_allows_all(self):
        self.assertTrue(remote_link.is_address_allowed("10.1.2.3", remote_link.parse_allowlist("")))

    def test_ip_and_cidr(self):
        nets = remote_link.parse_allowlist("192.168.1.5, 10.0.0.0/8")
        self.assertTrue(remote_link.is_address_allowed("192.168.1.5", nets))
        self.assertTrue(remote_link.is_address_allowed("10.20.30.40", nets))
        self.assertFalse(remote_link.is_address_allowed("192.168.1.6", nets))
        self.assertFalse(remote_link.is_address_allowed("::1", nets))
        self.assertFalse(remote_link.is_address_allowed("not-an-ip", nets))

    def test_ipv4_mapped(self):
        nets = remote_link.parse_allowlist("192.168.1.5")
        self.assertTrue(remote_link.is_address_allowed("::ffff:192.168.1.5", nets))

    def test_invalid_entry(self):
        with self.assertRaises(ValueError):
            remote_link.parse_allowlist("hello")


class ViewerTests(unittest.TestCase):
    def test_matching(self):
        self.assertTrue(remote_link.viewer_matches("mstsc.exe", "Remote Desktop", "MSTSC", ""))
        self.assertTrue(remote_link.viewer_matches("mstsc.exe", "pc-b - Remote Desktop", "mstsc", "pc-b"))
        self.assertFalse(remote_link.viewer_matches("mstsc.exe", "pc-b", "mstsc", "pc-c"))
        self.assertFalse(remote_link.viewer_matches("code.exe", "x", "mstsc", ""))

    def test_no_filters_never_matches(self):
        self.assertFalse(remote_link.viewer_matches("anything", "anything", "", " "))


class ReceiverTests(unittest.TestCase):
    def test_handle_datagram_and_staleness(self):
        rx = remote_link.RemoteReceiver("127.0.0.1", 0, "10.0.0.1", "k")
        good = remote_link.encode_message("VS Code", "k")
        self.assertFalse(rx.handle_datagram(good, "10.0.0.2", now=0))
        self.assertIsNone(rx.get_profile(now=0))
        self.assertFalse(rx.handle_datagram(remote_link.encode_message("VS Code"), "10.0.0.1", now=0))
        self.assertTrue(rx.handle_datagram(good, "10.0.0.1", now=0))
        self.assertEqual(rx.get_profile(now=1), "VS Code")
        self.assertIsNone(rx.get_profile(now=remote_link.STALE_SECONDS + 1))
        rx.handle_datagram(remote_link.encode_message("", "k"), "10.0.0.1", now=2)
        self.assertIsNone(rx.get_profile(now=3))

    def test_sender_to_receiver_over_udp(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        rx = remote_link.RemoteReceiver("127.0.0.1", port, "127.0.0.1", "k")
        rx.start()
        tx = remote_link.RemoteSender("127.0.0.1", port, "k")
        tx.start()
        try:
            tx.set_profile("VS Code")
            deadline = time.time() + 5
            while rx.get_profile() != "VS Code" and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(rx.get_profile(), "VS Code")
            tx.set_profile("")
            deadline = time.time() + 5
            while rx.get_profile() is not None and time.time() < deadline:
                time.sleep(0.05)
            self.assertIsNone(rx.get_profile())
        finally:
            tx.stop()
            rx.stop()

    def test_per_port_slots(self):
        rx = remote_link.RemoteReceiver("127.0.0.1", [52010, 52011], "10.0.0.1", "k")
        self.assertTrue(rx.handle_datagram(remote_link.encode_message("Firefox", "k"), "10.0.0.1", port_index=0, now=0))
        self.assertTrue(rx.handle_datagram(remote_link.encode_message("Autohotkey", "k"), "10.0.0.1", port_index=1, now=0))
        self.assertEqual(rx.get_profile(0, now=1), "Firefox")
        self.assertEqual(rx.get_profile(1, now=1), "Autohotkey")
        # slots age independently: refreshing port 1 does not keep port 0 alive
        rx.handle_datagram(remote_link.encode_message("Autohotkey", "k"), "10.0.0.1", port_index=1, now=remote_link.STALE_SECONDS)
        self.assertIsNone(rx.get_profile(0, now=remote_link.STALE_SECONDS + 1))
        self.assertEqual(rx.get_profile(1, now=remote_link.STALE_SECONDS + 1), "Autohotkey")

    def test_two_senders_over_udp(self):
        probes = []
        for _ in range(2):
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind(("127.0.0.1", 0))
            probes.append(probe.getsockname()[1])
            probe.close()
        rx = remote_link.RemoteReceiver("127.0.0.1", probes, "127.0.0.1", "k")
        rx.start()
        senders = [remote_link.RemoteSender("127.0.0.1", port, "k") for port in probes]
        for tx in senders:
            tx.start()
        try:
            senders[0].set_profile("Firefox")
            senders[1].set_profile("Autohotkey")
            deadline = time.time() + 5
            while (rx.get_profile(0) != "Firefox" or rx.get_profile(1) != "Autohotkey") and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(rx.get_profile(0), "Firefox")
            self.assertEqual(rx.get_profile(1), "Autohotkey")
            # continued heartbeats from sender 2 must not disturb slot 0
            time.sleep(remote_link.HEARTBEAT_SECONDS * 2)
            self.assertEqual(rx.get_profile(0), "Firefox")
        finally:
            for tx in senders:
                tx.stop()
            rx.stop()


class SenderTimingTests(unittest.TestCase):
    def setUp(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.tx = remote_link.RemoteSender("127.0.0.1", self.sock.getsockname()[1])
        self.tx.start()

    def tearDown(self):
        self.tx.stop()
        self.sock.close()

    def receive(self, timeout):
        self.sock.settimeout(timeout)
        try:
            return remote_link.decode_message(self.sock.recvfrom(2048)[0])
        except socket.timeout:
            return None

    def test_profile_change_sent_immediately(self):
        self.tx.set_profile("A")
        self.assertEqual(self.receive(1), "A")
        self.tx.set_profile("B")
        self.assertEqual(self.receive(1), "B")

    def test_same_profile_without_focus_change_is_only_a_heartbeat(self):
        self.tx.set_profile("A")
        self.assertEqual(self.receive(1), "A")
        self.tx.set_profile("A")
        self.assertIsNone(self.receive(1))
        self.assertEqual(self.receive(remote_link.HEARTBEAT_SECONDS + 1), "A")

    def test_focus_change_sent_immediately_even_if_profile_same(self):
        self.tx.set_profile("A")
        self.assertEqual(self.receive(1), "A")
        self.tx.set_profile("A", focus_changed=True)
        self.assertEqual(self.receive(1), "A")
        self.tx.set_profile("", focus_changed=True)
        self.assertEqual(self.receive(1), "")


if __name__ == '__main__':
    unittest.main()
