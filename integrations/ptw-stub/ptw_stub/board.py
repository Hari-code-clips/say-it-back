"""The permit board (GET /): server-rendered HTML, no script, no external asset.

Every value from a webhook is escaped. The only style is the inline block below, allowed by its own
SHA-256 in the page's Content-Security-Policy (app.py), so the page can load nothing else. It
refreshes itself every few seconds, so a decision made in Say It Back shows up without a click.
"""

from __future__ import annotations

import base64
import hashlib
from html import escape
from typing import Any

from ptw_stub.permits import DEMO_LABEL, Permit

REFRESH_S = 5

STYLE = """
/* Hallmark · genre: modern-minimal · component: permit board · tone: utilitarian
 * audience: site permit coordinator, demo evaluators · use: see which permits are released or held
 * v0.5.2: grouped permits (one card per permit ref, one row per worker slot, never a name)
 * pre-emit critique: P4 H4 E4 S4 R5 V3 · states: static page, no interactive element
 */
:root {
  --color-paper: oklch(97.5% 0.004 250);
  --color-surface: oklch(99.5% 0.002 250);
  --color-rule: oklch(88% 0.006 250);
  --color-muted: oklch(46% 0.012 250);
  --color-ink: oklch(21% 0.014 250);
  --color-released: oklch(46% 0.11 150);
  --color-released-wash: oklch(95% 0.03 150);
  --color-held: oklch(48% 0.15 35);
  --color-held-wash: oklch(95.5% 0.025 35);
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --space-xs: 0.25rem; --space-sm: 0.5rem; --space-md: 1rem;
  --space-lg: 1.5rem; --space-xl: 2.5rem;
  --radius: 8px;
  --radius-pill: 999px;
  --text-sm: 0.875rem; --text-base: 1rem; --text-lg: 1.25rem;
  --text-xl: clamp(1.5rem, 2vw + 1rem, 2.25rem);
}
@media (prefers-color-scheme: dark) {
  :root {
    --color-paper: oklch(17% 0.01 250);
    --color-surface: oklch(21% 0.012 250);
    --color-rule: oklch(32% 0.012 250);
    --color-muted: oklch(72% 0.01 250);
    --color-ink: oklch(94% 0.006 250);
    --color-released: oklch(76% 0.12 150);
    --color-released-wash: oklch(26% 0.04 150);
    --color-held: oklch(74% 0.13 35);
    --color-held-wash: oklch(27% 0.045 35);
  }
}
html, body { overflow-x: clip; }
body {
  margin: 0; background: var(--color-paper); color: var(--color-ink);
  font-family: var(--font-sans); font-size: var(--text-base); line-height: 1.5;
}
main { max-width: 64rem; margin: 0 auto; padding: var(--space-xl) var(--space-md); }
header { display: grid; gap: var(--space-sm); margin-bottom: var(--space-xl); }
h1 {
  margin: 0; font-size: var(--text-xl); font-weight: 650; letter-spacing: -0.02em;
  overflow-wrap: anywhere; min-width: 0;
}
.lede { margin: 0; color: var(--color-muted); max-width: 44rem; }
.tally { margin: 0; font-variant-numeric: tabular-nums; }
.permits { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-md); }
.permit {
  background: var(--color-surface); border: 1px solid var(--color-rule);
  border-left: 6px solid var(--state); border-radius: var(--radius);
  padding: var(--space-lg); display: grid; gap: var(--space-md); min-width: 0;
}
.permit.released { --state: var(--color-released); --wash: var(--color-released-wash); }
.permit.held { --state: var(--color-held); --wash: var(--color-held-wash); }
.top {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-sm) var(--space-md);
}
.top h2 {
  margin: 0; font-family: var(--font-mono); font-size: var(--text-lg); letter-spacing: -0.01em;
  overflow-wrap: anywhere; min-width: 0;
}
.status {
  font-weight: 650; font-size: var(--text-sm); color: var(--state); background: var(--wash);
  border: 1px solid var(--state); border-radius: var(--radius-pill); padding: 0 var(--space-sm);
  white-space: nowrap;
}
.why { margin: 0; color: var(--color-muted); }
.count {
  margin: 0; font-weight: 650; color: var(--state); font-variant-numeric: tabular-nums;
}
.slots { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-sm); }
.slot {
  display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-xs) var(--space-md);
  border-top: 1px solid var(--color-rule); padding-top: var(--space-sm); min-width: 0;
}
.who { font-weight: 600; }
.mark { font-size: var(--text-sm); font-weight: 650; }
.slot.go .mark { color: var(--color-released); }
.slot.no-go .mark { color: var(--color-held); }
.slot.waiting .mark { color: var(--color-muted); }
.detail { min-width: 0; overflow-wrap: anywhere; display: grid; gap: var(--space-xs); }
.demo {
  margin: 0; font-weight: 600; border: 1px dashed var(--color-rule);
  border-radius: var(--radius); padding: var(--space-xs) var(--space-sm);
}
dl {
  margin: 0; display: grid; grid-template-columns: minmax(0, 1fr);
  gap: var(--space-sm) var(--space-lg);
}
dl div { min-width: 0; }
dt { font-size: var(--text-sm); color: var(--color-muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.mono { font-family: var(--font-mono); font-size: var(--text-sm); }
.open { margin: 0; padding-left: var(--space-lg); }
.none { color: var(--color-muted); }
.empty {
  border: 1px dashed var(--color-rule); border-radius: var(--radius);
  padding: var(--space-xl) var(--space-lg); color: var(--color-muted);
}
footer { margin-top: var(--space-xl); color: var(--color-muted); font-size: var(--text-sm); }
@media (min-width: 48rem) {
  main { padding: var(--space-xl) var(--space-lg); }
  dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  dl .wide { grid-column: 1 / -1; }
  .slot { grid-template-columns: 7rem 8rem minmax(0, 1fr); align-items: baseline; }
}
"""

STYLE_SHA256 = base64.b64encode(hashlib.sha256(STYLE.encode("utf-8")).digest()).decode("ascii")


def _e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _open_steps(permit: Permit) -> str:
    if not permit.open_steps:
        return '<span class="none">None open</span>'
    return _steps_list(permit.open_steps)


def _open_hazards(permit: Permit) -> str:
    if not permit.open_hazards:
        return '<span class="none">None open</span>'
    return f'<span class="mono">{_e(", ".join(permit.open_hazards))}</span>'


IN_PERSON = "checked in person"  # 2026-10-17: the worker declined the AI check
NO_AI_CHECK = "No AI check was made: the worker chose not to be recorded."


def _why(permit: Permit) -> str:
    if permit.status == "released" and permit.in_person:
        return (
            f"The supervisor checked the worker in person and decided Go. {NO_AI_CHECK} Work may "
            "start under this permit."
        )
    if permit.status == "released":
        return "The supervisor decided Go. Work may start under this permit."
    return "The supervisor decided No-go. Work stays stopped."


def _demo(permit: Permit) -> str:
    if not permit.demo:
        return ""
    asked = ", ".join(f"round {a['round']} {a['questionId']}" for a in permit.sample_answers)
    return f'<p class="demo">{_e(DEMO_LABEL)} ({_e(asked)}): not the worker\'s own words.</p>'



def _steps_list(steps: list[dict[str, Any]]) -> str:
    """Open steps; a grouped permit's carry their worker's `slot`, shown first."""
    items = "".join(
        "<li>"
        + (f"Worker {_e(s['slot'])} · " if "slot" in s else "")
        + f"<span class=\"mono\">{_e(s['id'])}</span> {_e(s.get('text', ''))}</li>"
        for s in steps
    )
    return f'<ul class="open">{items}</ul>'


def _workers(slots: list[int]) -> str:
    """"worker 2", "workers 2 and 3", "workers 1, 2 and 3"."""
    names = [str(n) for n in slots]
    if len(names) == 1:
        return f"worker {names[0]}"
    return f"workers {', '.join(names[:-1])} and {names[-1]}"


def _slot_row(permit: Permit, n: int) -> str:
    entry = permit.slot(n)
    if entry is None:
        return f"""<li class="slot waiting"><span class="who">Worker {n}</span>
      <span class="mark">No decision yet</span><span class="detail"></span></li>"""
    go = entry.decision == "go"
    mark = ("Go" if go else "No-go") + (f" · {IN_PERSON}" if entry.in_person else "")
    open_steps = f"<span>{NO_AI_CHECK}</span>" if entry.in_person else ""
    if entry.go_with_open_steps:
        count = len(entry.open_steps)
        open_steps += (
            f'<span>{count} step{"" if count == 1 else "s"} open at decision; the supervisor\'s '
            f"reason is in the Say It Back record.</span>{_steps_list(entry.open_steps)}"
        )
    elif entry.open_steps:
        open_steps += _steps_list(entry.open_steps)
    when = _e(entry.decided_at) or "—"
    return f"""<li class="slot {"go" if go else "no-go"}"><span class="who">Worker {n}</span>
      <span class="mark">{mark}</span>
      <span class="detail"><span class="mono">{_e(entry.briefing_id)} · {when}</span>
      <span class="mono">{_e(entry.record_hash)}</span>{open_steps}</span></li>"""


def _group_why(permit: Permit) -> str:
    if permit.status == "released":
        why = "Every worker on this permit has a Go from the supervisor. Work may start under it."
    else:
        why = (
            "Released only when every worker on this permit has a Go. "
            f"Waiting on {_workers(permit.waiting)}."
        )
    ordered = sorted(permit.slots, key=lambda s: s.slot)
    open_go = [s.slot for s in ordered if s.go_with_open_steps]
    if open_go:
        verb = "a Go" if len(open_go) == 1 else "Go"
        why += f" {_workers(open_go).capitalize()} had {verb} with a step still open."
    in_person = [s.slot for s in ordered if s.in_person]
    if in_person:
        verb = "was" if len(in_person) == 1 else "were"
        why += f" {_workers(in_person).capitalize()} {verb} {IN_PERSON}, with no AI check."
    return why


def _group(permit: Permit) -> str:
    """A grouped permit (v0.5.2): one row per worker slot, never a name."""
    crew = permit.crew_size or 0
    rows = "".join(_slot_row(permit, n) for n in range(1, crew + 1))
    return f"""<li class="permit {permit.status}">
  <div class="top"><h2>{_e(permit.ref)}</h2></div>
  <p class="count">{permit.verified} of {crew} workers verified · {permit.status}</p>
  <p class="why">{_group_why(permit)}</p>{_demo(permit)}
  <ol class="slots">{rows}</ol>
  <dl>
    <div><dt>Site and task</dt><dd>{_e(permit.site_id)} · {_e(permit.task_id)}</dd></div>
    <div><dt>Board number</dt><dd class="mono">{_e(permit.id)}</dd></div>
    <div><dt>Latest decision</dt><dd class="mono">{_e(permit.decided_at) or "—"}</dd></div>
    <div><dt>Received</dt><dd class="mono">{_e(permit.received_at)}</dd></div>
    <div class="wide"><dt>Open steps</dt><dd>{_open_steps(permit)}</dd></div>
    <div class="wide"><dt>Open hazards</dt><dd>{_open_hazards(permit)}</dd></div>
  </dl>
</li>"""


def _permit(permit: Permit) -> str:
    if permit.grouped:
        return _group(permit)
    label = "Released" if permit.status == "released" else "Held"
    return f"""<li class="permit {permit.status}">
  <div class="top"><h2>{_e(permit.id)}</h2><span class="status">{label}</span></div>
  <p class="why">{_why(permit)}</p>{_demo(permit)}
  <dl>
    <div><dt>Site and task</dt><dd>{_e(permit.site_id)} · {_e(permit.task_id)}</dd></div>
    <div><dt>Briefing</dt><dd class="mono">{_e(permit.briefing_id)}</dd></div>
    <div><dt>Decided</dt><dd class="mono">{_e(permit.decided_at) or "—"}</dd></div>
    <div><dt>Received</dt><dd class="mono">{_e(permit.received_at)}</dd></div>
    <div class="wide"><dt>Open steps</dt><dd>{_open_steps(permit)}</dd></div>
    <div class="wide"><dt>Open hazards</dt><dd>{_open_hazards(permit)}</dd></div>
    <div class="wide"><dt>Record hash</dt><dd class="mono">{_e(permit.record_hash)}</dd></div>
  </dl>
</li>"""


def render(permits: list[Permit], *, store: str = "memory") -> str:
    released = sum(1 for p in permits if p.status == "released")
    held = len(permits) - released
    if permits:
        body = '<ol class="permits">' + "".join(_permit(p) for p in permits) + "</ol>"
    else:
        body = (
            '<p class="empty">No permits yet. When a supervisor decides Go or No-go in Say It '
            "Back, the signed decision arrives here and a permit is released or held.</p>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_S}">
<title>Permit board</title>
<style>{STYLE}</style>
</head>
<body>
<main>
<header>
  <h1>Permit board</h1>
  <p class="lede">A stand-in permit-to-work system. Each permit follows a supervisor's decision
  in Say It Back, received as a signed webhook. Nothing here decides anything.</p>
  <p class="tally">{released} released · {held} held</p>
</header>
{body}
<footer>Kept in {"Firestore" if store == "firestore" else "memory"}. Only posts signed with the
shared secret, within 300 s, are accepted.
Refreshes every {REFRESH_S} s.</footer>
</main>
</body>
</html>
"""
