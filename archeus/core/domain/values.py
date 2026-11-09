"""Small value types and the closed vocabularies entities are validated against."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ref:
    """A typed reference to any addressable object: `{kind, id}`."""
    kind: str
    id: str

    def __post_init__(self):
        if not (isinstance(self.kind, str) and self.kind and isinstance(self.id, str) and self.id):
            raise ValueError('Ref needs a non-empty kind and id: %r' % (self,))


#: Principal kind -> the scopes it may hold (domain-model §3.3). A brain can
#: propose and never approve; an execution cannot create missions.
PRINCIPAL_SCOPES = {
    'user_device': ('observe', 'control', 'approve', 'admin'),
    'brain': ('propose',),
    'execution': ('report', 'checkpoint', 'request_approval'),
    'automation': ('create_mission',),
    'node': ('node_report',),
    'system': ('system',),
}

SOURCE_KINDS = ('user', 'brain', 'execution', 'inspection', 'import', 'automation', 'legacy')
ORIGINS = ('explicit', 'inferred')
