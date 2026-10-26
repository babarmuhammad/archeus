// The command line's grammar, DOM free. A slash command is "/name rest"; plain text goes to Archeus; "name" alone is a place.
// It only reads the shared command table in sim.js (English names, Italian aliases); sim.say() is what runs a command.
import { COMMANDS, findCommand } from '../../sim.js';

export function parse(text) {
  const t = String(text || '').trim();
  if (!t) return { kind: 'empty' };
  if (t.startsWith('//')) return { kind: 'tell', text: t.slice(1) };
  if (!t.startsWith('/')) return { kind: 'text', text: t };
  const sp = t.indexOf(' '), name = sp < 0 ? t.slice(1) : t.slice(1, sp), arg = sp < 0 ? '' : t.slice(sp + 1).trim(), cmd = findCommand(name);
  if (!cmd) return { kind: 'unknown', name, text: t };
  if (!cmd.args && arg) return { kind: 'error', cmd, reason: '/' + cmd.name + ' takes no argument.', text: t };
  return { kind: 'command', cmd, arg, text: t };
}

// the commands a prefix could still become, in the user's language
export function complete(buf, lang) {
  const q = buf.slice(1).toLowerCase();
  return COMMANDS.filter((c) => !q || c.name.startsWith(q) || c.it.startsWith(q)).map((c) => ({ cmd: c, insert: '/' + (lang === 'it' ? c.it : c.name) + (c.args ? ' ' : ''), label: '/' + (lang === 'it' ? c.it : c.name) + (c.args ? ' ' + c.args : ''), cls: c.cls, desc: c.desc }));
}
