# Contributing to Linux Peripherals Controller

Everybody is invited and welcome to contribute to Linux Peripherals Controller. Even if you are not a developer, perhaps you would like to help with the documentation? If you are a developer and have a feature that isn't supported by LPC yet, why not spend some time and help to integrate it?

The process is straight-forward.

- Fork the LPC repository.
- Write the code for your feature or fix.
- Ensure tests pass and linting succeeds (`./script/lint` and `./script/tests`).
- Write docstrings in Sphinx style with `:param:` (see the Code Quality Checks section in the README).
- Create a Pull Request against the `main` branch.
- For a breaking change, tick "Breaking change" and fill the "Breaking change migration" section of the PR description. It is copied to `breaking_change.md` on merge and into the release notes.

## Feature suggestions

If you want to suggest a new feature for LPC, please open a discussion on GitHub.

## Issue Tracker

If you want to report an issue, please create an issue on the repository.

## AI Policy

Linux Peripherals Controller is an [Open Home Foundation](https://www.openhomefoundation.org/) project and follows the [OHF AI Policy](https://github.com/music-assistant/.github/blob/main/AI_POLICY.md). Please read it before submitting AI-assisted contributions. The TLDR: AI tools are allowed, but a human is responsible and must review and understand every change. Autonomous agents and unreviewed AI output will be rejected.