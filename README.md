# OMM Homebrew Tap

This is the official Homebrew tap for [Open Model Manager](https://github.com/omm-hippo/omm).

## Install

```sh
brew install omm-hippo/omm/omm
```

The package is installed as the `omm` command. Homebrew owns the Python
environment and its dependencies; it does not modify your global Python
installation.

## Update

```sh
brew upgrade omm
```

Tagged OMM releases are published and verified on PyPI before the main
repository notifies this Tap. The Tap validates the signed tag, exact source
commit, and public PyPI source archive. A validated release dispatch prepares a
Formula update PR once its dependencies satisfy their release cooldowns. Only
the main package's release cooldown is bypassed. Scheduled fallback runs retain
Homebrew's normal release cooldown.

Every bump updates the Formula source archive and regenerates its Python
`resource` blocks from the same published `omm-model` version. Pull-request CI
resolves the resources again and fails if a package, URL, or SHA-256 differs,
so a version-only bump cannot be merged. Formula changes are never pushed
directly to `main` by the bump job.

For bump PRs created with the workflow's `GITHUB_TOKEN`, a maintainer must select
**Approve workflows to run** in the PR before CI starts. This is GitHub's
[workflow approval behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow),
separate from reviewing and merging the Formula update.

## Uninstall

```sh
brew uninstall omm
```

Downloaded models and OMM settings under `~/.omm` are preserved when the
formula is removed.

## Alternative two-step install

```sh
brew tap omm-hippo/omm
brew install omm
```
