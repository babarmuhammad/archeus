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

## Availability, checked 2026-09-14

| | |
|---|---|
| npm `archeus` | free |
| crates.io `archeus` | free |
| RubyGems / NuGet / Packagist `archeus` | free |
| PyPI `archeus` | **ours** |
| GitHub user/org `archeus` | **taken** since 2012 by an unrelated account. The repository stays `babarmuhammad/archeus`; there is nothing to claim. |
| Docker Hub user `archeus` | **taken**, zero repositories. Publish as `babarmuhammad/archeus`. |
| `archeus.com` `.dev` `.sh` `.io` `.ai` `.app` | all appear unregistered. The documentation domain is still the previous name's and is deliberately held back in `tools/_rename_brand.py` until one is bought. |

## Publishing

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

Bump its `archeus>=` pin to the release you just published;
`test_the_shim_pins_a_version_that_does_not_exist_yet` fails if it lags.

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
docker build -t babarmuhammad/archeus:2.3.0 -t babarmuhammad/archeus:latest packaging/docker
docker push babarmuhammad/archeus:2.3.0
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
gem push archeus-2.3.0.gem
```

### NuGet

```bash
cd packaging/nuget
nuget pack archeus.nuspec
dotnet nuget push archeus.2.3.0.nupkg --source https://api.nuget.org/v3/index.json --api-key <key>
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
