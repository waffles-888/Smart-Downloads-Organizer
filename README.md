# Smart Downloads Organizer

A small desktop app that fixes the classic messy downloads folder problem.
files piling up unsorted, silent duplicates wasting space, and old junk
nobody ever goes back to clean up.

## The problem

Downloads folders are digital junk drawers. Screenshots, installers, PDFs,
random archives, and duplicate copies of the same file all end up in one
flat folder with no structure. Finding anything means scrolling through
hundreds of unrelated files, and nobody ever gets round to tidying it
manually because it's tedious and there's a nagging fear of deleting
something important by accident.

This tool removes the friction from all three parts of that problem, safely.

## The 3 major QoL improvements

1. **Automatic categorization** - scans a folder and sorts files into
   sensible category folders (Images, Documents, Archives, Installers,
   Audio, Video, Code, Other) based on file extension. No more hunting
   through one giant list.

2. **Duplicate detection by content, not filename** - hashes each file's
   actual contents so it catches true duplicates even if they've
   been renamed (`report.pdf` vs `report_copy.pdf` with identical content).
   The oldest copy is kept in place. The rest are moved (never
   deleted) into a `Duplicates` folder for review.

3. **Stale file flagging** - flags anything untouched for a configurable
   number of days (default 90) and offers to move it into an
   `Archive/Stale` folder, so old clutter gets surfaced instead of sitting
   there forever unnoticed.

## Safety features

- **Preview before you commit** - every action has a dry run "Preview"
  step that shows exactly what would move, before anything actually moves.
- **Never deletes anything** - duplicates and stale files are only ever
  *moved*, never deleted.
- **Full undo** - every real move is logged to `undo_log.json` inside the
  target folder. The "Undo Last Run" button reverts the most recent batch
  of moves back to their original locations.
- **Configurable** - stale threshold, category folder names, and the
  extension to category mapping all live in `organizer_config.json`, which
  the Settings tab can edit (or you can hand-edit the JSON directly).

## Requirements

- Python 3.8+

## Running it

```bash
python3 gui.py
```

The folder field defaults to your OS's Downloads folder if it finds one,
but you can browse to any folder.

## How to use it

1. Choose a folder and click **Scan**.
2. Go through each tab (**Categorize**, **Duplicates**, **Stale Files**),
   click **Preview** to see what would happen, then **Apply** if you're
   happy with it.
3. If anything looks wrong afterwards, open the **Log / Undo** tab and hit
   **Undo Last Run**.
