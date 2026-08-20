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
