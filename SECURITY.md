# Security Policy

BrainC is local-first software with authentication, file access, web search, code execution, and model/tool integration. Those capabilities deserve explicit scrutiny.

## Secrets

Never commit:

- `.env` files;
- JWT signing secrets;
- API tokens;
- private keys;
- user databases;
- backups;
- logs containing sensitive data;
- exported conversation datasets;
- model artifacts containing private training data.

The repository includes `.env.example` only with placeholder values.

## Code execution

BrainC includes a historical code-execution tool with AST checks and subprocess isolation.

Treat it as **untrusted execution infrastructure**, not as a security boundary proven against hostile arbitrary code. Deployments exposed to untrusted users should add OS/container sandboxing and a stricter permission model.

For modern PhiOS integration, code execution should sit behind the Action Gate with explicit grants and receipts.

## File access

The historical file reader is intended to remain inside the configured workspace boundary. Changes affecting path normalization or traversal must receive security review.

## Network exposure

The original deployment model was local-first. If BrainC is exposed beyond localhost:

- rotate all default/example secrets;
- restrict registration;
- configure trusted hosts and reverse-proxy TLS;
- review CORS and authentication;
- isolate the execution tool;
- review SearXNG and MCP endpoints separately.

## Reporting

Do not publish real credentials or personal data in a public issue. Describe the affected component and impact without including live secrets.
