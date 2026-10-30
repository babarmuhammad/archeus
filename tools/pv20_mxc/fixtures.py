"""No-follow fixture validation and closed policy generation."""

import json
import os
from pathlib import Path
import stat
from uuid import UUID


class Refused(ValueError):
    pass


def inspect(path):
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise Refused('Link or reparse point')
    if stat.S_ISREG(info.st_mode):
        if info.st_nlink != 1:
            raise Refused('Multiply linked or unknown-link-count file')
    elif not stat.S_ISDIR(info.st_mode):
        raise Refused('Unsupported filesystem object')
    return info


def ancestors(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Refused('Absolute normalized path required')
    for part in (*reversed(path.parents), path):
        inspect(part)
    return path


def scan(path):
    path = ancestors(path)
    pending = [path]
    while pending:
        current = pending.pop()
        if stat.S_ISDIR(inspect(current).st_mode):
            with os.scandir(current) as entries:
                pending.extend(Path(entry.path) for entry in entries)


def create_root(parent, fixture_uuid):
    parent = ancestors(parent)
    if str(UUID(fixture_uuid)) != fixture_uuid:
        raise Refused('Canonical UUID required')
    root = parent / fixture_uuid
    root.mkdir(exist_ok=False)
    write_json(root / '.pv20-created', {'fixture_uuid': fixture_uuid})
    for name in ('runtime', 'p/workspace', 'p/config', 'p/temp', 'p/requests',
                 'q/workspace', 'q/config', 'q/temp', 'q/requests', 'responses',
                 'sentinels', 'spawn-config', 'verifier', 'core-private',
                 'authority-fixtures', 'evidence'):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path, data):
    path = Path(path)
    ancestors(path.parent)
    encoded = json.dumps(data, sort_keys=True, allow_nan=False).encode('utf-8')
    if len(encoded) > 262144:
        raise Refused('JSON exceeds evidence limit')
    with path.open('xb') as stream:
        stream.write(encoded)


def policy(root, *, command_line, systemroot, timeout_ms=10000, ui=False,
           proxy_port=None, peer='p'):
    root = ancestors(root)
    if peer not in ('p', 'q') or type(ui) is not bool:
        raise Refused('Invalid peer or UI policy')
    if type(timeout_ms) is not int or not 0 < timeout_ms <= 600000:
        raise Refused('Invalid process deadline')
    if not command_line or '\0' in command_line:
        raise Refused('Explicit command line required')
    systemroot = Path(systemroot)
    if not systemroot.is_absolute() or '..' in systemroot.parts:
        raise Refused('Explicit absolute SYSTEMROOT required')
    rw = [root / peer / name for name in ('workspace', 'config', 'temp', 'requests')]
    ro = [root / name for name in ('runtime', 'responses', 'sentinels', 'spawn-config')]
    for grant in rw + ro:
        scan(grant)
    env = {'SYSTEMROOT': str(systemroot)}
    env.update({key: str(root / peer / 'config')
                for key in ('LOCALAPPDATA', 'USERPROFILE', 'HOME')})
    env.update({key: str(root / peer / 'temp') for key in ('TEMP', 'TMP')})
    result = {
        'version': '1.0.0', 'containment': 'processcontainer',
        'lifecycle': {'destroyOnExit': True, 'preservePolicy': False},
        'process': {'commandLine': command_line, 'cwd': str(rw[0]),
                    'env': [f'{k}={v}' for k, v in env.items()],
                    'inheritDefaultEnv': False, 'timeout': timeout_ms},
        'filesystem': {'readwritePaths': list(map(str, rw)),
                       'readonlyPaths': list(map(str, ro)),
                       'deniedPaths': [str(root / name) for name in
                                       ('q' if peer == 'p' else 'p', 'verifier',
                                        'core-private', 'authority-fixtures', 'evidence')]},
        'network': {'egress': {'default': 'deny'},
                    'ingress': {'default': 'deny', 'hostLoopback': 'deny'}},
        'ui': {'disable': not ui, 'clipboard': 'none', 'injection': False},
        'telemetry': {'enabled': False},
    }
    if proxy_port is not None:
        if type(proxy_port) is not int or not 1 <= proxy_port <= 65535:
            raise Refused('Invalid fixture proxy port')
        result['network']['ingress'] = {'default': 'allow', 'hostLoopback': 'allow'}
        result['runtimeConfig'] = {'networkProxy': f'http://127.0.0.1:{proxy_port}'}
        result['processContainer'] = {'capabilities': ['internetClient']}
    return result


def launch_scan(root, compiled):
    root = ancestors(root)
    for key in ('readwritePaths', 'readonlyPaths'):
        for grant in compiled['filesystem'][key]:
            path = Path(grant)
            if path == root or not path.is_relative_to(root):
                raise Refused('Grant outside fixture or broad root grant')
            scan(path)


def origin_matches(accepted, current):
    return (accepted.get('alive') is True and current.get('alive') is True
            and type(accepted.get('pid')) is int and accepted['pid'] > 0
            and accepted.get('creation_time') is not None
            and accepted['pid'] == current.get('pid')
            and accepted['creation_time'] == current.get('creation_time')
            and current.get('outer_job_member') is True
            and current.get('launcher_ancestry_verified') is True)


def launcher_argv(exe, policy_path):
    exe = Path(exe)
    policy_path = Path(policy_path)
    if not exe.is_absolute() or not policy_path.is_absolute():
        raise Refused('Absolute launcher and policy paths required')
    if exe.name.lower() != 'wxc-exec.exe':
        raise Refused('Pinned MXC launcher required')
    return [str(exe), '--debug', str(policy_path)]
