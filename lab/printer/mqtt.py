"""Listen to the printer's own MQTT reports over the LAN. The only message ever sent is a `pushall` request (once
per connection, reconnects included), which asks the printer to report its full state; nothing that changes the
printer can be sent from here."""
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


def pinned_context(der: bytes):
    """A TLS context that trusts exactly this certificate and nothing else. Used for every handshake paho makes,
    reconnects included, so a different device at the printer's address is refused before the access code is sent.
    Hostname checking stays off: the printer's certificate names its serial, not its address."""
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN  # the pinned leaf itself is the trust anchor
    ctx.load_verify_locations(cadata=der)
    return ctx


def cert_details(der: bytes) -> dict:
    """Subject, issuer and expiry of a certificate, read with the openssl command (best effort)."""
    import shutil
    import ssl
    import subprocess
    if not shutil.which("openssl"):
        return {"subject": "?", "issuer": "?", "not_after": "?", "expired": False}
    pem = ssl.DER_cert_to_PEM_cert(der).encode()
    out = subprocess.run(["openssl", "x509", "-noout", "-subject", "-issuer", "-enddate"], input=pem,
                         capture_output=True).stdout.decode()
    fields = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    if not fields:  # openssl couldn't read it: say so rather than guess
        return {"subject": "unreadable", "issuer": "unreadable", "not_after": "unknown", "expired": None}
    expired = subprocess.run(["openssl", "x509", "-noout", "-checkend", "0"], input=pem,
                             capture_output=True).returncode != 0
    return {"subject": fields.get("subject", "?").strip(), "issuer": fields.get("issuer", "?").strip(),
            "not_after": fields.get("notAfter", "?").strip(), "expired": expired}


def check_certificate(env: dict, fetch, details=cert_details) -> bytes:
    """Refuse to send the access code unless the printer presents the certificate pinned in printer.env. The
    printer's certificate is self-signed, so the pin stands in for normal certificate checking."""
    import hashlib
    der = fetch()
    got = hashlib.sha256(der).hexdigest()
    pin = (env.get("cert_sha256") or "").replace(":", "").lower()
    info = details(der)
    if info.get("expired") is True:
        raise ConnectionError(f"The printer's certificate expired on {info.get('not_after')}. The logger won't "
                              "connect with an expired certificate and has sent nothing.")
    if not pin:
        # Enrolment: a fingerprint read over the network proves nothing by itself, so show what the certificate
        # claims and let the owner check it against the printer before pinning it.
        raise ConnectionError(
            "No printer certificate is pinned, so nothing was sent. Before pinning, check this certificate:\n"
            f"  subject: {info.get('subject')}\n  issuer:  {info.get('issuer')}\n  expires: {info.get('not_after')}\n"
            f"  The subject's CN should be the serial on your printer's screen (Settings → Device): "
            f"{env.get('serial')}; check it matches your printer's serial, and that the issuer is Bambu Lab's device CA.\n"
            "If both hold and you're on your own network, add this line to printer.env:\n"
            f"  BAMBU_CERT_SHA256={got}")
    if got != pin:
        raise ConnectionError(f"The certificate at this address doesn't match the pinned printer (got {got}). "
                              "Nothing was sent. If the printer was reset or replaced, check it and update the pin.")
    return der


class _ListenerState:
    """Shared between paho's network thread and the main thread: an error in a report handler stops the listener
    instead of silently killing paho's thread."""

    def __init__(self):
        self.connected, self.error = False, None

    def guard(self, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - re-raised on the main thread
            self.error = self.error or exc

    def raise_if_failed(self) -> None:
        if isinstance(self.error, BaseException):
            raise self.error
        if self.error:
            raise ConnectionError(self.error)


def listen(env: dict, on_report, *, should_stop, on_disconnect=None, connect_timeout_s: float = 20.0,
           idle_timeout_s: float = 600.0) -> None:
    """Connect, subscribe to the report topic, send pushall on each connection, and pass each decoded report to
    on_report until should_stop() is true. on_disconnect is called whenever the connection drops. Silence longer than
    idle_timeout_s raises TimeoutError instead of waiting forever. Needs paho-mqtt."""
    import paho.mqtt.client as mqtt

    # Fetch the certificate once to compare with the pin, then make paho's TLS trust only that certificate, so the
    # check holds on the connection that carries the access code and on every reconnect.
    der = check_certificate(env, lambda: _peer_certificate(env["host"]))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"print-lab-log-{os.getpid()}")
    client.username_pw_set("bblp", env["code"])
    client.tls_set_context(pinned_context(der))
    pub = ReadOnlyPublisher(lambda t, p: client.publish(t, p), serial=env["serial"])
    state = _ListenerState()

    last_heard = [time.time()]

    def on_connect(c, _u, _f, rc, _p=None):
        def go():
            if rc != 0:
                raise ConnectionError(f"the printer refused the connection ({rc}); check the access code and LAN mode")
            state.connected = True
            c.subscribe(f"device/{env['serial']}/report")
            pub.pushall()
        state.guard(go)

    def on_disconnect_cb(_c, _u, *_rest):
        if on_disconnect:
            state.guard(on_disconnect)

    def on_message(_c, _u, msg):
        try:
            rep = json.loads(msg.payload)
        except ValueError:
            return
        last_heard[0] = time.time()
        if isinstance(rep, dict):
            state.guard(lambda: on_report(rep))

    client.on_connect, client.on_message, client.on_disconnect = on_connect, on_message, on_disconnect_cb
    client.connect(env["host"], 8883, keepalive=60)
    client.loop_start()
    try:
        t0 = time.time()
        while not state.connected and not state.error:
            if time.time() - t0 > connect_timeout_s:
                raise TimeoutError(f"No answer from the printer at {env['host']}:8883 within {connect_timeout_s:g} s.")
            time.sleep(0.2)
        state.raise_if_failed()
        while not should_stop():
            state.raise_if_failed()
            if time.time() - last_heard[0] > idle_timeout_s:
                raise TimeoutError(f"Nothing from the printer for {idle_timeout_s / 60:g} minutes.")
            time.sleep(1.0)
    finally:
        client.loop_stop()
        client.disconnect()
