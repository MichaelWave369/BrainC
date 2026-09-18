# Third-Party Notices

BrainC is MIT-licensed for project-owned code. Its dependencies and external services remain independent works under their upstream licenses.

This file is informational and does not replace upstream license texts.

## Python runtime dependencies

BrainC currently declares dependencies including:

- FastAPI
- Uvicorn
- HTTPX
- aiosqlite
- Pydantic
- sentence-transformers
- NumPy
- datasets
- transformers
- Beautiful Soup
- python-multipart
- aiofiles
- python-jose
- bcrypt
- passlib
- python-dotenv
- structlog
- slowapi
- psutil
- colorama

Before distributing a bundled or vendored environment, review the exact installed versions and preserve all notices required by those upstream projects.

## Fine-tuning dependencies

The optional fine-tuning stack references:

- Unsloth
- TRL
- PEFT
- Accelerate
- bitsandbytes
- datasets
- transformers
- PyTorch (installed separately)

These packages are not relicensed by BrainC.

## SearXNG

BrainC includes Docker configuration for a separate SearXNG service.

SearXNG is an independent project licensed under the GNU Affero General Public License (AGPL-3.0-or-later). BrainC's MIT license does not relicense SearXNG.

The repository does not vendor the SearXNG application source; it references the upstream container image/configuration.

## Docker and external software

Docker images, Ollama, model runtimes, browsers, CUDA components, llama.cpp, and other external tools retain their own licenses and terms.

## Release rule

If a future release vendors third-party source, binaries, fonts, media, model weights, or datasets, add their exact source/version and required notices here before release.
