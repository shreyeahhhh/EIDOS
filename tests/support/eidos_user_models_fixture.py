"""A service rig that accepts a model of the user's own (decisions.md D-246): shared by the service and API tests of bring-your-own-key.

The factory records every (provider, key) it is handed and returns a scripted model, so a test can say which model a run used and which key built it. Nothing here touches a network or a credential.
"""

from eidos.service import MissionService, ModelChoice, RunnerConfig, UserModels

from eidos_agents_factories import ScriptedModel
from eidos_search_fixture import cite_every_document
from eidos_service_fixture import make_rig, make_spec

KEY = "sk-test-0123456789ABCDEFGH"


class UserRig:
    """A service rig whose service accepts a model of the user's own, from a factory that records what it was given and hands back a scripted model."""

    def __init__(self, providers=("openai", "gemini", "groq"), respond=cite_every_document, **rig_kwargs):
        self.rig = make_rig(runner=RunnerConfig(flush_backoff_seconds=0.0, max_active_runs_per_tenant=3, worker_pool_size=3), **rig_kwargs)
        self.built: list[tuple[str, str, ScriptedModel]] = []
        self._respond = respond

        def factory(provider, key):
            model = ScriptedModel(self._respond)
            self.built.append((provider, key, model))
            return model

        self.factory = factory
        self.rig.service = MissionService(
            repositories=self.rig.storage.repositories(), runner=self.rig.runner, composition=self.rig.composition, config=self.rig.config,
            user_models=UserModels(providers=frozenset(providers), factory=factory),
        )
        self.service = self.rig.service

    def mission(self, who="alice", **spec):
        context = self.rig.context(who)
        return context, self.service.create_mission(context, make_spec(**spec))[0].mission_id

    def stored_text(self, context, mission_id) -> str:
        records = self.rig.storage.read(context.tenant_id, mission_id)
        events = " ".join(record.model_dump_json() if hasattr(record, "model_dump_json") else repr(record) for record in records)
        return events + " " + repr(self.rig.storage.repositories().missions.get(context.tenant_id, mission_id))


def choice(provider="openai", model="a-model", key=KEY) -> ModelChoice:
    return ModelChoice(provider=provider, model=model, api_key=key)



__all__ = ["KEY", "UserRig", "choice"]
