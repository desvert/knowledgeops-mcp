#!/usr/bin/env python3
"""
knowledgeops_mcp - Personal knowledge processor MCP server

File I/O only. No Anthropic API calls.
Claude Code handles all AI reasoning using your subscription.

Tools:
  knowledgeops_scan_folder   - List files and return inventory
  knowledgeops_read_folder   - Read all file contents, return to Claude Code
  knowledgeops_save_outputs  - Write writeup.md and blurb.txt to ./output/

Notes root: /notes (maps to /home/ubu/notes on the host via Docker volume)
"""

import json
import base64
import mimetypes
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, field_validator, ConfigDict

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

NOTES_ROOT = Path("/notes")

SUPPORTED_TEXT  = {".txt", ".md", ".log", ".py", ".sh", ".yaml", ".yml", ".json", ".csv"}
SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SUPPORTED_PDF   = {".pdf"}
SUPPORTED_ALL   = SUPPORTED_TEXT | SUPPORTED_IMAGE | SUPPORTED_PDF

# ──────────────────────────────────────────────
# Server init
# ──────────────────────────────────────────────

mcp = FastMCP("knowledgeops_mcp")

# ──────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────

def _resolve_folder(folder: str) -> tuple[Path, str | None]:
    """
    Resolve a folder path relative to NOTES_ROOT.
    Accepts either a bare subfolder name ('task4') or a full path ('/notes/task4').
    Returns (resolved_path, error_string_or_None).
    """
    p = Path(folder)

    # If caller passed a full path starting with /notes, use it directly
    if p.is_absolute():
        resolved = p.resolve()
    else:
        # Treat as relative to notes root
        resolved = (NOTES_ROOT / folder).resolve()

    # Safety: must stay within NOTES_ROOT
    try:
        resolved.relative_to(NOTES_ROOT)
    except ValueError:
        return resolved, f"Path '{folder}' is outside the notes root ({NOTES_ROOT}). Use a subfolder of /notes."

    if not resolved.exists():
        return resolved, f"Folder '{resolved}' does not exist."
    if not resolved.is_dir():
        return resolved, f"'{resolved}' is not a directory."

    return resolved, None


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[Could not read {path.name}: {e}]"


def _read_pdf_file(path: Path) -> str:
    if not HAS_PYPDF:
        return f"[PDF skipped — pypdf not installed]\nFile: {path.name}"
    try:
        reader = pypdf.PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"--- Page {i+1} ---\n{text}")
        return "\n\n".join(pages) if pages else f"[PDF had no extractable text: {path.name}]"
    except Exception as e:
        return f"[Could not read PDF {path.name}: {e}]"


def _encode_image(path: Path) -> tuple[str, str]:
    """Returns (base64_data, media_type)."""
    mime, _ = mimetypes.guess_type(str(path))
    media_type = mime or "image/png"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def _format_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes //= 1024
    return f"{num_bytes:.1f} GB"

# ──────────────────────────────────────────────
# Input models
# ──────────────────────────────────────────────

class FolderInput(BaseModel):
    """Input model for folder-targeting tools."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    folder: str = Field(
        ...,
        description=(
            "Subfolder name under /notes, or full path starting with /notes. "
            "Examples: 'task4', 'malware-lab/june', '/notes/task4'"
        ),
        min_length=1
    )

    @field_validator("folder")
    @classmethod
    def no_traversal(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("Path traversal ('..') is not allowed.")
        return v


class SaveInput(BaseModel):
    """Input model for saving outputs."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    folder: str = Field(
        ...,
        description="Subfolder name or full /notes path — same folder that was read.",
        min_length=1
    )
    writeup: str = Field(
        ...,
        description="Full markdown content for writeup.md.",
        min_length=1
    )
    blurb: Optional[str] = Field(
        default=None,
        description="Short project blurb for blurb.txt. Omit if not generated."
    )

    @field_validator("folder")
    @classmethod
    def no_traversal(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("Path traversal ('..') is not allowed.")
        return v

# ──────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────

@mcp.tool(
    name="knowledgeops_scan_folder",
    annotations={
        "title": "Scan Notes Folder",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def knowledgeops_scan_folder(params: FolderInput, ctx: Context) -> str:
    """Scan a notes folder and return an inventory of all files found.

    Call this first to preview what is in a folder before reading it.
    Returns file counts, types, sizes, and flags unsupported files.
    No file contents are returned — use knowledgeops_read_folder for that.

    Args:
        params (FolderInput): Input containing:
            - folder (str): Subfolder name or full /notes path.
              Examples: 'task4', 'malware-lab/june', '/notes/task4'

    Returns:
        str: JSON object with keys:
            - folder (str): Resolved absolute path
            - file_count (int): Number of supported files found
            - total_size_bytes (int): Combined size of all supported files
            - total_size (str): Human-readable size (e.g. '1.2 MB')
            - files (list): Each entry has 'file', 'type', 'size_bytes', 'size'
            - unsupported (list): Filenames found but not supported
            - output_exists (bool): Whether an output/ subfolder already exists
    """
    folder, err = _resolve_folder(params.folder)
    if err:
        return json.dumps({"error": err})

    await ctx.report_progress(0.2, "Scanning...")

    inventory = []
    unsupported = []
    total_bytes = 0

    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if "output" in path.relative_to(folder).parts:
            continue

        ext = path.suffix.lower()
        rel = str(path.relative_to(folder))
        size = path.stat().st_size

        if ext in SUPPORTED_TEXT:
            inventory.append({"file": rel, "type": "text", "size_bytes": size, "size": _format_size(size)})
            total_bytes += size
        elif ext in SUPPORTED_PDF:
            inventory.append({"file": rel, "type": "pdf", "size_bytes": size, "size": _format_size(size)})
            total_bytes += size
        elif ext in SUPPORTED_IMAGE:
            inventory.append({"file": rel, "type": "image", "size_bytes": size, "size": _format_size(size)})
            total_bytes += size
        else:
            unsupported.append(rel)

    output_exists = (folder / "output").exists()

    await ctx.report_progress(1.0, "Scan complete.")

    return json.dumps({
        "folder": str(folder),
        "file_count": len(inventory),
        "total_size_bytes": total_bytes,
        "total_size": _format_size(total_bytes),
        "files": inventory,
        "unsupported": unsupported,
        "output_exists": output_exists
    }, indent=2)


@mcp.tool(
    name="knowledgeops_read_folder",
    annotations={
        "title": "Read Notes Folder Contents",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def knowledgeops_read_folder(params: FolderInput, ctx: Context) -> str:
    """Read all supported files in a notes folder and return their contents.

    Text files and PDFs are returned as plain text. Images are returned as
    base64-encoded data with their media type, so Claude Code can read them
    directly using vision. The output/ subfolder is always skipped.

    Call this after knowledgeops_scan_folder. Once you receive the contents,
    produce the write-up and blurb yourself, then call knowledgeops_save_outputs.

    Args:
        params (FolderInput): Input containing:
            - folder (str): Subfolder name or full /notes path.

    Returns:
        str: JSON object with keys:
            - folder (str): Resolved absolute path
            - file_count (int): Number of files read
            - files (list): Each entry contains:
                For text/PDF files:
                  - file (str): Relative path
                  - type (str): 'text' or 'pdf'
                  - content (str): Full text content
                For image files:
                  - file (str): Relative path
                  - type (str): 'image'
                  - media_type (str): e.g. 'image/png'
                  - base64 (str): Base64-encoded image data
                  - note (str): Instruction to extract visible text/content
    """
    folder, err = _resolve_folder(params.folder)
    if err:
        return json.dumps({"error": err})

    await ctx.report_progress(0.1, "Reading files...")

    files_out = []
    total = 0

    all_paths = sorted(folder.rglob("*"))
    supported = [
        p for p in all_paths
        if p.is_file() and p.suffix.lower() in SUPPORTED_ALL
        and "output" not in p.relative_to(folder).parts
    ]

    for i, path in enumerate(supported, 1):
        await ctx.report_progress(0.1 + 0.85 * (i / max(len(supported), 1)), f"Reading {path.name}...")
        ext = path.suffix.lower()
        rel = str(path.relative_to(folder))

        if ext in SUPPORTED_TEXT:
            files_out.append({
                "file": rel,
                "type": "text",
                "content": _read_text_file(path)
            })

        elif ext in SUPPORTED_PDF:
            files_out.append({
                "file": rel,
                "type": "pdf",
                "content": _read_pdf_file(path)
            })

        elif ext in SUPPORTED_IMAGE:
            try:
                b64, media_type = _encode_image(path)
                files_out.append({
                    "file": rel,
                    "type": "image",
                    "media_type": media_type,
                    "base64": b64,
                    "note": "Base64-encoded image. Extract all visible text, commands, terminal output, and diagrams."
                })
            except Exception as e:
                files_out.append({
                    "file": rel,
                    "type": "image",
                    "error": f"Could not encode image: {e}"
                })

        total += 1

    await ctx.report_progress(1.0, "All files read.")

    return json.dumps({
        "folder": str(folder),
        "file_count": total,
        "files": files_out
    })


@mcp.tool(
    name="knowledgeops_save_outputs",
    annotations={
        "title": "Save Knowledge Ops Outputs",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def knowledgeops_save_outputs(params: SaveInput, ctx: Context) -> str:
    """Save the generated write-up and blurb to the output/ subfolder.

    Creates <folder>/output/ if it does not exist, then writes writeup.md
    and optionally blurb.txt. Call this after you have produced the content.

    Args:
        params (SaveInput): Input containing:
            - folder (str): Same folder that was read — output/ will be created inside it.
            - writeup (str): Full markdown content for writeup.md.
            - blurb (str | None): Short project blurb for blurb.txt. Optional.

    Returns:
        str: JSON object with keys:
            - output_dir (str): Path to the output directory
            - writeup_path (str): Full path to writeup.md
            - writeup_size (str): Human-readable file size
            - blurb_path (str | null): Full path to blurb.txt, or null if not provided
            - blurb_preview (str | null): First 280 chars of blurb for quick review
    """
    folder, err = _resolve_folder(params.folder)
    if err:
        return json.dumps({"error": err})

    output_dir = folder / "output"
    output_dir.mkdir(exist_ok=True)

    writeup_path = output_dir / "writeup.md"
    writeup_path.write_text(params.writeup, encoding="utf-8")

    blurb_path_str = None
    blurb_preview = None

    if params.blurb:
        blurb_path = output_dir / "blurb.txt"
        blurb_path.write_text(params.blurb, encoding="utf-8")
        blurb_path_str = str(blurb_path)
        blurb_preview = params.blurb[:280]

    await ctx.report_progress(1.0, "Files saved.")

    return json.dumps({
        "output_dir": str(output_dir),
        "writeup_path": str(writeup_path),
        "writeup_size": _format_size(writeup_path.stat().st_size),
        "blurb_path": blurb_path_str,
        "blurb_preview": blurb_preview
    }, indent=2)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable_http", port=8000)
