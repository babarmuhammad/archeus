from dataclasses import dataclass


@dataclass(frozen=True)
class Pv20Switches:
    origin_enforcement: bool = False
    production_dispatch: bool = False
    confined_verification: bool = False
    native_run: bool = False
    heartbeat: bool = False
    host: bool = False
    broker_dispatch: bool = False
    a4: bool = False
    store_fetch: bool = False
    isolated_dispatch: bool = False

    def __post_init__(self):
        values = tuple(vars(self).values())
        if any(type(value) is not bool for value in values) or len(set(values)) != 1:
            raise ValueError('PV-20 switches must all be closed or all be open')


def checked(switches):
    if switches is not None and type(switches) is not Pv20Switches:
        raise TypeError('switches must be a Pv20Switches or None')
    return switches


def enabled(switches, name, default=False):
    return default if checked(switches) is None else getattr(switches, name)
