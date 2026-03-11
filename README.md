# knowledgeops-mcp

A Dockerized MCP server that gives Claude Code read/write access to a local notes folder.
Claude Code handles all AI reasoning. The server handles file I/O only — no API calls, no separate billing.

The pattern: drop a folder of raw notes, logs, screenshots, and PDFs into `/home/ubu/notes/`, ask Claude Code to process it, and get back a structured markdown write-up with a self-quiz section and a short project blurb.

Full background, design decisions, and lessons learned are in the [blog post](https://desvert.github.io/2026/03/10/building-a-personal-knowledge-processor-with-mcp-and-claude-code.html).

---

## Architecture

```
Claude Code (your subscription)
    → knowledgeops_scan_folder    read-only inventory of files
    → knowledgeops_read_folder    full file contents returned to Claude Code
    → [Claude Code reasons, writes the output]
    → knowledgeops_save_outputs   write writeup.md + blurb.txt to disk
```

The MCP server is a file I/O layer. It reads text files, extracts PDF text, and base64-encodes images for Claude Code's vision. The model decides what to do with the content — the server does not call the Anthropic API directly.

---

## Tools

| Tool | Read/Write | Description |
|---|---|---|
| `knowledgeops_scan_folder` | Read | Returns file inventory with names, types, sizes. No content. |
| `knowledgeops_read_folder` | Read | Returns full file contents. Text as plain text, images as base64. |
| `knowledgeops_save_outputs` | Write | Writes `writeup.md` and `blurb.txt` to `<folder>/output/`. |

### Supported input types

| Type | Extensions |
|---|---|
| Text / notes | `.txt`, `.md`, `.log`, `.py`, `.sh`, `.yaml`, `.yml`, `.json`, `.csv` |
| Images / screenshots | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` |
| PDFs | `.pdf` |

Images are returned as base64 with their media type — Claude Code processes them natively via vision. No OCR dependency.

---

## Setup

### Prerequisites

- Docker and Docker Compose
- Claude Code (`npm install -g @anthropic-ai/claude-code`)
- A notes folder at `/home/ubu/notes/` (or adjust the volume mount in `docker-compose.yml`)

### 1. Clone the repo

```bash
git clone https://github.com/desvert/knowledgeops-mcp
cd knowledgeops-mcp
```

### 2. Build and start the container

```bash
docker compose up -d --build
```

The server listens on `http://localhost:8000`. Your notes folder is mounted read-write to `/notes` inside the container.

### 3. Connect Claude Code

```bash
claude mcp add --transport http knowledgeops http://localhost:8000/mcp
```

Verify:

```bash
claude mcp list
```

---

## Usage

Start Claude Code in your project or notes directory:

```bash
claude
```

Then describe what you want in natural language:

```
Process my notes in task4 and save the outputs
```

Claude Code will scan the folder, read the files, generate the write-up and blurb, then save both. Outputs land in `<folder>/output/writeup.md` and `blurb.txt`.

On the host that means `/home/ubu/notes/<folder>/output/`.

### Folder path formats

The server accepts either:
- Bare subfolder name: `task4`
- Full container path: `/notes/task4`

### What Claude Code produces

**`writeup.md`** — structured markdown write-up with a `## Self-Quiz` section at the end. Structure is determined by content type: study notes get the study-guide treatment, lab logs get a narrative blog structure.

**`blurb.txt`** — 3-5 sentence project blurb suitable for a LinkedIn post or GitHub README intro. Specific, humble, no filler phrases.

See [`examples/sample-output/`](examples/sample-output/) for representative output.

---

## Repository Structure

```
.
├── docker-compose.yml
├── docker/
│   └── knowledgeops/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── server.py           # MCP server (FastMCP, file I/O only)
├── docs/
│   ├── architecture.md         # Design decisions and tradeoffs
│   └── claude-code-prompts.md  # Prompt patterns that work well
└── examples/
    └── sample-output/
        ├── writeup.md          # Example write-up from a lab session
        └── blurb.txt           # Example project blurb
```

---

## Security Notes

The container has no outbound network access and mounts only `/home/ubu/notes`. Path traversal is rejected server-side — all paths are validated to stay within `/notes`. The server runs as a non-root user inside the container.

There are no API keys in this container. The only credentials involved are Claude Code's, which live on the host.

---

## Stopping and Rebuilding

```bash
docker compose down
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f
```

---

## Related

- [Blog post](https://desvert.github.io) — why this was built and what the build process actually looked like
- [AI-Assisted SOC Triage Lab](https://github.com/desvert/ai-soc-mcp-lab) — earlier project using the same MCP pattern for network traffic analysis
