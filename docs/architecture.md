# Architecture

## Overview

knowledgeops-mcp is a file I/O layer, nothing more. It exposes three MCP tools to Claude Code: one to scan a folder, one to read its contents, and one to save outputs. All AI reasoning happens inside Claude Code using the user's subscription. The server makes no Anthropic API calls.

This is a deliberate design choice, not a limitation.

---

## Why MCP

MCP (Model Context Protocol) lets Claude Code call external tools natively, without any wrapper scripts or prompt engineering around tool invocation. The model knows what tools are available, what they accept, and what they return. It decides when to call them and in what order.

The alternative — a standalone Python script that calls the API directly — works fine but puts all orchestration logic in the script. MCP inverts that: Claude Code does the orchestration, and the server does only what Claude Code asks it to do. That separation makes the tool composable with other MCP servers (e.g., a GitHub server to auto-commit outputs, or a calendar server to timestamp entries).

---

## Why no API calls in the server

The first version of this tool called the Anthropic API from inside the server. It worked, but it created two problems:

**Billing.** Claude Code uses your subscription. API calls are billed separately per token. Running AI processing inside the server means every use incurs API cost on top of the subscription.

**Data handling.** API calls and Claude Code conversations are governed by different Anthropic policies. Consumer Claude Code conversations are subject to potential training data use (opt-out available in settings). API calls are not. Keeping the AI reasoning inside Claude Code means data handling is governed by one policy, not two.

The tradeoff: the server can no longer report progress during AI processing, and chunking logic for large inputs moves to Claude Code rather than being handled automatically. In practice this is not a meaningful limitation — Claude Code handles large context well.

---

## File I/O design

### Text files
Read with UTF-8 encoding, `errors="replace"` to handle non-UTF-8 content without crashing. Returned as plain text with a filename header so Claude Code knows which file each block came from.

### PDFs
Extracted with `pypdf`. Pages are returned with page number headers. If pypdf is not installed, the server returns a descriptive error rather than crashing. Scanned PDFs (image-only) will return an empty extraction — for those, the image pipeline handles it better.

### Images
Base64-encoded with their MIME type. Claude Code receives them with a note to extract all visible text, commands, and diagrams. This works well for terminal screenshots, network diagrams, and configuration screenshots. It does not require any OCR dependency on the host or in the container.

### Output
Always written to `<folder>/output/`. The directory is created if it does not exist. The `output/` subdirectory is excluded from all scan and read operations to prevent re-processing outputs as inputs.

---

## Path safety

All paths are validated server-side against the notes root (`/notes`). The `_resolve_folder` helper:
- Accepts bare subfolder names (`task4`) or full paths (`/notes/task4`)
- Rejects `..` traversal in input validation (Pydantic `field_validator`)
- Resolves the final path and confirms it stays within `/notes` using `Path.relative_to()`

This matters because the server writes to disk. Even in a personal-use context, defense in depth is worth the few lines.

---

## Transport

The server uses FastMCP's streamable HTTP transport on port 8000. This is the right choice for a containerized server because:
- stdio transport requires subprocess execution, which doesn't work cleanly across a Docker network boundary
- Streamable HTTP works with Claude Code's `--transport http` flag directly
- The container can be started, stopped, and rebuilt independently of Claude Code

---

## Chunking

The earlier API-based version included automatic chunking logic to split large folders into multiple API calls to stay under rate limits. That logic is not needed here — Claude Code handles large context windows natively, and rate limits on the API are not a factor when the AI processing happens inside Claude Code.

If a folder is genuinely massive (hundreds of files), the right approach is to point Claude Code at a subfolder rather than the root.
