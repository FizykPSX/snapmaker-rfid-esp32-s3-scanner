import socket
import json
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
                print("Spoolman non-200 response:", status_line, "(", len(response), "bytes total)")
                return None

            body = response.split(b"\r\n\r\n", 1)[1]
            return json.loads(body)
        finally:
            if s:
                s.close()

    ATTEMPTS = 4
    RETRY_DELAY_MS = 400

    def _get(self, path):
        # The button GPIOs' IRQ handlers plus continuous LCD/RFID bus traffic
        # in the main loop were seen (on hardware) to reliably stall the first
        # 1-2 connect() attempts right after a read - a plain 2-try retry
        # wasn't always enough under that load, so retry a few more times.
        for attempt in range(1, self.ATTEMPTS + 1):
            try:
                result = self._get_once(path)
            except Exception as e:
                print("Spoolman request", attempt, "raised:", e)
                result = None
            if result is not None:
                return result
            if attempt < self.ATTEMPTS:
                time.sleep_ms(self.RETRY_DELAY_MS)
        return None

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
