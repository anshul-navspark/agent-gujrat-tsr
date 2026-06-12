# Note for Rishabh — 2026-05-20

Hey Rishabh, this is a note from Anshul (via Claude Code share link).

**TL;DR: you were on an older version of the code that had the
Chain-of-Title numbering issue. It's already fixed on `main`. Please
pull before you keep working — your local fix may be redundant or may
conflict with mine.**

## What happened

- Your working copy was based on a commit older than `a158ee2`
  (`feat: auto-number Chain of Title rows so lawyers can insert rows
  without renumbering`, May 14). That's the fix for the numbering
  problem — Word-native `w:numPr` on column 1 of the Chain-of-Title
  table, so the rows auto-renumber when a lawyer inserts/deletes a row
  in Word.
- You apparently noticed the same bug and started fixing it locally.
- I pushed today's snapshot as `5c368c7` on `origin/main`. The
  numbering fix and a couple of follow-ups (`711537a`, `9516703`) are
  already there.

## What to do

```bash
git fetch origin
git status              # see if you have local commits
git log --oneline -10   # confirm your base
```

- **If your local fix is uncommitted**: `git stash`, then
  `git pull --rebase origin main`, then `git stash pop` and resolve
  any conflict in `tsr_generator/document/docx_generator.py`
  (specifically `_create_decimal_numbering` and
  `_apply_list_number`).
- **If you committed locally but didn't push**: `git pull --rebase origin main`
  and resolve conflicts the same way. If your fix is essentially the
  same as mine, drop your commit during the rebase.
- **If you pushed to a branch**: open a PR against `main` so we can
  diff approaches; don't force-push over `main`.

## Other things to know before you continue

- `.env` has a new Gemini key
  (`AIzaSyCpl…az-JU` — supports all models). The two older keys are
  dead (403 + 0-quota). Pull and update your `.env` if yours is stale.
- `LAWYER_REVIEW_NOTES_2026_05_20.md` (at repo root, also in the
  commit I just pushed) — please skim before tomorrow's lawyer
  review. It has a per-entry audit of a Trambo-150 TSR generated on
  current `main` and the extraction gaps I want to flag with the
  lawyer (missing death dates, merged distribution rows, `/p1/p`
  notation).
- AnyRoR is unreachable from my machine right now (foreign-IP
  geo-block, `No route to host`). If you can scrape from your end,
  please generate TSRs for the four surveys from the WhatsApp photo:
  Kharoda/Lakhpat/Kutch 81, 12, 14 and Vayor/Abdasa/Kutch 11.

Ping me if anything's confusing.

— Anshul
