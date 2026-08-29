# Operating AnyRoR without getting blocked

> **Runtime:** this repo requires **Python >= 3.11** — see `references/runtime.md`.
> Bare `python3` on the office Mac is 3.9.6; run tests with an explicit 3.11 path.


Everything here was learned by losing access. AnyRoR blocks by **source IP**, the
firm has **one** residential proxy exit, and a block affects everyone at once.
Read this before changing anything about how requests are made.

## The one rule

**Every AnyRoR request goes through `ANYROR_PROXY`.** Not "after a block" — always.
Datacenter IPs, VPN exits and Cloudflare WARP are all blocked; only an Indian
*residential* IP passes. The proxy is an asocks subscription with a sticky exit.

## Proxy gotchas that look like something else

| Symptom | Actual cause |
|---|---|
| `407` on the proxy | Wrong port. **Only gateway port 443 authenticates.** 8080 and 12321 are open but always 407, which reads exactly like a dead subscription. |
| Whole attempt times out early | The HTTPS CONNECT tunnel **cold-starts >10s**, then settles at ~2s. `ANYROR_CONNECT_TIMEOUT` defaults to 30s when a proxy is set for this reason. |
| `ProxyError` / `RemoteDisconnected` mid-run | The proxy drops connections intermittently — roughly 2 in 15 requests observed 2026-08-27. This is **transient, not a block**. Rebuild the session and continue; do not treat it as a WAF event. |
| A `curl` through the proxy returns 200 but fetches fail | A bad proxy returns a **false 200**. Never test with a bare curl — test against AnyRoR itself and check the page signature below. |

## Telling a good page from a block page

Do not trust the status code. Check the body:

- **Good** landing page: **~36–38 KB**, `ddlDistrict` populated with **35 options**
  (34 districts + the blank "Select").
- **WAF block** page: **~44 KB**, contains **`Attack ID`** or `Web Page Blocked`,
  and every `<select>` is empty.

## Pacing

Three full fetch sessions in ~6 minutes tripped the WAF on 2026-08-21, and that
was correctly-paced work. A full fetch is a 7-request walk. **Leave ≥60s between
fetches.** Only one lawyer works Gujarat today, so this is guidance rather than a
lock — revisit if that changes.

Landing-page GETs are much cheaper than fetches (one request, and the captcha is
already on that page), but they still count.

## Maintenance window

AnyRoR is down daily **14:00–14:30 IST**. `core/anyror_maintenance.py` knows this.
Say so and stop; do not retry into it.

## Never do this

- **Never drive AnyRoR with a browser.** Selenium was the block *trigger*, not a
  workaround: on 2026-07-31 a Selenium-only run on a FRESH IP drew the WAF page on
  its very first navigation and escalated to a full block within ~4 minutes. The
  Selenium stack was deleted on 2026-08-27 for exactly this reason. The only
  browser use left is local headless Chrome rendering already-fetched HTML to PDF,
  which never touches AnyRoR.
- **Never retry a failed name lookup against the portal.** Resolve district,
  taluka and village against `anyror_hierarchy.json` *first* — a name miss should
  cost zero sessions.

## Survey numbers

Pass them ASCII (`44`, `150/p1`, `1300/p1/p2`); the fetcher generates the
Gujarati-digit and paiki spellings itself, including N-level nested forms, and
matches slash-insensitively against the live dropdown.

## Village names are not unique

There are 33,830 villages. Resolve a village **scoped by its district and taluka**,
never on its own: unscoped, "Bodkee" resolves to code 040 and "Bodki" to 094 — two
different places. An unscoped lookup returns a real, valid-looking PDF for the
wrong land.
