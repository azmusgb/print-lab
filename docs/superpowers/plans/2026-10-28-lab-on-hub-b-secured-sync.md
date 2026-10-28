# Print lab on Pi Hub, Plan B: secured print-lab sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lab sync` and `lab pull` work against Local AI *and* the deployed Pi Hub: HTTPS to the hub with the house CA,
each target its own key and header, per-target results, no silent failures, and phone photos checked against their
SHA-256 before they enter a record.

**Architecture:** Work in the print-lab worktree `/Users/billrahe/dev/print-lab-hubsync`, branch `feat/hub-sync` (from
`feat/lab-on-hub` 9ab8168, the other session's dual-sync WIP; its `sync_targets`/`LAB_SYNC_URLS`, both-header `_call`
and `http://10.0.0.30` default are replaced, not kept). `lab/sync.py` gains a `Target` (who, where, which header, which
key, which TLS context); every remote call goes through it. `lab/pull.py` runs once per target. The launchd agent keeps
running the main checkout until the owner merges.

**Tech Stack:** Python 3.12, stdlib `urllib`/`ssl`/`hashlib`, pytest (`uv run python -m pytest`).

**Spec:** `/Users/billrahe/dev/pi-hub/docs/superpowers/specs/2026-10-28-print-lab-on-hub-design.md` (L4, L8). The hub
side (Plan A) is `/Users/billrahe/dev/pi-hub/hub/lab.py`.

## Global Constraints

- Hub target: base `LAB_HUB_URL`, default `https://home.home.arpa`; must start with `https://`, else that target fails
  with "The Pi Hub address must start with https://".
- Hub CA: `LAB_HUB_CA`, default `~/.config/print-lab/home-ca.crt`; the context is
  `ssl.create_default_context(cafile=…)` only — never the system store, never unverified. Missing file → that target
  fails with "Save the house CA first: curl -o ~/.config/print-lab/home-ca.crt https://home.home.arpa/home-ca.crt".
- Hub key: `LAB_HUB_KEY_FILE`, default `~/.config/print-lab/hub.key`; sent only as `X-Hub-Mac-Key`. No key file → the
  hub target is not set up and is left out entirely (not a failure). Empty key file → that target fails.
- Local AI target unchanged: `LAB_LOCALAI_URL`/`BASE`, `LAB_LOCALAI_KEY_FILE`, `LAB_LOCALAI_CA`, header
  `X-LocalAI-Mac-Key` only.
- Each request carries exactly one key header, the target's own. Never both.
- Printer telemetry (`check_active_print`, `fetch_workshop_status`) and `lab page`'s link stay on Local AI.
- An explicit `base=` argument means "Local AI at this address only" (tests and old callers).
- Error text from a target: the reply's `error` (Local AI) or `detail` (Pi Hub / FastAPI), else `HTTP <code>`.
- Tests never reach the network or the real home folder: `tests/conftest.py`'s autouse fixture also points
  `LAB_HUB_KEY_FILE` at a missing file and `LAB_HUB_URL` at `https://127.0.0.1:9`.
- Run: `uv run python -m pytest -q -p no:cacheprovider tests` (slow tests may be deselected with `-m "not slow"` if
  the repo marks them; report which).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't touch the owner's uncommitted
  files in the main checkout (`/Users/billrahe/dev/print-lab`).

## Review Focus

1. The hub key file exists but the CA was never saved → Local AI still syncs; `sync.json` says ok False with the CA
   message under "Pi Hub"; nothing goes out over an unverified connection (Task 1).
2. One phone request id pending on both targets (the owner tapped on both pages) → applied once; the second target
   gets "duplicate" (Task 2).
3. A target that was down comes back → the next run fixes `sync.json` per target; an old failure doesn't stick (Task 2).
4. `lab pull` with the hub down → Local AI requests still applied, telemetry still checked, the hub's error printed
   (Task 2).
5. A phone photo whose bytes don't hash to its name, or a name like `../x` → request refused, no file written into the
   project (Task 3).

---

### Task 1: Targets — the hub over verified HTTPS with its own key

**Files:** Modify `lab/sync.py` (replace `sync_targets`, `_call`, `_context` use), `lab/pull.py` (callers of `_call`,
`_context`, `_key`, `sync_targets`), `tests/conftest.py` (isolation), `tests/test_isolation.py`. Test
`tests/test_sync_targets.py` (new); update `tests/test_sync.py`, `tests/test_pull.py` for the new signatures.

**Interfaces:**
- Produces in `lab/sync.py`:
  - `@dataclass(frozen=True) class Target: name: str; base: str; header: str; key: str; context: ssl.SSLContext | None`
    (`name` is `"Local AI"` or `"Pi Hub"`).
  - `localai_target(base: str | None = None) -> Target` (raises `OSError` if the key file is missing, as `_key()` does).
  - `hub_target() -> Target | None` — `None` when the key file is absent; raises `ValueError(<constraint message>)` for
    http, missing CA, empty key.
  - `targets(base: str | None = None) -> list[Target | tuple[str, str]]` — with `base`: `[localai_target(base)]`;
    without: Local AI then the hub (if set up). A target that can't be built becomes `(name, message)` instead of
    raising, so the caller records it as that target's failure.
  - `_call(target: Target, method: str, path: str, timeout: float, body: bytes | None = None, ctype="application/json") -> tuple[int, dict]`
    — sends only `{target.header: target.key}`.
- `lab/pull.py`: `apply_pending(pdir: Path, target: Target, timeout: float = 10) -> list[dict]`; the photo download
  uses `target.header`/`target.key`/`target.context`.

- [ ] **Step 1: Failing tests** (`tests/test_sync_targets.py`, with tmp key/CA files via env):
  - `test_no_hub_key_means_local_ai_only` → `[t.name for t in targets()] == ["Local AI"]`.
  - `test_hub_needs_https` (`LAB_HUB_URL=http://10.0.0.30`) → the hub entry is `("Pi Hub", "The Pi Hub address must start with https://")`.
  - `test_hub_needs_the_house_ca` → `("Pi Hub", <message starting "Save the house CA first">)`.
  - `test_hub_context_trusts_only_the_house_ca` → with a CA file (generate one with `cryptography` if installed,
    else `openssl req -x509 … -subj /CN=test` via subprocess into tmp; skip if neither), `hub_target().context.verify_mode == ssl.CERT_REQUIRED`
    and `context.get_ca_certs()` has exactly that one cert.
  - `test_each_target_sends_only_its_own_header` → two `Fake` servers recording all headers; a hub `Target` built by
    hand with `context=None` and the fake's http base; Local AI's fake sees `X-LocalAI-Mac-Key` and no
    `X-Hub-Mac-Key`; the hub fake the reverse; keys are each file's own value.
  - `test_explicit_base_is_local_ai_only` even when a hub key exists.
  - `test_isolation.py`: `LAB_HUB_KEY_FILE` doesn't exist and `LAB_HUB_URL` starts with `https://127.0.0.1:9`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Remove `sync_targets`, `HUB_BASE` and `LAB_SYNC_URLS`. `_call`'s error text per Global
  Constraints. Existing tests switch from `(base, key)` to `localai_target(fake.base)` or a hand-built `Target`.
  Until Task 2, `sync()` and `pull()` may keep calling only the Local AI target.
- [ ] **Step 4: Run** the whole suite — PASS.
- [ ] **Step 5: Commit** — "sync: a target per place, the hub over verified https with its own key".

### Task 2: Per-target sync and pull, nothing swallowed

**Files:** Modify `lab/sync.py` (`sync`, `_sync_to` helper), `lab/pull.py` (`apply_pending`, `pull`, `cmd_pull`),
`lab/status.py` (sync lines). Test `tests/test_sync.py`, `tests/test_pull.py`, `tests/test_status*.py` (whichever
holds the sync line test).

**Interfaces:**
- Consumes Task 1's `targets`, `Target`, `_call`, `apply_pending(pdir, target, timeout)`.
- Produces: `class RemoteError(Exception)` in `lab/sync.py`; `apply_pending` raises `RemoteError(<target error text>)`
  when the pending list can't be fetched (non-200, network, TLS, non-list body) — a busy lock still returns `[]`.
- `sync.json` / `sync()` return shape:
  `{"ok": bool, "message": str, "photos_sent": int, "targets": {"Local AI": {"ok", "message", "photos_sent"?, "upserted"?, "removed"?, "unchanged"?}, "Pi Hub": {...}}, "at": …}`;
  `ok` is true only when every target in `targets` is ok; `message` is `"synced"` when ok, else
  `"; ".join(f"{name}: {msg}" for the failed ones)`; `photos_sent` is the sum.
- `pull()` result list gains `{"id": "<target name>", "status": "error", "message": …}` per failed target; `cmd_pull`
  returns 1 when any entry has status `error`.

- [ ] **Step 1: Failing tests:**
  - `test_sync_is_ok_only_when_every_target_is` — two fakes (Local AI 200, hub 409): `ok` False, `message` starts
    `"Pi Hub: "`, `targets["Local AI"]["ok"]` True.
  - `test_a_target_that_cannot_be_built_is_a_failed_target` — hub `("Pi Hub", msg)` → `targets["Pi Hub"] == {"ok": False, "message": msg}`, Local AI still synced.
  - `test_a_recovered_target_clears_its_failure` — fail then succeed: second `sync.json` all ok.
  - `test_missing_photo_file_fails_that_target` (not skipped silently): message names the photo path.
  - `test_hub_detail_text_is_reported` — hub replies `{"detail": "No project x."}` 404 → that message.
  - `test_pull_runs_every_target_and_reports_a_down_one` — Local AI fake with a verdict, hub target at a closed port:
    verdict applied, results include `{"id": "Pi Hub", "status": "error", …}`, `cmd_pull` exit 1.
  - `test_same_request_id_on_two_targets_applies_once` — second target receives result `duplicate`.
  - `test_pull_checks_telemetry_on_local_ai` — `check_active_print` gets Local AI's base even when the hub is first
    or Local AI fails.
  - `test_pull_syncs_every_target_after_applying` — `pull()` with no `base` ends in `sync()` with no `base` (both
    targets), not `sync(pdir, <one base>)`.
  - `test_status_shows_each_target` — `lab status` text has one line per target with ✓/✗ and the failed one's
    message; an old single-target `sync.json` (no `targets`) still renders as before.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Replace every bare `except Exception: pass` in these paths with a narrow catch that records
  or prints to stderr (posting a result that fails is printed and left for the next run's `duplicate`).
- [ ] **Step 4: Run** the whole suite — PASS.
- [ ] **Step 5: Commit** — "sync and pull: every target, each with its own result".

### Task 3: Phone photos are checked before they enter a record

**Files:** Modify `lab/pull.py` (the `photos` branch of `apply_pending`). Test `tests/test_pull.py` (fix the existing
photo tests to use real SHA-256 names).

**Interfaces:** Produces `SHA_RE = re.compile(r"[0-9a-f]{64}")` in `lab/pull.py`; constants `MAX_PHOTOS = 50`,
`MAX_TAB = 16`, `MAX_PHOTO_BYTES = 8 * 1024 * 1024` (Pi Hub's caps).

- [ ] **Step 1: Failing tests:**
  - `test_photo_request_shape_is_checked` (parametrized): 0 photos, 51 photos, sha `"../x"`, uppercase sha, 63-char
    sha, tab of 17 chars, tab not a string, photos not a list → status `refused`, nothing fetched (fake records no
    `/incoming/` GET), no files added.
  - `test_photo_bytes_must_match_their_name` → incoming bytes differ from the sha → `refused`, message says the photo
    didn't match, the run's photos unchanged.
  - `test_photo_over_the_cap_is_refused` → fake serves `MAX_PHOTO_BYTES + 1` bytes → `refused`; the read stops at
    cap + 1.
  - `test_photo_download_failure_leaves_the_request_for_next_time` → incoming 404/closed → status `error`, not written
    to `requests.jsonl`, no result posted; a later run with the photo present applies it.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Validate with `SHA_RE.fullmatch` before building any URL or path; read at most
  `MAX_PHOTO_BYTES + 1`; compare `hashlib.sha256(data).hexdigest()` to the name.
- [ ] **Step 4: Run** the whole suite — PASS.
- [ ] **Step 5: Commit** — "pull: phone photos checked by name, size and hash".
- [ ] **Step 6: Stop.** The owner merges to print-lab `main` (the launchd agent then runs it). Before that, the owner
  saves `hub.key` (Plan A step 4) and the house CA with plain `curl` (no `-k`: the Mac's keychain already trusts the
  house CA, so the download itself is verified):
  `mkdir -p ~/.config/print-lab && curl -fsS -o ~/.config/print-lab/home-ca.crt https://home.home.arpa/home-ca.crt`.
