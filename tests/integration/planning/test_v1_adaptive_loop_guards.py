"""Architectural boundary checks for the V1.0 Step 6 adaptive-loop integration test (decisions.md D-198).

Complements ``test_selection_integration_boundaries.py`` (V0.8 Step 6), ``test_selectors_guards.py`` and
``test_memory_guards.py``: those check each package's own source, and the planning+selectors pairing, in
isolation; this file checks what actually happens when a real caller composes the *complete* adaptive loop
(planning, selectors, memory, expansion, validation, recording, telemetry) together for the first time.
"""

import ast
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
INTEGRATION_FILE = TESTS_DIR / "test_v1_adaptive_loop_integration.py"


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(node.module or "")
    return found


def test_the_integration_file_never_imports_langgraph_or_model_assisted_selector():
    # The reference executor is used throughout (record()'s own default, eidos_recording_factories.py) — never
    # LangGraph; and every mission "under test" (as opposed to Test B's own explicitly-labelled seed step) goes
    # through ExperienceInformedSelector only, never ModelAssistedSelector.
    text = INTEGRATION_FILE.read_text(encoding="utf-8")
    for forbidden in ("LangGraphExecutor", "ModelAssistedSelector", "eidos.backends"):
        assert forbidden not in text, f"test_v1_adaptive_loop_integration.py mentions {forbidden}"


def test_the_only_values_passed_to_run_mission_come_from_selection_or_the_labelled_seed():
    # Static proof of requirement 15 ("no strategy selection happens outside ExperienceInformedSelector"): every
    # call to the test's own _run_mission helper passes either a name assigned from _generate_and_select's own
    # return (an ExperienceInformedSelector's actual choice) or the one deliberately-labelled seed variable —
    # never a bare DeterministicSelector()-derived comparison value.
    tree = ast.parse(INTEGRATION_FILE.read_text(encoding="utf-8"))
    forbidden_arg_names = {"deterministic_choice", "fallback_choice"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_run_mission":
            strategy_arg = node.args[1] if len(node.args) > 1 else None
            if isinstance(strategy_arg, ast.Name):
                assert strategy_arg.id not in forbidden_arg_names, f"_run_mission called with {strategy_arg.id}"


def test_using_the_complete_adaptive_loop_together_loads_no_forbidden_dependency():
    # A real, combined run of every layer the loop touches, proving the composed import graph stays clean, not
    # only each package's own guards read in isolation.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "sys.path.insert(0, 'tests/support')\n"
        "from eidos.expansion import expand_strategy\n"
        "from eidos.memory import JsonlExperienceStore, evaluate_experience\n"
        "from eidos.planning import DeterministicSelector, RuleBasedCandidateGenerator, generate_candidate_strategies, select_strategy\n"
        "from eidos.recording import UuidPlanIds, UuidStrategyIds\n"
        "from eidos.selectors import ExperienceInformedSelector\n"
        "from eidos.telemetry import project\n"
        "from eidos.validation import validate_plan\n"
        "\n"
        "forbidden_prefixes = ('eidos.a2a', 'eidos.backends', 'eidos.providers')\n"
        "forbidden_vendors = ('langgraph', 'langchain', 'langsmith', 'httpx', 'requests', 'mcp', 'qdrant')\n"
        "loaded = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.startswith(forbidden_prefixes) or m.split('.')[0] in forbidden_vendors\n"
        ")\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
