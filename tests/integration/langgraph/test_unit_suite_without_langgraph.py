"""The core unit suite runs with the LangGraph family unimportable (decisions.md D-116).

D-116: LangGraph is an optional extra and the core stays usable without it, tests included. This runs the whole ``tests/unit`` tree in a fresh
interpreter where importing ``langgraph``, ``langchain``, ``langchain_core`` or ``langsmith`` raises, and requires it to pass and to have loaded
none of them. It lives under ``tests/integration`` because it *starts* pytest: inside ``tests/unit`` it would run itself.

It exists because a unit test once reached LangGraph through a shared test helper and nothing noticed until this was run by hand.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SCRIPT = r"""
import sys
BLOCKED = ('langgraph', 'langchain', 'langchain_core', 'langsmith')


class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in BLOCKED:
            raise ImportError('blocked: ' + name)


sys.meta_path.insert(0, Block())
import pytest

code = pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/unit'])
loaded = sorted(m for m in sys.modules if m.split('.')[0] in BLOCKED)
print('LOADED', loaded)
sys.exit(code)
"""


def test_every_core_unit_test_passes_with_langgraph_langchain_and_langsmith_unimportable():
    result = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, cwd=ROOT, timeout=280)

    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "LOADED []"
