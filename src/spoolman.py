import socket
import json
import sys

class SpoolmanClient:
    def __init__(self, cfg):
        self.enabled = cfg.get("enabled", False)
        self.host = cfg.get("host")
        self.port = cfg.get("port", 7912)
        self.extra_field = cfg.get("extra_field", "rfid_uid")

    def find_by_uid(self, uid_hex):
        if not self.enabled:
            return None

        s = None
        try:
            addr = socket.getaddrinfo(self.host, self.port)[0][-1]
            s = socket.socket()
            s.settimeout(5)
            s.connect(addr)
            request = (
                "GET /api/v1/spool?allow_archived=false HTTP/1.1\r\n"
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

            body = response.split(b"\r\n\r\n", 1)[1]
            spools = json.loads(body)

            for spool in spools:
                extra = spool.get("extra", {})
                value = extra.get(self.extra_field)
                if value and uid_hex in value:
                    filament = spool.get("filament", {})
                    return {
                        "remaining_weight": spool.get("remaining_weight"),
                        "filament_name": filament.get("name"),
                    }

            return None
        except Exception as e:
            print("Error querying Spoolman:", e)
            sys.print_exception(e)
            return None
        finally:
            if s:
                s.close()
