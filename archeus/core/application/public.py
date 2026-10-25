from copy import deepcopy

from ..homes import public_value, scrub_text


def system_value(value, homes, *, authored=(), path_keys=(), _path=()):
    # Paths describe content provenance; actor identity and field names alone do not.
    if _path in authored:
        return deepcopy(value)
    if isinstance(value, dict):
        return {k: system_value(v, homes, authored=authored, path_keys=path_keys,
                                _path=(*_path, k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [system_value(v, homes, authored=authored, path_keys=path_keys,
                             _path=_path) for v in value]
    projected = public_value(value, homes, path_keys=path_keys,
                             _key=_path[-1] if _path else None)
    return scrub_text(projected, homes)
