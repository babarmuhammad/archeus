"""Core's reviewed hash pins for what runs inside MXC (completion plan B0, MXC-R07/R08/R09).

The pins are `mxc_pins.json`, committed beside this module, and nothing else: there is no
path argument, environment variable or setting that names another file. `PINS_DIGEST` is
the SHA-256 of that file's canonical JSON, so a pin changes only in a reviewed commit that
also bumps this constant, and an edited or truncated file refuses everything.

A placeholder (`UNSET`) is a legal value in the file and is never a pin: every use refuses
it, so nothing passes before a reviewer has recorded the real hash.
"""

import hashlib
import json
import os
import re

UNSET = 'UNSET'
PINS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mxc_pins.json')
PINS_DIGEST = '2ebeef49faabcb906c8e2644cc07395727729a504256865bc09283eea7ee8a75'

_HEX = re.compile(r'[0-9a-f]{64}')
_SHAPE = {'pins_version': int, 'mxc_sdk': {'version': str, 'files': dict},
          'policy_schema': {'path': str}, 'claude_code': {'version': str, 'files': dict}}


class PinError(ValueError):
    pass


def digest(pins):
    return hashlib.sha256(json.dumps(pins, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def safe_name(rel):
    return (isinstance(rel, str) and '\\' not in rel and ':' not in rel
            and not any(part in ('', '.', '..') for part in rel.split('/')))


def check_files(files, required, *, allow_unset=False):
    """*files* maps safe relative names to full lowercase SHA-256 hashes, *required*
    among them."""
    if not isinstance(files, dict) or not set(required) <= files.keys() or any(
            not safe_name(rel) for rel in files) or any(
            not (isinstance(value, str) and (_HEX.fullmatch(value)
                                             or allow_unset and value == UNSET))
            for value in files.values()):
        raise PinError('missing or invalid reviewed pins')


def _shaped(value, shape):
    if isinstance(shape, dict):
        return (isinstance(value, dict) and value.keys() == shape.keys()
                and all(_shaped(value[k], shape[k]) for k in shape))
    return type(value) is shape


def load():
    try:
        with open(PINS_FILE, 'rb') as f:
            pins = json.loads(f.read().decode('utf-8'))
    except (OSError, ValueError) as err:
        raise PinError('the reviewed pins cannot be read') from err
    if digest(pins) != PINS_DIGEST:
        raise PinError('the pins file is not the reviewed one: bump PINS_DIGEST with it')
    if not _shaped(pins, _SHAPE) or pins['pins_version'] != 1:
        raise PinError('the pins file has an unknown shape')
    for name in ('mxc_sdk', 'claude_code'):
        check_files(pins[name]['files'], (), allow_unset=True)
        if not pins[name]['files']:
            raise PinError('%s has no pinned files' % name)
    return pins


def artifact(name, *, version=None, required=()):
    """The pinned file hashes of *name*, once nothing in them is UNSET. A *version* is
    the code's own constant and must be the one the file was reviewed for."""
    entry = load()[name]
    if entry['version'] == UNSET or version is not None and entry['version'] != version:
        raise PinError('%s is not pinned at the version this code is reviewed for' % name)
    check_files(entry['files'], required)
    return dict(entry['files'])


def schema_path():
    """Where the SDK holds the pinned policy schema, a file of the reviewed inventory."""
    path = load()['policy_schema']['path']
    if path == UNSET or not safe_name(path):
        raise PinError('the policy schema is not pinned')
    return path
