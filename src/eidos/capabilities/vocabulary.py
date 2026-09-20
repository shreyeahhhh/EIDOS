"""The V0.4 capability vocabulary (decisions.md D-132, D-144).

Five capability IDs, exactly as ruled by the owner: ``architecture``, ``security``, ``cost``, ``research`` and
``verification`` — lowercase, matched by exact string. This is a **V0.4-only** set. It is not a global vocabulary and it
does not answer D-007 (hierarchy, similarity, ownership and a cross-mission list all stay Open).

``verification`` is a member of the set that **no work agent serves**: the Verification Agent is reached through the
``Verifier`` port by ``VERIFY`` node kind, not by capability (D-133, D-144). An ``agent`` step that requested it is an
unbound capability and is refused before dispatch (D-134).

V0.2 does not use this module. Its capability stage checks a step's capability against the mission's own
``required_capabilities`` (D-102) and knows nothing about which agents exist.
"""

from eidos.contracts import CapabilityId

ARCHITECTURE = CapabilityId("architecture")
SECURITY = CapabilityId("security")
COST = CapabilityId("cost")
RESEARCH = CapabilityId("research")
VERIFICATION = CapabilityId("verification")

V04_CAPABILITIES: tuple[CapabilityId, ...] = (ARCHITECTURE, SECURITY, COST, RESEARCH, VERIFICATION)
