# Publishing archeus under its own name

Everything here is a distribution of the *name*, not of the tool. The tool ships
from the repository root as a Python package; PyPI is the only registry that
carries real code.

Nothing in this directory is built or published by CI. Each one is a deliberate,
credentialed act — run the command when you mean it.

## What is here

| Directory | Registry | What it is |
|---|---|---|
| `npm/` | npm | **A real launcher.** `npx archeus` runs the tool, installing it with pipx or pip first if it is missing, and running it as a module when the command exists but is not on PATH. |
| `docker/` | Docker Hub | **A real image.** slim Python + `pip install archeus`, entrypoint `archeus`. |
| `crates/` | crates.io | Pointer. Prints the real install command and exits non-zero. |
| `rubygems/` | RubyGems | Pointer, same shape. |
| `nuget/` | NuGet | Pointer. No assemblies — the README is the payload. |
| `packagist/` | Packagist | Pointer. **Needs a repository of its own** — see below. |
| `legacy-name/` | PyPI | The final release under the previous name: no code, one console script, one dependency. Its own rules — see the note in its `pyproject.toml`. |

The pointer packages exist for one measured reason: the previous name lost six
of its eight organic search results to an unrelated Rust crate, structurally
(crates.io, docs.rs and lib.rs are three high-authority domains a Python package
is never granted). Owning the name in the ecosystems that rank is cheaper than
out-writing them later.

## Where the name stands, checked 2026-09-15

| | |
|---|---|
| PyPI `archeus` | **ours** — 2.4.0 |
| PyPI `claudectl` (the old name) | **ours** — 1.9.2, the shim: no code, `archeus>=2.4.0`, published 2026-09-15 |
| npm `archeus` | **ours** — 2.4.1 (the launcher runs a patch ahead; see below) |
| RubyGems `archeus` | **ours** — 2.4.0 |
| crates.io / NuGet / Packagist `archeus` | free |
| GitHub user/org `archeus` | **taken** since 2012 by an unrelated account. The repository stays `babarmuhammad/archeus`; there is nothing to claim. |
| Docker Hub user `archeus` | **taken**, zero repositories. Publish as `babarmuhammad/archeus`. |
| `archeus.com` `.dev` `.sh` `.io` `.ai` `.app` | all appear unregistered. The documentation domain is still the previous name's and is deliberately held back in `tools/_rename_brand.py` until one is bought. |

## Publishing

**"Publish the release" means every registry in this table, not just PyPI.** Work
down the list below, publish each one that has a credential and a toolchain on
this machine, and report the ones that do not — a registry skipped in silence is
a name left for somebody else, which is the whole reason this directory exists.
A registry whose version is already current is done, not skipped.

Order matters in exactly one place: **PyPI first, then `legacy-name/`**, because
the shim's pin has to be a version the user does not already have. Everything
else is independent.

### PyPI — the real package

```bash
python -m build
python -m twine upload dist/*
```

### PyPI — the final release under the previous name

```bash
cd packaging/legacy-name
python -m build
python -m twine upload dist/*
```

Set the pin DOWN to the archeus release that just went out, in the built copy
only — the repo file names the NEXT one, which is what
`test_the_shim_pins_a_version_that_does_not_exist_yet` asserts. Build it
somewhere else rather than editing the file, and prove it before uploading: a
clean venv, `pip install <the wheel>`, then check that `claudectl` and `archeus`
both run and that `importlib.metadata.files('claudectl')` lists NO
`claude_sessions` files. That last one is the whole design — a shim that owns
those files deletes the real package's copy of them when it is next uninstalled.

Its `project_urls` name the repository and nothing else, deliberately: this file
is on the rename script's SKIP list, so it may not carry a domain that is still
waiting on the move. Add the site links in the same pass that releases the
documentation domain.

### npm

```bash
cd packaging/npm
npm publish --access public
```

`npm whoami` first. The launcher is worth a real check before every publish,
because its whole job is the case where nothing is installed yet:

```bash
node bin/archeus.js --version
```

### Docker Hub

```bash
docker build -t babarmuhammad/archeus:2.4.0 -t babarmuhammad/archeus:latest packaging/docker
docker push babarmuhammad/archeus:2.4.0
docker push babarmuhammad/archeus:latest
```

### crates.io

```bash
cd packaging/crates
cargo publish
```

`cargo login` first, with a token from <https://crates.io/settings/tokens>.

### RubyGems

```bash
cd packaging/rubygems
gem build archeus.gemspec
gem push archeus-2.4.0.gem
```

`gem signin` first, and **answer `y` to "Do you want to customise scopes?"**, then
enable `push_rubygem`. The default scope is `index_rubygems`, which is read-only:
accept it and the push fails with `This API key cannot perform the specified
action on this gem`, which reads like an ownership problem and is not one.

### NuGet

```bash
cd packaging/nuget
nuget pack archeus.nuspec
dotnet nuget push archeus.2.4.0.nupkg --source https://api.nuget.org/v3/index.json --api-key <key>
```

### Packagist

Packagist reads the `composer.json` at the **root of a git repository**, so
`packaging/packagist/composer.json` cannot be submitted from here. Put it at the
root of a small repository of its own — `babarmuhammad/archeus-packagist` — and
submit that URL at <https://packagist.org/packages/submit>. It does not go at the
root of this repository: every PHP tool that walks a checkout would then treat
this as a PHP project.

## Keeping the versions honest

Every manifest here except `legacy-name/` carries the same version as
`pyproject.toml`, and `test_every_packaging_manifest_declares_the_same_version`
fails when one drifts. A release is one number in several files; a test is
cheaper than remembering which.

`npm/` is the one allowed to run AHEAD, by a patch on the same minor. It is the
only manifest here that ships code of its own, and npm will not let a version be
published twice — so a bug in the launcher alone has to go out under a new
number without dragging a PyPI release behind it. Everything else is a pointer
or an install of the real package, and has no such excuse.
