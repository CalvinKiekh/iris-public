"""A switch in front of the test bridge, so a UI test can pull the plug.

Forwards 127.0.0.1:<listen> to 127.0.0.1:<target>. A request for
/__offline?seconds=N cuts every open connection - the card stream too - and
turns every new one away for N seconds, the way a phone that lost its signal
or a Mac that fell asleep would look to the app.

    python3 offline_proxy.py 8774 8776 8773

The switch has a port of its own (the third one): on the forwarding port a
keep-alive connection carries later requests straight to the bridge, so a
switch request sent over one the test had used before never reached here.
"""
import socket
import sys
import threading
import time
import urllib.parse

LISTEN, TARGET = int(sys.argv[1]), int(sys.argv[2])
CONTROL = int(sys.argv[3]) if len(sys.argv) > 3 else None
state = {"until": 0.0}


def log(*parts):
    print(time.strftime("%H:%M:%S"), f"{time.time() % 60:06.3f}", *parts, flush=True)
open_socks = set()
lock = threading.Lock()


def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()
            with lock:
                open_socks.discard(s)


def handle_switch(client, first):
    """Pull the plug: cut every open connection, turn new ones away."""
    path = first.split(b" ")[1].decode()
    seconds = float(urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
                    .get("seconds", ["15"])[0])
    state["until"] = time.time() + seconds
    # no-store: a cached "ok" once made the switch look pulled while the
    # request never got here.
    client.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nCache-Control: no-store\r\n"
                   b"Connection: close\r\n\r\nok")
    client.close()
    with lock:
        cut = list(open_socks)
        open_socks.clear()
    log(f"OFFLINE für {seconds:g} s, kappe {len(cut)} Sockets")
    for s in cut:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        s.close()


def handle(client):
    # Tracked from the moment it is accepted: a connection that is still
    # waiting for its first bytes when the plug is pulled is cut as well -
    # otherwise the app could reuse it and get through while "offline".
    with lock:
        open_socks.add(client)
    if time.time() < state["until"]:
        log("abgewiesen (offline)")
        client.close()                     # offline: nobody home
        return
    try:
        first = client.recv(65536)
    except OSError:
        client.close()
        return
    if not first.startswith(b"GET /__offline") and time.time() < state["until"]:
        log("abgewiesen (offline, wartete)", first.split(b"\r\n")[0][:60])
        client.close()                     # went offline while it waited
        return
    log("durch:", first.split(b"\r\n")[0][:70])
    if first.startswith(b"GET /__offline"):
        handle_switch(client, first)
        return
    try:
        upstream = socket.create_connection(("127.0.0.1", TARGET), timeout=5)
        upstream.settimeout(None)
        upstream.sendall(first)
    except OSError:
        client.close()
        return
    with lock:
        open_socks.add(upstream)
    threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pump, args=(upstream, client), daemon=True).start()


def listen(port, handler):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(64)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handler, args=(conn,), daemon=True).start()


def control(client):
    """Only the switch lives here - whatever the request says."""
    try:
        first = client.recv(65536)
    except OSError:
        client.close()
        return
    if not first.startswith(b"GET /__offline"):
        client.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        client.close()
        return
    handle_switch(client, first)


if CONTROL:
    threading.Thread(target=listen, args=(CONTROL, control), daemon=True).start()
listen(LISTEN, handle)
