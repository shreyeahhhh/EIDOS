"""A semantic worker that breaks the protocol in one scripted way, for the tests of the client (V1.3 Step 5).

Run as ``python -I misbehaving_semantic_worker.py MODE IDENTITY_JSON``. ``IDENTITY_JSON`` holds the identity a good worker would report (revision, weights_sha256, directory_sha256, dimension,
max_pieces). Modes that spoil the start: ``exit`` (ends at once with a message on stderr), ``hang`` (never says anything), ``garbage`` (a line that is not JSON), ``bad_protocol``,
``wrong_type`` (a first message that is not ready), ``failed_<reason>`` (a failed message), ``extra_field``, ``partial_ready`` (half a line, then the end), ``identity_<field>`` (a ready
message in which one field of the identity is wrong). Modes that spoil the first reply, after a good start: ``wrong_id``, ``short_items``, ``too_many_items``, ``garbage_reply``,
``oversize_reply``, ``partial_reply``, ``error_reply``, ``refused_reply``, ``nan_reply``, ``eof_reply``, ``hang_reply``, ``slow_exit`` (says something on stderr, closes its output, and ends with code 7 only after a
moment), ``quiet_slow_exit`` (the same, having closed stderr too), ``ignore_close`` (an honest worker that does not end when asked to close), ``reply_at_bound`` and ``reply_over_bound`` (a valid reply whose line is exactly, or one byte over, the bound given as the
third argument), ``echo_id`` (answers each text with the id of the request as its piece count), ``close_input`` (closes its own input after it is ready, and then does nothing), ``ok`` (an honest worker that answers every text with the vector [1, 0, ...]).
"""

import json
import os
import sys
import time

PROTOCOL = "eidos-semantic-worker-v1"


def send(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))  # bytes, so a line ends with one newline on every platform
    sys.stdout.buffer.flush()


def ready_line(identity: dict, *, protocol: str = PROTOCOL, extra: dict | None = None) -> str:
    message = {
        "type": "ready",
        "protocol": protocol,
        "identity": identity,
        "environment": {"python_version": "3.13.1", "implementation": "CPython", "platform": "test", "libraries": [["lib", "1"]], "threads": 1, "evaluation_mode": True, "device": "cpu", "dtype": "float32"},
        "import_seconds": 0.5,
        "verify_seconds": 0.25,
        "load_seconds": 0.75,
    }
    message.update(extra or {})
    return json.dumps(message) + "\n"


def main(argv: list[str]) -> int:
    mode, given = argv[0], json.loads(argv[1])
    bound = int(argv[2]) if len(argv) > 2 else 0
    identity = {name: given[name] for name in ("revision", "weights_sha256", "directory_sha256", "dimension", "max_pieces")}  # what a worker reports: the model's name is not measured
    if mode == "exit":
        sys.stderr.write("scripted early exit\n")
        return 7
    if mode == "hang":
        time.sleep(3600)
        return 0
    if mode == "garbage":
        send("this is not json\n")
    elif mode == "bad_protocol":
        send(ready_line(identity, protocol="something-else"))
    elif mode == "wrong_type":
        send(json.dumps({"type": "embedded", "id": 1, "seconds": 0.0, "items": []}) + "\n")
    elif mode.startswith("failed_"):
        send(json.dumps({"type": "failed", "reason": mode[len("failed_"):], "message": "scripted refusal"}) + "\n")
        return 3
    elif mode == "extra_field":
        send(ready_line(identity, extra={"surprise": 1}))
    elif mode == "partial_ready":
        send(ready_line(identity)[:40])
        return 0
    elif mode.startswith("identity_"):
        field = mode[len("identity_"):]
        broken = dict(identity)
        broken[field] = broken[field] + 1 if isinstance(broken[field], int) else ("0" * len(broken[field]) if broken[field][:1] != "0" else "1" * len(broken[field]))
        send(ready_line(broken))
    else:
        send(ready_line(identity))
        if mode == "close_input":
            os.close(0)
            time.sleep(30)
            return 0
        return serve(mode, identity, bound)
    time.sleep(0.5)
    return 0


def serve(mode: str, identity: dict, bound: int = 0) -> int:
    for raw in sys.stdin:
        request = json.loads(raw)
        if request.get("type") == "close":
            if mode == "ignore_close":
                continue
            return 0
        texts = request["texts"]
        items = [{"pieces": 3, "vector": [1.0] + [0.0] * (identity["dimension"] - 1)} for _ in texts]
        reply = {"type": "embedded", "id": request["id"], "seconds": 0.125, "items": items}
        if mode == "echo_id":
            reply["items"] = [{"pieces": request["id"], "vector": [1.0] + [0.0] * (identity["dimension"] - 1)} for _ in texts]
        elif mode == "wrong_id":
            reply["id"] = request["id"] + 100
        elif mode == "short_items":
            reply["items"] = items[:-1]
        elif mode == "too_many_items":
            reply["items"] = items + items[:1]
        elif mode == "garbage_reply":
            send("{ not json at all\n")
            continue
        elif mode == "oversize_reply":
            send("x" * (5 * 1024 * 1024) + "\n")
            continue
        elif mode == "partial_reply":
            send(json.dumps(reply)[:30])
            return 0
        elif mode == "error_reply":
            send(json.dumps({"type": "error", "id": request["id"], "message": "scripted internal error"}) + "\n")
            return 5
        elif mode == "refused_reply":
            send(json.dumps({"type": "refused", "id": request["id"], "message": "scripted refusal"}) + "\n")
            continue
        elif mode == "nan_reply":
            send(json.dumps(reply).replace("1.0", "NaN", 1) + "\n")
            continue
        elif mode == "eof_reply":
            return 0
        elif mode == "slow_exit":
            sys.stderr.write("scripted slow exit\n")
            sys.stderr.flush()
            os.close(1)
            time.sleep(0.6)
            os._exit(7)
        elif mode == "quiet_slow_exit":
            os.close(1)
            os.close(2)
            time.sleep(0.6)
            os._exit(7)
        elif mode in ("reply_at_bound", "reply_over_bound"):
            text = json.dumps(reply)
            size = bound if mode == "reply_at_bound" else bound + 1
            send(text + " " * (size - len(text)) + "\n")
            continue
        elif mode == "hang_reply":
            time.sleep(3600)
        send(json.dumps(reply) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
