# Claude Code Prompt Patterns

A reference for prompts that work well with knowledgeops-mcp. None of these are required — Claude Code will figure out the tool sequence on its own — but being specific about what you want produces better output.

---

## Basic usage

The simplest prompt that works:

```
Process my notes in task4 and save the outputs
```

Claude Code will scan the folder, read everything, decide on the write-up structure, generate the blurb, and save both files without further instruction.

---

## Specifying output style

If you want to steer the write-up structure:

```
Process /notes/malware-lab and write it up as a lab report —
narrative style with what I did, what I found, and what I'd do differently.
Include a self-quiz at the end. Save when done.
```

Or for study notes:

```
Process the notes in cisco-module-3. Structure the write-up as a study guide
with a compare/contrast table for any protocols or concepts that come up,
and a flashcard-style quiz at the end. Save both outputs.
```

---

## Scanning first

If you want to check what's in a folder before committing to processing it:

```
Scan /notes/task4 and tell me what's there before doing anything else
```

Claude Code will call `knowledgeops_scan_folder` and report back. You can then decide whether to proceed.

---

## Blurb tone guidance

The default blurb is calibrated for a humble, specific tone. If you want to adjust:

```
Process task4 and save the outputs. For the blurb, write it for a GitHub README
intro rather than LinkedIn — a bit more technical, less career-narrative.
```

---

## Re-running on revised notes

If you've updated your notes after a first pass and want a fresh output:

```
Re-process /notes/task4 and overwrite the existing outputs
```

`knowledgeops_save_outputs` overwrites existing files by default, so no special handling is needed.

---

## Multiple folders

Claude Code can process folders sequentially in a single session:

```
Process task3, task4, and task5 in order and save outputs for each
```

It will run the scan/read/save cycle for each folder, keeping context from earlier folders to inform later ones if relevant.

---

## Notes on image handling

If your folder contains screenshots, Claude Code receives them as base64 and processes them via vision. You don't need to do anything special — just include the images in the folder. Descriptive filenames help (e.g., `wireshark-http-filter.png` is more useful than `screenshot1.png`).

Scanned PDFs (image-only, no selectable text) are handled the same way as images if they are first exported as PNGs or JPGs. `pypdf` cannot extract text from scanned-only PDFs.
