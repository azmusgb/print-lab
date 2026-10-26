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
                                "BAMBU_TOKEN=<the access code from the printer's screen>.")
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
    return {"host": vals["PRINTER_HOST"], "serial": vals["BAMBU_SERIAL"], "code": vals["BAMBU_TOKEN"]}


def listen(env: dict, on_report, *, should_stop, connect_timeout_s: float = 20.0) -> None:
    """Connect, subscribe to the report topic, send pushall once, and pass each decoded report to on_report until
    should_stop() is true. Needs paho-mqtt."""
    import ssl

    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"print-lab-log-{os.getpid()}")
    client.username_pw_set("bblp", env["code"])
    client.tls_set(cert_reqs=ssl.CERT_NONE)  # the printer's certificate is self-signed
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
