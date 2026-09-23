"""Integration-level architectural boundary checks for V0.8 Step 6.

Complements, and does not replace, the existing per-package guards (``tests/unit/planning/test_planning_guards.py``,
``tests/unit/selectors/test_selectors_guards.py``): those check each package's own source in isolation; this file
checks what actually happens when a real caller uses **both together** to run a real selection, and that the
V0.8 Step 6 files in this directory never reach for the Plan/execution layer, proving "no Plan is generated or
executed by this step" structurally rather than only by claim.

**V0.9 Step 3 deliberately, legitimately widens what this directory as a whole covers**: its own file,
``test_strategy_to_telemetry_integration.py``, exists specifically to compile and execute a real, expanded Plan —
the opposite claim from this file's own. The check below is scoped to the four V0.8 Step 6 files it was written
for, not to every ``test_*.py`` this directory will ever hold; each later step's own integration proof states its
own boundary in its own file, the way ``test_strategy_to_telemetry_integration.py`` does in its own docstring.

**V1.0 Step 4 (D-198) deliberately revises, not weakens, this file's own two ``eidos.selectors``-dependency
checks**: written before ``eidos.memory`` existed, they correctly forbade it; ``ExperienceInformedSelector`` now
legitimately depends on it (and, transitively, on ``eidos.state``/``eidos.telemetry``, mirroring the
``compiler``/``runtime``/``capabilities`` exception already established below for ``eidos.agents``) — the exact
same class of correction this project has made every time a guard's own original assumption became genuinely
false on purpose.
"""

import ast
import subprocess
import sys
from pathlib import Path

TESTS_PLANNING = Path(__file__).resolve().parent
SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"

# The four files V0.8 Step 6 itself added — explicitly about the selection boundary only, never the Plan/execution
# layer. NOT every test_*.py this directory will ever hold: V0.9 Step 3's own file exists specifically to compile
# and execute a real Plan, the opposite claim, and states its own boundary separately (its own module docstring).
_V0_8_STEP_6_FILES = {
    "test_selection_pipeline.py",
    "test_model_assisted_selection.py",
    "test_selector_comparison.py",
    "test_selection_integration_boundaries.py",
}
FORBIDDEN_LAYERS_IN_THIS_SUITE = {"compiler", "runtime", "backends", "baseline"}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(node.module or "")
    return found


def test_this_integration_suite_never_imports_the_plan_or_execution_layer():
    for path in sorted(TESTS_PLANNING.glob("test_*.py")):
        if path.name not in _V0_8_STEP_6_FILES:
            continue
        for name in imports_of(path):
            parts = name.split(".")
            assert not (len(parts) > 1 and parts[0] == "eidos" and parts[1] in FORBIDDEN_LAYERS_IN_THIS_SUITE), \
                f"{path.name} imports {name}"


def test_using_planning_and_selectors_together_loads_no_forbidden_dependency():
    # A real, combined run of the actual selection boundary (candidate generation, feasibility, both Selector
    # implementations, with a ScriptedModel standing in for the model call) — proving the two packages' own
    # per-file guards also hold true of the actual composed import graph, not just each file read in isolation.
    # Deliberately builds every contract inline via bare eidos.contracts/eidos.validation constructors, never
    # through tests/support's own factory hub: that hub is shared across the whole test suite and legitimately
    # imports eidos.compiler/eidos.runtime/eidos.capabilities for unrelated (Plan-level) factories, which would
    # otherwise show up in sys.modules here as a false positive about this suite's own test-support dependency,
    # not about what eidos.planning/eidos.selectors themselves load.
    #
    # eidos.compiler/eidos.runtime/eidos.capabilities are deliberately NOT in the forbidden list below: eidos.agents
    # (needed for ModelPort, D-190) already, legitimately, imports them for its own unrelated WorkAgent/artifact
    # concerns (pre-existing V0.4 architecture, untouched by V0.8) — checked directly (this subprocess reproduced
    # the failure with them included, confirming they load only via eidos.agents, never via eidos.planning or
    # eidos.selectors themselves, both of which the per-package guards already prove never import compiler/
    #
    # eidos.state/eidos.telemetry/eidos.memory are deliberately, additionally, NOT in the forbidden list either
    # (V1.0 Step 4, D-198): eidos.selectors.experience_informed legitimately imports eidos.memory, which itself
    # legitimately depends on eidos.state and eidos.telemetry (mirrors eidos.telemetry's own dependency shape,
    # confirmed by eidos.memory's own guard tests) — the same "an approved adapter dependency transitively pulls
    # in what it needs" reasoning already established for compiler/runtime/capabilities above, one dependency
    # further. The per-package guards (test_selectors_guards.py, test_memory_guards.py) already prove neither
    # eidos.planning nor the rest of eidos.selectors imports any of these directly.
    # runtime/capabilities directly). What this check is actually for — a real protocol/vendor/storage boundary
    # this step could plausibly violate — is the list that remains.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "from uuid import UUID\n"
        "from eidos.contracts import CapabilityId, MissionId, ReliabilityContract, ReliabilityContractId, RiskLevel, AutonomyLevel, TaskGenome, TenantId\n"
        "from eidos.validation.limits import SystemLimits\n"
        "from eidos.planning import RuleBasedCandidateGenerator, DeterministicSelector, generate_candidate_strategies, select_strategy\n"
        "from eidos.selectors import ModelAssistedSelector\n"
        "from eidos.agents import ModelResponse, ModelSettings, GenerationParameters\n"
        "\n"
        "class Scripted:\n"
        "    def complete(self, request):\n"
        "        return ModelResponse(text='[[CANDIDATE_1]]')\n"
        "\n"
        "class FixedIds:\n"
        "    def __init__(self):\n"
        "        self._n = 0\n"
        "    def next_strategy_id(self):\n"
        "        self._n += 1\n"
        "        return UUID(int=9_000_000 + self._n)\n"
        "\n"
        "tenant = TenantId(UUID(int=1))\n"
        "contract = ReliabilityContract(tenant_id=tenant, contract_id=ReliabilityContractId(UUID(int=2)), min_quality=0.9, max_risk_level=RiskLevel.MEDIUM, min_independent_evidence=1)\n"
        "genome = TaskGenome(tenant_id=tenant, goal='integration check', required_capabilities=(CapabilityId('research'), CapabilityId('cost')), risk_level=RiskLevel.MEDIUM, autonomy_level=AutonomyLevel.SAFE_READ_ONLY, allowed_actions=(), reliability_contract_id=contract.contract_id)\n"
        "limits = SystemLimits(max_nodes=50, max_depth=10, max_parallel_branches=8, max_retries=3, max_replans=2, max_agent_calls=20, max_tool_calls=40, max_execution_time=60000, max_tokens=5000)\n"
        "\n"
        "generation = generate_candidate_strategies(\n"
        "    RuleBasedCandidateGenerator(), genome, mission_id=MissionId(UUID(int=3)), reliability_contract=contract,\n"
        "    limits=limits, max_candidates=3, ids=FixedIds(),\n"
        ")\n"
        "settings = ModelSettings(model='test-model', parameters=GenerationParameters(temperature=0.0, seed=1, max_output_tokens=64), timeout_seconds=5.0)\n"
        "det_result = select_strategy(DeterministicSelector(), generation.candidates, genome)\n"
        "model_result = select_strategy(ModelAssistedSelector(model=Scripted(), settings=settings), generation.candidates, genome)\n"
        "assert det_result.outcome.value == 'selected'\n"
        "assert model_result.outcome.value == 'selected'\n"
        "\n"
        "forbidden_prefixes = ('eidos.a2a', 'eidos.recording', 'eidos.backends', 'eidos.providers', 'eidos.baseline')\n"
        "forbidden_vendors = ('langgraph', 'langchain', 'langsmith', 'httpx', 'requests', 'mcp')\n"
        "loaded = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m.startswith(forbidden_prefixes) or m.split('.')[0] in forbidden_vendors\n"
        ")\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_eidos_planning_still_never_imports_eidos_selectors_from_this_integration_suites_own_dependency_graph():
    # A narrower, direct restatement of the check above for the specific pairing this step introduces.
    for path in sorted((SRC / "planning").glob("*.py")):
        for name in imports_of(path):
            assert "selectors" not in name.split("."), f"{path.name} imports {name}"


def test_eidos_selectors_depends_only_on_agents_contracts_planning_and_memory():
    # V1.0 Step 4 (D-198) adds eidos.memory: ExperienceInformedSelector legitimately consumes ExperienceStore,
    # mirroring test_selectors_guards.py's own identical, deliberate ALLOWED_EIDOS revision.
    for path in sorted((SRC / "selectors").glob("*.py")):
        for name in imports_of(path):
            if name.startswith("eidos"):
                assert ".".join(name.split(".")[:2]) in {"eidos.agents", "eidos.contracts", "eidos.memory", "eidos.planning"}, \
                    f"{path.name} imports {name}"
