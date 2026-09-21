# Gujarat TSR lessons (knowledge home)

Every lawyer correction and process lesson for Gujarat TSRs is recorded here and committed (standing rule, 21-09-2026:
TSR knowledge lives in the state's repo, never in a side folder). Other states keep theirs in `agent-raj-tsr`
(`tsr_spec/LESSONS.md`) and `agent-mp` (`docs/TSR_LESSONS.md`); nothing is shared across repos. None of these rules has
formal lawyer sign-off beyond the source quoted.

## Firm policy (Vijay)
- **G1. No SRO / EC search for Gujarat TSRs.** Encumbrances and legal cases are entered on the land record itself. Still
  run **one court-case search** per TSR "just to be sure". Free online copies are enough; do not pay for certified copies.
  Source: Rishabh relaying Vijay, 28-08-2026: *"SRO is not needed as they add encumbrance, for legal cases they are also
  mentioned, but he said to once look for cases just to be sure"*; *"we don't need certified copies, online copies
  suffice"*. (`skills/gujarat-encumbrance/SKILL.md` explains the free search is not an EC; this is the policy on top.)
- **G2. The Gujarat format is the firm's reference style.** Mittali (reviewing Maharashtra drafts, 03-09-2026): *"we prefer
  gujrat like formats, table no 2 is very long we don't mention all the documents"*. Keep the Documents table terse; it
  is not an exhaustive list of every paper read.

## Process rules (learned in Rajasthan/MP, apply unchanged here)
- **G3. No review notes inside the .docx.** Doubts go in a separate `AI Drafts - Issues for lawyer review (DD.MM.YYYY) -
  <LOT>.docx`. Lawyers deleting inline notes by hand introduced defects (truncated names, "reflects reflects", digits
  merged).
- **G4. One TSR at a time, end to end** (draft → gates → audit → blind re-read → requisition); no fan-out across TSRs, not
  even for reading. Keep a `STATUS.md` handoff; /clear about every 4 TSRs.
- **G5. Adding documents to an existing TSR = edit the lawyer's file in place and deploy it under its original name**;
  list the destination folder afterwards. An issues sheet alone is not delivery.
- **G6. A file the lawyer has edited is the spec.** Read it, never rewrite it; overwrite only when its md5 equals our last
  deploy. New versions go beside it as `(revised DD.MM.YYYY)`. A move is not an edit — diff before treating as reviewed.
- **G7. OCR per page, one agent per page, at most 8 image reads**; whole-PDF agents loop for over an hour. Scanned
  handwritten fields: Opus at high effort only (never Sonnet).
- **G8. Staff OneDrive folders get .docx only** — no .md/.txt, not even notes. OCR JSON and crops stay local.
