# claudectl is now archeus

This release installs [**archeus**](https://pypi.org/project/archeus/) and nothing
else. The project was renamed; the tool, the settings, the memory graphs and the
`claudectl` command all carry on.

```bash
pip install -U claudectl        # or: pipx upgrade claudectl
```

Everything on disk moves itself on the first start — the settings file, the
per-account caches, the agent and skill libraries, every project's working
directory, and the hooks and statusline entries that recorded a path into the
old installation.

New installs should use the new name directly:

```bash
pipx install archeus            # or: pip install archeus
```

Source, documentation and issues: <https://github.com/babarmuhammad/archeus>

MIT licensed.
