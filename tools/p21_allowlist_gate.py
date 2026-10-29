import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archeus.core.execution.command_allowlist import ROWS  # noqa: E402

BEGIN = '<!-- command-allowlist:begin -->'
END = '<!-- command-allowlist:end -->'
MODES = {
    'none': 'none', 'P*': '`P*`', 'F+': '`F+`',
    'search': '`search` (literal `--`, then `L`, then `P+`)',
    'optional_paths': '`optional_paths` (none, or `--` then `P+`)',
    'optional_head': '`optional_head` (none, or `HEAD`)', 'head': '`head` (`HEAD` only)',
}


def generated_table(rows=ROWS):
    lines = [
        '<!-- GENERATED from archeus/core/execution/command_allowlist.py ROWS. Do not hand-edit. -->',
        '',
        '| ID | Program | Fixed prefix (exact, in order) | Complete option vectors (exactly one, before the operands) | Operands | Class |',
        '|---|---|---|---|---|---|',
    ]
    for row in rows:
        prefix = '`' + ' '.join(row.prefix) + '`' if row.prefix else '—'
        options = ' · '.join('`' + ' '.join(vector) + '`' if vector else '(no options)'
                             for vector in row.options)
        cls = '**exec**' if row.action_class == 'exec' else row.action_class
        lines.append(f'| {row.id} | {row.program} | {prefix} | {options} | {MODES[row.operands]} | {cls} |')
    return '\n'.join(lines)


def check_gate(text, rows=ROWS):
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('gate must contain one generated allow-list block')
    block = text.split(BEGIN)[1].split(END)[0].strip()
    if block != generated_table(rows):
        raise ValueError('gate allow-list table drift')


if __name__ == '__main__':
    print(generated_table())
