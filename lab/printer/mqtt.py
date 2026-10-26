"""Listen to the printer's own MQTT reports over the LAN. The only message ever sent is one `pushall` request,
which asks the printer to report its full state; nothing that changes the printer can be sent from here."""
import json
import os
import stat
import time
from pathlib import Path

PUSHALL = {"pushing": {"sequence_id": "0", "command": "pushall"}}
DEFAULT_ENV = Path("~/.config/print-lab/printer.env").expanduser()
END_STATES = ("FINISH", "FAILED", "IDLE")


class ReadOnlyPublisher:
    def __init__(self, publish, *, serial: str):
        self._publish, self.topic = publish, f"device/{serial}/request"

    def pushall(self) -> None:
        self._publish(self.topic, json.dumps(PUSHALL))

    def send(self, topic: str, payload) -> None:
        raise PermissionError("The printer log is read-only: it only ever sends the pushall request.")


def load_printer_env(path: Path = DEFAULT_ENV) -> dict:
    """PRINTER_HOST, BAMBU_SERIAL and BAMBU_TOKEN (the LAN access code) from a file only the owner can read."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Create {path} (chmod 600) with three lines: PRINTER_HOST=…, BAMBU_SERIAL=… and "
                                "BAMBU_TOKEN=<the access code from the printer's screen>. The first run tells you a "
                                "fourth line to add, BAMBU_CERT_SHA256=…, which pins the printer's certificate.")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError(f"{path} must be readable by you only: chmod 600 {path}")
    vals = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    missing = [k for k in ("PRINTER_HOST", "BAMBU_SERIAL", "BAMBU_TOKEN") if not vals.get(k)]
    if missing:
        raise ValueError(f"{path} is missing {', '.join(missing)}.")
    pin = vals.get("BAMBU_CERT_SHA256", "").replace(":", "").strip().lower() or None
    return {"host": vals["PRINTER_HOST"], "serial": vals["BAMBU_SERIAL"], "code": vals["BAMBU_TOKEN"],
            "cert_sha256": pin}


def _peer_certificate(host: str, port: int = 8883, timeout: float = 10.0) -> bytes:
    """The printer's TLS certificate (DER), fetched without sending any credentials."""
    import socket
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw, ctx.wrap_socket(raw) as tls:
        return tls.getpeercert(binary_form=True)


def check_certificate(env: dict, fetch) -> None:
    """Refuse to send the access code unless the printer presents the certificate pinned in printer.env. The
    printer's certificate is self-signed, so the pin stands in for normal certificate checking."""
    import hashlib
    got = hashlib.sha256(fetch()).hexdigest()
    pin = (env.get("cert_sha256") or "").replace(":", "").lower()
    if not pin:
        raise ConnectionError("No printer certificate is pinned. If you're on your own network and the address is "
                              f"the printer's, add this line to printer.env: BAMBU_CERT_SHA256={got}")
    if got != pin:
        raise ConnectionError(f"The certificate at this address doesn't match the pinned printer (got {got}). "
                              "Nothing was sent. If the printer was reset or replaced, check it and update the pin.")


def listen(env: dict, on_report, *, should_stop, connect_timeout_s: float = 20.0) -> None:
    """Connect, subscribe to the report topic, send pushall once, and pass each decoded report to on_report until
    should_stop() is true. Needs paho-mqtt."""
    import ssl

    import paho.mqtt.client as mqtt

    check_certificate(env, lambda: _peer_certificate(env["host"]))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"print-lab-log-{os.getpid()}")
    client.username_pw_set("bblp", env["code"])
    # The printer's certificate is self-signed, so normal checking can't pass; check_certificate above pinned it.
    # The pin is checked on a separate connection just before this one; an attacker would have to swap devices
    # in that moment.
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    pub = ReadOnlyPublisher(lambda t, p: client.publish(t, p), serial=env["serial"])
    state = {"connected": False, "error": None}

    def on_connect(c, _u, _f, rc, _p=None):
        if rc != 0:
            state["error"] = f"the printer refused the connection ({rc}); check the access code and LAN mode"
            return
        state["connected"] = True
        c.subscribe(f"device/{env['serial']}/report")
        pub.pushall()

    def on_message(_c, _u, msg):
        try:
            on_report(json.loads(msg.payload))
        except ValueError:
            pass

    client.on_connect, client.on_message = on_connect, on_message
    client.connect(env["host"], 8883, keepalive=60)
    client.loop_start()
    try:
        t0 = time.time()
        while not state["connected"] and not state["error"]:
            if time.time() - t0 > connect_timeout_s:
                raise TimeoutError(f"No answer from the printer at {env['host']}:8883 within {connect_timeout_s:g} s.")
            time.sleep(0.2)
        if state["error"]:
            raise ConnectionError(state["error"])
        while not should_stop():
            time.sleep(1.0)
    finally:
        client.loop_stop()
        client.disconnect()
