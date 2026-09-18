# Contributing to BrainC

Thank you for contributing to BrainC.

## License

Project-owned BrainC code and documentation are released under the MIT License unless otherwise noted.

By submitting a contribution for inclusion, you agree that your contribution may be distributed under MIT and represent that you have the right to submit it under those terms.

Do not submit third-party code, model weights, datasets, media, credentials, private conversation data, or other material unless you have the right to do so and all required notices are included.

## Public-release hygiene

Before opening a pull request:

1. do not commit `.env`, secrets, tokens, private keys, databases, logs, backups, model weights, or exported conversation datasets;
2. keep local runtime state outside Git;
3. update `THIRD_PARTY_NOTICES.md` for new bundled third-party material;
4. update `MODEL_LICENSES.md` for model or dataset changes;
5. run the public-release CI checks.

## Architecture direction

BrainC is a donor system for PhiOS and PhiVessel.

New work should preserve the distinction between capability and authority. In particular, code execution, filesystem mutation, network actions, and future external side effects should be designed so they can sit behind explicit PhiOS Action Gate grants rather than assuming historical BrainC tool permission is sufficient.
