import socket
import json
import sys
import time

class SpoolmanClient:
    def __init__(self, cfg):
        self.enabled = cfg.get("enabled", False)
        self.host = cfg.get("host")
        self.port = cfg.get("port", 7912)
        self.extra_field = cfg.get("extra_field", "card_uids")

    def _get_once(self, path):
        s = None
        try:
            addr = socket.getaddrinfo(self.host, self.port)[0][-1]
            s = socket.socket()
            s.settimeout(5)
            s.connect(addr)
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {self.host}\r\n"
                "Connection: close\r\n\r\n"
            )
            s.send(request.encode())

            response = b""
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break
                response += chunk

            status_line = response.split(b"\r\n", 1)[0]
            if b" 200 " not in status_line:
                return None

            body = response.split(b"\r\n\r\n", 1)[1]
            return json.loads(body)
        finally:
            if s:
                s.close()

    def _get(self, path):
        # WiFi can hiccup right after RFID/I2C activity - one retry is enough
        # to ride out a transient failure without making a failed lookup feel
        # any slower than the RFID read itself already is.
        for attempt in (1, 2):
            try:
                return self._get_once(path)
            except Exception as e:
                if attempt == 2:
                    print("Error querying Spoolman:", e)
                    sys.print_exception(e)
                    return None
                time.sleep_ms(300)

    @staticmethod
    def _summarize(spool):
        filament = spool.get("filament", {})
        return {
            "remaining_weight": spool.get("remaining_weight"),
            "filament_name": filament.get("name"),
        }

    def find_by_spool_id(self, spool_id):
        if not self.enabled or spool_id is None:
            return None
        spool = self._get(f"/api/v1/spool/{spool_id}")
        return self._summarize(spool) if spool else None

    def find_by_uid(self, uid_hex):
        if not self.enabled:
            return None

        spools = self._get("/api/v1/spool?allow_archived=false")
        if not spools:
            return None

        uid_hex = uid_hex.lower()
        for spool in spools:
            extra = spool.get("extra", {})
            value = extra.get(self.extra_field)
            if value and uid_hex in value.lower():
                return self._summarize(spool)

        return None

    def find(self, uid_hex, spool_id=None):
        # The RFID tag's own spool_id (when present) is an exact reference and
        # cheaper to look up than scanning every spool's extra fields, so try
        # it first and only fall back to UID matching.
        result = self.find_by_spool_id(spool_id)
        if result is not None:
            return result
        return self.find_by_uid(uid_hex)
