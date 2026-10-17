"""The SOP library (2026-10-16, API.md Deviations "library"): per site, SOP entries with numbered
versions and, per version, the pre-approved critical steps a briefing can start from.

    entry   {id, siteId, title, taskId?, seeded, versions}
    version {number, text, lang, createdAt, createdBy, changeNote, status, steps, approvedBy?,
             approvedAt?, readOnly}

- A version is `draft` until a safety officer approves its steps. Only an `approved` version can
  start a briefing (`sopRef`), and an approved version never changes again.
- Seeds: each catalog task is an entry of its demo site with one approved, read-only version: the
  catalog SOP under its own number (SOP-LF-03 is v2, as the briefing's `sop.version` says) and the
  task's referenceSteps (English). Seeds are built from the catalog on every read and never
  stored, so no request can change them. With accounts, a new version of a seeded SOP is stored
  like any other; with none (device mode), a seed takes no new version (security fixes A, H3), so
  a catalogue SOP id never names steps an anonymous browser wrote and "approved".
- Scope: the store keeps one document per (site, scope). With accounts (SIB_AUTH_MODE=firebase,
  auth.py) the scope is the caller's org, shared by everyone with a role on the site. In device
  mode it is the caller's device-key hash, like a briefing's owner, so one judge's drafts never
  reach another.
- Roles (auth.require_role, a no-op in device mode): reading needs any role on the site, a draft
  admin or safety_officer, an approval safety_officer. `createdBy`/`approvedBy` record the role
  that acted ("device" in device mode, "catalog" for a seed), never a person.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable
from typing import Any, Literal

from sayitback import catalog, validators
from sayitback.caller import Caller
from sayitback.errors import InvalidState, NotFound, Unprocessable, quote
from sayitback.models import SOP_ID_PATTERN, CreateBriefing, Sop, SopRef, Step, Wire, now_iso
from sayitback.settings import Settings
from sayitback.store import Store

READ_ROLES = ("admin", "safety_officer", "supervisor")
DRAFT_ROLES = ("admin", "safety_officer")
APPROVE_ROLES = ("safety_officer",)
SEED_LANG = "en"  # the catalog's referenceSteps are English
MAX_ENTRIES = 50  # authored entries per scope
MAX_VERSIONS = 30  # per SOP
MAX_DOC_BYTES = 900_000  # one Firestore document holds at most 1 MiB
MAX_NOTE_CHARS = 300
CATALOGUE_READ_ONLY = "Catalogue SOPs are read-only in this demo. Add your own SOP instead."
VersionStatus = Literal["draft", "approved"]


class LibraryVersion(Wire):
    number: int
    text: str
    lang: str
    created_at: str
    created_by: str
    change_note: str = ""
    status: VersionStatus = "draft"
    steps: list[Step] = []
    approved_by: str | None = None
    approved_at: str | None = None
    read_only: bool = False


class LibraryEntry(Wire):
    id: str
    site_id: str
    title: str
    task_id: str | None = None
    seeded: bool = False
    versions: list[LibraryVersion] = []

    def version(self, n: int) -> LibraryVersion | None:
        return next((v for v in self.versions if v.number == n), None)

    def stored(self) -> dict[str, Any] | None:
        """What the store keeps: a seed's authored versions only (its seed version comes from the
        catalog), or None when there is nothing of the caller's to keep."""
        authored = [v.wire() for v in self.versions if not v.read_only]
        if self.seeded and not authored:
            return None
        return {**self.wire(), "versions": authored}


class NewSop(Wire):
    title: str
    text: str
    change_note: str = ""
    task_id: str | None = None
    lang: str | None = None


class NewVersion(Wire):
    text: str
    change_note: str = ""
    lang: str | None = None


class PutVersionSteps(Wire):
    steps: list[Step]


# Seeds and scope -------------------------------------------------------------------------------


def _seed_number(label: str) -> int:
    digits = "".join(c for c in label if c.isdigit())
    return int(digits) if digits else 1


def seeds(site_id: str) -> list[LibraryEntry]:
    """The catalog's tasks of this site, each an approved, read-only version."""
    cat = catalog.load_catalog()
    day = f"{cat.get('version', '2026-10-15')}T00:00:00.000Z"
    out = []
    for task in cat["tasks"]:
        if task.get("demoSite") != site_id:
            continue
        sop = task["sop"]
        version = LibraryVersion(
            number=_seed_number(sop["version"]),
            text=sop["text"],
            lang=SEED_LANG,
            created_at=day,
            created_by="catalog",
            change_note="From the demo catalog.",
            status="approved",
            steps=[Step.model_validate(s) for s in task["referenceSteps"]],
            approved_by="catalog",
            approved_at=day,
            read_only=True,
        )
        out.append(
            LibraryEntry(
                id=sop["id"],
                site_id=site_id,
                title=sop["title"],
                task_id=task["id"],
                seeded=True,
                versions=[version],
            )
        )
    return out


def scope_key(caller: Caller, site_id: str) -> str:
    """The store document's name: a SHA-256 of the site and the scope (the org with accounts, else
    the device-key hash). Never the device key, and never shown."""
    org = getattr(caller, "org_id", None)
    scope = f"org:{org}" if org else f"device:{caller.owner}"
    return hashlib.sha256(f"{site_id}\n{scope}".encode()).hexdigest()


def merged(site_id: str, doc: dict[str, Any] | None) -> list[LibraryEntry]:
    """The site's seeds, each with the caller's own later versions, then the caller's own SOPs."""
    entries = {e.id: e for e in seeds(site_id)}
    for raw in (doc or {}).get("sops", []):
        stored = LibraryEntry.model_validate(raw)
        seed = entries.get(stored.id)
        if seed is None:
            entries[stored.id] = stored.model_copy(update={"seeded": False, "site_id": site_id})
            continue
        last = seed.versions[-1].number
        later = [v for v in stored.versions if v.number > last and not v.read_only]
        entries[stored.id] = seed.model_copy(update={"versions": [*seed.versions, *later]})
    return list(entries.values())


def _require(caller: Caller, site_id: str, *roles: str) -> None:
    """auth.require_role: 403 `forbidden` with accounts, a no-op in device mode."""
    from sayitback.auth import require_role  # at call time: auth imports the API's middleware

    require_role(caller, site_id, *roles)


def _no_seed_version_without_accounts(caller: Caller, entry: LibraryEntry) -> None:
    """Security fixes A (H3): with no accounts every browser acts as a safety officer, so a seed
    takes no new version (403 `forbidden`); the caller's own SOPs keep the whole flow."""
    if entry.seeded and caller.org_id is None:
        from sayitback.auth import Forbidden  # at call time, as in _require

        raise Forbidden(CATALOGUE_READ_ONLY)


def _actor(caller: Caller, site_id: str, allowed: tuple[str, ...]) -> str:
    held = (getattr(caller, "roles", None) or {}).get(site_id, frozenset())
    return next((r for r in allowed if r in held), "device")


def _entry(entries: list[LibraryEntry], sop_id: str) -> LibraryEntry:
    found = next((e for e in entries if e.id == sop_id), None)
    if found is None:
        raise NotFound("SOP not found.", code="sop_not_found")
    return found


def _version(entry: LibraryEntry, n: int) -> LibraryVersion:
    found = entry.version(n)
    if found is None:
        raise NotFound("SOP version not found.", code="version_not_found")
    return found


def _draft(entry: LibraryEntry, n: int) -> LibraryVersion:
    version = _version(entry, n)
    if version.read_only:
        raise InvalidState(
            "This version comes from the catalog and is read-only.", code="read_only"
        )
    if version.status != "draft":
        raise InvalidState("An approved version never changes. Create a new version.")
    return version


def _stored_doc(site_id: str, entries: list[LibraryEntry]) -> dict[str, Any]:
    kept = [s for s in (e.stored() for e in entries) if s is not None]
    if len([e for e in entries if not e.seeded]) > MAX_ENTRIES:
        raise Unprocessable(f"A library holds at most {MAX_ENTRIES} SOPs.", code="library_full")
    doc = {"siteId": site_id, "sops": kept}
    if len(json.dumps(doc, ensure_ascii=False).encode()) > MAX_DOC_BYTES:
        raise Unprocessable("This library is full.", code="library_full")
    return doc


# The library -----------------------------------------------------------------------------------


class SopLibrary:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.s = settings

    def _site(self, site_id: str) -> None:
        if catalog.site(site_id) is None:
            raise NotFound(
                f"Unknown site {quote(site_id, self.s.max_echo_chars)}.", code="unknown_site"
            )

    async def list(self, caller: Caller, site_id: str) -> list[LibraryEntry]:
        self._site(site_id)
        _require(caller, site_id, *READ_ROLES)
        return merged(site_id, await self.store.get_sop_library(scope_key(caller, site_id)))

    async def get(self, caller: Caller, site_id: str, sop_id: str) -> LibraryEntry:
        return _entry(await self.list(caller, site_id), sop_id)

    async def _mutate(
        self, caller: Caller, site_id: str, roles: tuple[str, ...], change: Callable
    ) -> LibraryEntry:
        """Apply `change(entries)` (it returns the entry it changed) in one atomic store update."""
        self._site(site_id)
        _require(caller, site_id, *roles)
        changed: list[LibraryEntry] = []

        def apply(doc: dict[str, Any] | None) -> dict[str, Any]:
            entries = merged(site_id, doc)
            changed.append(change(entries))
            return _stored_doc(site_id, entries)

        await self.store.update_sop_library(scope_key(caller, site_id), apply)
        return changed[-1]

    def _text(self, value: str, field: str) -> str:
        return validators.clean_text(
            value, field=field, limit=self.s.max_custom_sop_chars, required=True
        )

    def _note(self, value: str) -> str:
        return validators.clean_text(value, field="changeNote", limit=MAX_NOTE_CHARS)

    async def create(self, caller: Caller, site_id: str, body: NewSop) -> LibraryEntry:
        """A new SOP with a draft version 1 and no steps yet."""
        title = validators.clean_text(
            body.title, field="title", limit=self.s.max_custom_sop_title_chars, required=True
        )
        text, note = self._text(body.text, "text"), self._note(body.change_note)
        if body.task_id is not None and catalog.task(body.task_id) is None:
            what = quote(body.task_id, self.s.max_echo_chars)
            raise Unprocessable(f"Unknown taskId {what}.", code="unknown_task")
        site = catalog.site(site_id) or {}
        lang = catalog.require_lang(body.lang or site.get("defaultSupervisorLanguage", "en"))
        actor = _actor(caller, site_id, DRAFT_ROLES)

        def change(entries: list[LibraryEntry]) -> LibraryEntry:
            entry = LibraryEntry(
                id="sop_" + base64.b32encode(secrets.token_bytes(8)).decode().lower()[:10],
                site_id=site_id,
                title=title,
                task_id=body.task_id,
                versions=[_new_version(1, text, lang, actor, note, [])],
            )
            entries.append(entry)
            return entry

        return await self._mutate(caller, site_id, DRAFT_ROLES, change)

    async def add_version(
        self, caller: Caller, site_id: str, sop_id: str, body: NewVersion
    ) -> LibraryEntry:
        """A draft of the next number, starting from the latest approved version's steps."""
        text, note = self._text(body.text, "text"), self._note(body.change_note)
        lang = catalog.require_lang(body.lang) if body.lang else None
        actor = _actor(caller, site_id, DRAFT_ROLES)

        def change(entries: list[LibraryEntry]) -> LibraryEntry:
            entry = _entry(entries, sop_id)
            _no_seed_version_without_accounts(caller, entry)
            if any(v.status == "draft" for v in entry.versions):
                raise InvalidState("This SOP already has a draft version.", code="draft_exists")
            if len(entry.versions) >= MAX_VERSIONS:
                raise Unprocessable(f"At most {MAX_VERSIONS} versions.", code="library_full")
            approved = [v for v in entry.versions if v.status == "approved"]
            base = approved[-1] if approved else entry.versions[-1]
            steps = [s.model_copy() for s in approved[-1].steps] if approved else []
            number = entry.versions[-1].number + 1
            entry.versions.append(_new_version(number, text, lang or base.lang, actor, note, steps))
            return entry

        return await self._mutate(caller, site_id, DRAFT_ROLES, change)

    async def set_steps(
        self, caller: Caller, site_id: str, sop_id: str, n: int, items: list[Step]
    ) -> LibraryEntry:
        steps = validators.steps(items, self.s)

        def change(entries: list[LibraryEntry]) -> LibraryEntry:
            entry = _entry(entries, sop_id)
            _draft(entry, n).steps = steps
            return entry

        return await self._mutate(caller, site_id, DRAFT_ROLES, change)

    async def approve(self, caller: Caller, site_id: str, sop_id: str, n: int) -> LibraryEntry:
        """A safety officer approves a draft's steps; from then on it never changes."""
        actor = _actor(caller, site_id, APPROVE_ROLES)

        def change(entries: list[LibraryEntry]) -> LibraryEntry:
            entry = _entry(entries, sop_id)
            version = _draft(entry, n)
            if not version.steps:
                raise Unprocessable(
                    "Set the critical steps before approving.", code="steps_required"
                )
            version.steps = _with_essentials(version.steps)
            version.status, version.approved_by, version.approved_at = "approved", actor, now_iso()
            return entry

        return await self._mutate(caller, site_id, APPROVE_ROLES, change)

    # Briefings (endpoint 4 with sopRef, and the steps phase) ------------------------------------

    async def _approved(
        self, caller: Caller, site_id: str, ref: SopRef
    ) -> tuple[LibraryEntry, LibraryVersion]:
        try:
            entry = await self.get(caller, site_id, ref.sop_id)
            version = _version(entry, ref.version)
        except NotFound as missing:
            raise Unprocessable(
                "sopRef names no version of this site's library.", code="unknown_sop"
            ) from missing
        if version.status != "approved":
            raise Unprocessable(
                "Only an approved SOP version can start a briefing.", code="sop_not_approved"
            )
        return entry, version

    async def briefing_sop(self, caller: Caller, body: CreateBriefing) -> Sop:
        """The SOP a briefing with `sopRef` carries: the approved version's text, its number as
        the version. Its task must be the briefing's (an SOP with no task: "custom"), and its steps
        must be in the supervisor's language, since the supervisor confirms them."""
        assert body.sop_ref is not None
        if body.sop is not None:
            raise Unprocessable("Send sop or sopRef, not both.", code="sop_conflict")
        entry, version = await self._approved(caller, body.site_id, body.sop_ref)
        if body.task_id != (entry.task_id or catalog.CUSTOM_TASK_ID):
            raise Unprocessable("sopRef is the SOP of another task.", code="sop_task_mismatch")
        if version.lang != body.supervisor_lang:
            raise Unprocessable(
                "This SOP version's steps are in another language than the supervisor's.",
                code="sop_language_mismatch",
            )
        return Sop(id=entry.id, version=f"v{version.number}", title=entry.title, text=version.text)

    async def approved_steps(self, caller: Caller, site_id: str, ref: SopRef) -> list[Step]:
        """The steps phase of a library briefing: the approved steps, no model call."""
        _entry_, version = await self._approved(caller, site_id, ref)
        return [s.model_copy(deep=True) for s in version.steps]


def _with_essentials(steps: list[Step]) -> list[Step]:
    """At sign-off, a step with no "what the worker must state" gets its own text as its one
    essential (17 Oct, note 36-a open issue 3): the library editor has no such field, and the judge
    needs one, so this is the default the Steps screen gives a hand-added step. Done at sign-off,
    not on every save, so a draft edited after a reload never keeps an essential of its old text."""
    return [s if s.essential else s.model_copy(update={"essential": [s.text]}) for s in steps]


def _new_version(
    number: int, text: str, lang: str, actor: str, note: str, steps: list[Step]
) -> LibraryVersion:
    return LibraryVersion(
        number=number, text=text, lang=lang, created_at=now_iso(), created_by=actor,
        change_note=note, steps=steps,
    )  # fmt: skip


__all__ = ["SOP_ID_PATTERN", "LibraryEntry", "LibraryVersion", "SopLibrary", "merged", "seeds"]
