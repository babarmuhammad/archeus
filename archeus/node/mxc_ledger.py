import hashlib
import json
import os
import re

from claude_sessions import config

from ..infra.paths import VERIFY_KEY, verify_key_parts


DEAD_CLEAN = 'DEAD_CLEAN'
DEAD_UNVERIFIED = 'DEAD_UNVERIFIED'
STILL_RUNNING = 'STILL_RUNNING'
UNKNOWN_OWNER = 'UNKNOWN_OWNER'


def journal_name(key, process_seq):
    """The one journal name of a process generation. A resume is another process of the
    same execution and a verifier key holds `/` and `.`, so neither can be the name as it
    is. An execution key holds no `-` and cannot start `verify_`, so the suffix and the
    verifier form each name one thing."""
    if type(process_seq) is not int or process_seq < 1:
        raise ValueError('invalid process generation')
    if isinstance(key, str) and key.startswith(VERIFY_KEY):
        vid, attempt = verify_key_parts(key)
        base = 'verify_%s_%d' % (vid, attempt)
    elif isinstance(key, str) and re.fullmatch('[A-Za-z0-9_]+', key) and not key.startswith('verify_'):
        base = key
    else:
        raise ValueError('invalid execution key')
    return '%s-p%d' % (base, process_seq)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _line(record):
    payload = _json(record)
    return _json({'length': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                  'record': record}) + b'\n'


def _validate(record, previous):
    op = record['op']
    ops = [r['op'] for r in previous]
    fields = {'execution_id', 'op', 'seq'}
    if type(record['seq']) is not int:
        raise ValueError('invalid sequence')
    if op == 'intent':
        fields |= {'requested_policy_digest', 'planned', 'applied', 'observed'}
        if (ops or not isinstance(record['planned'], list) or record['applied'] != []
                or record['observed'] != {}):
            raise ValueError('invalid intent')
    elif op == 'ownership':
        fields |= {'pid', 'create_time', 'requested_policy_digest', 'applied', 'observed', 'owned'}
        if (ops != ['intent'] or type(record['pid']) is not int or record['pid'] <= 0
                or type(record['create_time']) is not int or record['create_time'] <= 0
                or record['requested_policy_digest'] != previous[0]['requested_policy_digest']
                or not isinstance(record['applied'], list)
                or not isinstance(record['observed'], dict)
                or not isinstance(record['owned'], list)):
            raise ValueError('invalid ownership')
    elif op == 'disposal':
        fields.add('verified_absent')
        if ops != ['intent', 'ownership'] or record['verified_absent'] is not True:
            raise ValueError('invalid disposal')
    elif op == 'completion':
        fields.add('outcome')
        if ops != ['intent', 'ownership', 'disposal'] or type(record['outcome']) is not int:
            raise ValueError('invalid completion')
    elif op == 'quarantine':
        fields.add('reason')
        if not isinstance(record['reason'], str) or not record['reason']:
            raise ValueError('invalid quarantine')
    if set(record) != fields:
        raise ValueError('invalid record fields')
    if 'requested_policy_digest' in record:
        digest = record['requested_policy_digest']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('invalid requested policy digest')


def read_records(data, execution_id):
    if not isinstance(data, bytes):
        return [], True
    records, invalid = [], False
    for line in data.splitlines(keepends=True):
        try:
            envelope = json.loads(line)
            record = envelope['record']
            payload = _json(record)
            if (not line.endswith(b'\n') or set(envelope) != {'length', 'sha256', 'record'}
                    or envelope['length'] != len(payload)
                    or envelope['sha256'] != hashlib.sha256(payload).hexdigest()
                    or record['execution_id'] != execution_id
                    or record['op'] not in ('intent', 'ownership', 'disposal', 'completion',
                                             'quarantine')
                    or record['seq'] != len(records)):
                raise ValueError('invalid ledger record')
            _validate(record, records)
            records.append(record)
        except Exception:
            invalid = True
    return records, invalid


def reconcile(journals, process_reader, resource_reader):
    """Readers return PID creation time (None if absent), and explicit resource absence.

    Resource reader receives execution ID and returned ownership, never planned grants.
    No reader may mutate or terminate processes. Missing ownership cannot prove death.
    """
    results = {}
    for execution_id, data in journals.items():
        records, invalid = read_records(data, execution_id)
        ops = [r['op'] for r in records]
        state = DEAD_UNVERIFIED
        try:
            if invalid or 'quarantine' in ops:
                pass
            elif not ops or ops[0] != 'intent' or ops.count('intent') != 1:
                pass
            elif 'completion' in ops:
                if ops[-1] == 'completion' and 'disposal' in ops:
                    continue
            else:
                owners = [r for r in records if r['op'] == 'ownership']
                if len(owners) == 1:
                    owner = owners[0]
                    pid, created = owner['pid'], owner['create_time']
                    if type(pid) is not int or pid <= 0 or type(created) is not int or created <= 0:
                        raise ValueError('invalid launcher identity')
                    current = process_reader(pid)
                    if current is None:
                        if resource_reader(execution_id, owner) is True:
                            state = DEAD_CLEAN
                    elif type(current) is not int or current <= 0:
                        raise ValueError('invalid process observation')
                    elif current != created:
                        state = UNKNOWN_OWNER
                    else:
                        state = STILL_RUNNING
        except Exception:
            state = DEAD_UNVERIFIED
        results[execution_id] = state
    return results


class Ledger:
    # One Core writer owns this private directory; checksums detect damage, not hostile rewrites.
    def __init__(self, root):
        self.root = os.fspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, execution_id):
        if not isinstance(execution_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', execution_id):
            raise ValueError('invalid execution ID')
        return os.path.join(self.root, execution_id + '.jsonl')

    def journals(self):
        result = {}
        for name in os.listdir(self.root):
            if name.endswith('.jsonl'):
                execution_id = name[:-6]
                try:
                    with open(self._path(execution_id), 'rb') as stream:
                        result[execution_id] = stream.read()
                except Exception:
                    result[execution_id] = b'invalid\n'
        return result

    def append(self, execution_id, op, **facts):
        path = self._path(execution_id)
        # NTFS holds one file for two names that differ only by case, so they are one name
        if any(
                name[:-6] != execution_id and name[:-6].casefold() == execution_id.casefold()
                for name in os.listdir(self.root) if name.endswith('.jsonl')):
            raise ValueError('journal name collides with another by case')
        fresh = not os.path.exists(path)
        if fresh:
            if op != 'intent':
                raise ValueError('intent required')
            if not config.write_atomic(path, '', mode=0o600):
                raise OSError('ledger initialization failed')
        with open(path, 'rb') as stream:
            data = stream.read()
        torn = op == 'quarantine' and bool(data) and not data.endswith(b'\n')
        records, invalid = read_records(data + b'\n' if torn else data, execution_id)
        if invalid and op != 'quarantine':
            raise ValueError('corrupt ledger requires quarantine')
        ops = [r['op'] for r in records]
        allowed = {'intent': not data, 'ownership': ops == ['intent'],
                   'disposal': ops == ['intent', 'ownership'],
                   'completion': ops == ['intent', 'ownership', 'disposal'],
                   'quarantine': True}
        if not allowed.get(op, False) or 'quarantine' in ops:
            raise ValueError('invalid ledger transition')
        record = dict(facts, execution_id=execution_id, op=op, seq=len(records))
        _validate(record, records)
        encoded = _line(record)
        with open(path, 'ab') as stream:
            if torn:
                stream.write(b'\n')
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if fresh and os.name != 'nt':
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return record

    def create(self, execution_id, requested_policy, create, advance, *, planned=()):
        digest = hashlib.sha256(_json(requested_policy)).hexdigest()
        self.append(execution_id, 'intent', requested_policy_digest=digest,
                    planned=list(planned), applied=[], observed={})
        child, facts = create()
        self.append(execution_id, 'ownership', pid=child.pid, create_time=child.create_time,
                    requested_policy_digest=digest, applied=facts['applied'],
                    observed=facts['observed'], owned=facts['owned'])
        advance(child)
        return child

    def dispose(self, execution_id, dispose, absent):
        records, invalid = read_records(self.journals()[execution_id], execution_id)
        if invalid or [r['op'] for r in records] != ['intent', 'ownership']:
            raise ValueError('verified ownership required')
        owner = records[-1]
        try:
            dispose(owner)
            if absent(owner) is not True:
                raise ValueError('disposal unverified')
        except Exception:
            self.append(execution_id, 'quarantine', reason='disposal_unverified')
            raise
        self.append(execution_id, 'disposal', verified_absent=True)

    def complete(self, execution_id, outcome):
        self.append(execution_id, 'completion', outcome=outcome)

    def reconcile(self, process_reader, resource_reader, *, skip=()):
        journals = {name: data for name, data in self.journals().items() if name not in skip}
        results = reconcile(journals, process_reader, resource_reader)
        for execution_id, state in results.items():
            records, _ = read_records(journals[execution_id], execution_id)
            if state == DEAD_UNVERIFIED and not any(r['op'] == 'quarantine' for r in records):
                self.append(execution_id, 'quarantine', reason='restart_unverified')
        return results
