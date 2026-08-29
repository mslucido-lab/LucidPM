# LucidoPM — ChatGPT Handoff 52
*Dynamic Clause Numbering + Cross-References for Assembled Lease Packages*
*Prepared: 2026-08-27*

---

## What This Is

Right now, clause numbers in the amendment/lease clauses Mark authors in the Section Library are **hardcoded literals**. Two separate places:

1. **The visible number** is baked into each clause's `<para bulletText="...">` attribute — e.g. `<para bulletText="3.">` for the Holdover clause, and `bulletText="4."`, `"5."`, `"6."` for the three clauses that share the "Force and Effect" section's Content.
2. **In-prose cross-references** — e.g. "Section 3 of the Lease", and (in the sample PDF Mark attached) *"the lease Option as described in **Section 5** of the First Amendment"* — which is already wrong: the Option clause renders as clause 3, not 5.

If Mark inserts a clause in the middle he has to hand-renumber every `bulletText` below it **and** fix every prose cross-reference. This handoff makes both automatic.

**A half-built mechanism already exists and is explicitly being superseded, not extended:** the `{{SectionNumber}}` token (`lease_package_builder.py` — `_uses_dynamic_section_number`, `_section_consumes_section_number`, `_inject_display_label_after_section_number`, `_compose_section_render_text`). It is used by exactly one section (Prod `LeaseDocumentSections.LeaseDocumentSectionID = 41`, "Option"), which is currently **inactive**. Its limitations make it a dead end for this use case: it assumes exactly one number per section, the token must sit at the very start of the Content, it rebuilds the whole line into a bold heading (`**3. Option**`) which is the wrong format for hanging-indent `<para bulletText="N."><u>Label:</u> …</para>` amendment clauses, and it cannot handle three numbered clauses inside one section's Content. **Leave all of that `{{SectionNumber}}` code in place and working** (back-compat). This handoff's new tokens are the forward path; the inactive "Option" clause (lds 41) that still uses `{{SectionNumber}}` is **left exactly as-is — do not touch it, do not migrate it, do not touch its metadata.** (Migrating it is a deliberately-deferred follow-up; see "Known limitation".)

**Design, finalized with Mark before writing this handoff:**

- Two new token families, resolved **once per package, across all sections in document order** — not per-section, because their value depends on position in the assembled document, not on lease/tenant data:
  - **`{{ClauseNumber}}`** — emits the next sequential clause number (1, 2, 3, …) and advances the counter. Author writes it inside the bullet: `<para bulletText="{{ClauseNumber}}." …>`. Sub-items (`a.`, `b.`, `i.`) stay literal.
  - **`{{ClauseNumber:Anchor}}`** — same as `{{ClauseNumber}}`, and additionally records `Anchor → that number` for cross-referencing. (`Anchor` = letters/digits/underscore/hyphen.)
  - **`{{ClauseRef:Anchor}}`** — emits the number recorded for `Anchor`, with **no** increment. Usable anywhere, including in a clause that appears *before* the anchor definition (forward references resolve — see two-pass note below).
- Resolution is a **two-pass** operation over the ordered list of section texts: pass 1 walks every text in document order and fills every `{{ClauseNumber}}` / `{{ClauseNumber:Anchor}}`, building the anchor map; pass 2 fills every `{{ClauseRef:Anchor}}`. An unknown anchor is left in place and **blocks generation** with a clear actionable error, exactly like any other missing token.
- The pass runs on **raw Content, in document order, before** the existing per-section token rendering — clause numbers don't depend on any other token, and doing it first keeps it away from the fragile `{{SectionNumber}}` mixed-mode logic entirely.
- PDF-only / static sections contribute nothing to the counter (their numbering is baked into the PDF itself).
- The operation is **idempotent**: text with no clause tokens passes through untouched. This matters for the regenerate path, which re-renders frozen `ContentSnapshot` values that already have literal numbers baked in.

**Known limitations, to document, not solve here:**

- **Cross-referencing an excludable clause:** `{{ClauseRef:Anchor}}` in a clause that renders will block generation if the anchor-defining clause is *excluded* from that package. Rule for Mark: only cross-reference a clause guaranteed to be included whenever the referencing clause is. A future `{{ClauseRef:Anchor|fallback text}}` syntax could soften this; out of scope now.
- **The inactive "Option" clause (lds 41) is not migrated in this handoff** (Mark's explicit call). While it still uses `{{SectionNumber}}`, activating it in a package alongside the new `{{ClauseNumber}}` clauses would produce a **wrong number** for the Option clause — the two counters are independent (`{{SectionNumber}}`'s counter only counts `{{SectionNumber}}` sections). So: do not activate the "Option" section until a later change migrates it to `{{ClauseNumber:Option}}`. Note this in the doc (Part F).

**Files that change:** `LucidPM/lease_merge.py` (new helper + patterns), `LucidPM/pages/lease_package_builder.py` (wire the pass into all four render/validate paths), `LucidPM/pages/lease_documents.py` (token-picker buttons), a **data update to the Production `TenantCRM` database** (five active template-2 clause rows), `LucidoPM_ProjectContext_v2_1.md` (doc), and `CLAUDE.md` "Where We Left Off". **No schema change. No PDF-renderer change.**

**Explicit scope constraint:** this handoff does **not** refactor the three near-duplicate per-section render loops in `lease_package_builder.py` into one shared method, does not touch the `{{SectionNumber}}` code paths, does not touch the inactive "Option" section (lds 41) or its metadata, and does not touch the Test-DB `LeaseTemplateID = 2` ("NEW CORE LEASE" — an unrelated template that happens to share the ID). Only the five **active** Production `TenantCRM` `LeaseTemplateID = 2` ("Amendment Template - Standard") clause rows get data changes.

---

## Current State

### `LucidPM/lease_merge.py`

- `TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_\.\-]+)\s*\}\}")` (line 34). **No colon** in the character class, so `{{ClauseNumber:Option}}` and `{{ClauseRef:Option}}` are invisible to `extract_tokens()` / `validate_template_tokens()` — they will *not* be reported as missing tokens. Only bare `{{ClauseNumber}}` matches `TOKEN_PATTERN` and would be reported missing.
- `render_text_template(template_text, context) -> (rendered, unresolved)` (line 1003) — regex-substitutes `TOKEN_PATTERN`; unknown tokens go into `unresolved`.
- `extract_tokens()` (1023), `validate_template_tokens()` (1027).
- End of module: backward-compat aliases (`build_lease_context`, `merge_template`, `find_unresolved_tokens`) around lines 1042-1054.

### `LucidPM/pages/lease_package_builder.py`

Imports from `lease_merge` at lines 78-82: `get_lease_merge_context`, `render_text_template`, `validate_template_tokens`.

**`_validate_tokens_before_generation()`** (lines ~1406-1426) — note it currently has an accidental **doubled** filter block:

```python
            validation["missing"] = [
                t for t in (validation.get("missing", []) or [])
                if str(t) != "SectionNumber"
            ]
            validation["missing"] = [
                t for t in (validation.get("missing", []) or [])
                if str(t) != "SectionNumber"
            ]
```

**Four code paths** render or validate section Content and need the new pass:

| Method | Loop marker | Notes |
|---|---|---|
| `generate_package()` | `section_number = 1` at ~line 1506; `for idx, p in enumerate(selected, start=1):` at ~1519 | The real generation path. `selected` is document-ordered. |
| `generate_merge_preview()` | `section_number = 1` at ~1683 | Text preview, no PDF/DB writes. |
| `preview_regenerate_selected_generated_package()` | loop `for idx, row in enumerate(rows, start=1):` at ~2030 | **Validation only** — calls `validate_template_tokens`, does not call `render_text_template`. |
| `regenerate_selected_generated_package()` | `section_number = 1` at ~2147 | Re-renders frozen `LeasePackageSections` rows into a new version. `rows` is ordered. |

All three rendering loops share this shape:
```python
                    section_context = {**context, "SectionNumber": str(section_number)}
                    rendered_text, unresolved = render_text_template(content, section_context) if content else ("", [])
                    if unresolved:
                        # ... build actionable error, return
```
`SectionNumber` never trips `if unresolved:` because it is injected into `section_context`. Bare `{{ClauseNumber}}` **would** trip it — so it must be filtered.

### Production `TenantCRM` — `LeaseTemplateID = 2` ("Amendment Template - Standard")

Template sections in `SortOrder`, joined to `LeaseDocumentSections` (`lds`):

| Sort | TemplateSectionID | Label | lds ID | lds.ArticleNumber / DisplayLabel | Numbering in Content today |
|---|---|---|---|---|---|
| 10 | 37 | Header | 43 | – / – | none |
| 20 | 38 | RECITALS | 44 | – / – | `bulletText="A."` (recital, leave) |
| 30 | 39 | Consideration *(optional, inactive)* | 45 | – / – | none |
| 40 | 40 | Article 1 | 46 | – / – | `bulletText="1."` |
| 50 | 41 | Article 2 | 47 | – / – | `bulletText="2."` |
| 60 | 42 | Payment Schedule | 48 | – / – | `bulletText="a."` (sub-item of Article 2, leave) |
| 70 | 1053 | Option *(optional, inactive)* | 41 | `3` / `Option` | `{{SectionNumber}}. Provided that Tenant …` |
| 80 | 43 | Holdover | 49 | – / – | `bulletText="3."`; prose "Section 3 of the Lease" |
| 90 | 44 | Force and Effect | 50 | – / – | three `<para>`: `bulletText="4."`, `"5."`, `"6."` (Estoppel / Ratification / Counterparts) |
| 100 | 45 | Signature Page | 52 | – / – | static PDF |

"Section 3 of the Lease" in Holdover (lds 49) is a reference to the **original lease**, not this amendment — it stays a literal.

---

## The Fix

### Part A — `LucidPM/lease_merge.py`: new patterns + `apply_clause_numbering()`

Add near `TOKEN_PATTERN` (after line 34):

```python
# Document-wide clause numbering tokens. Resolved once per assembled package,
# across all sections in document order, by apply_clause_numbering() -- NOT via
# TOKEN_PATTERN / the per-section context, because their value depends on
# position in the final document, not on lease data.
#   {{ClauseNumber}}         -> next sequential clause number; advances counter
#   {{ClauseNumber:Anchor}}  -> same, and records Anchor -> that number
#   {{ClauseRef:Anchor}}     -> the number recorded for Anchor; no increment
CLAUSE_NUMBER_PATTERN = re.compile(r"\{\{\s*ClauseNumber(?:\s*:\s*([A-Za-z0-9_\-]+))?\s*\}\}")
CLAUSE_REF_PATTERN = re.compile(r"\{\{\s*ClauseRef\s*:\s*([A-Za-z0-9_\-]+)\s*\}\}")
```

Add this function near the other public helpers (e.g. just above the backward-compat aliases at the end of the module):

```python
def apply_clause_numbering(
    section_texts: list[str], start: int = 1
) -> tuple[list[str], list[str]]:
    """Resolve {{ClauseNumber}} / {{ClauseNumber:anchor}} / {{ClauseRef:anchor}}
    across an ordered list of section texts.

    Pass 1 walks the list in order and replaces each {{ClauseNumber}} /
    {{ClauseNumber:anchor}} with the next integer (counting from `start`),
    recording each anchor -> number.
    Pass 2 replaces each {{ClauseRef:anchor}} with the recorded integer.

    Returns (resolved_texts, unresolved_refs). unresolved_refs holds the names
    of any {{ClauseRef:...}} whose anchor was never defined; those refs are left
    verbatim in the text so the caller can block generation, exactly like any
    other missing token. If an anchor is defined more than once, the last
    definition in document order wins.

    Idempotent: a text with no clause tokens is returned unchanged.
    """
    counter = int(start) - 1
    anchors: dict[str, int] = {}

    def _assign(match: "re.Match[str]") -> str:
        nonlocal counter
        counter += 1
        anchor = match.group(1)
        if anchor:
            anchors[anchor] = counter
        return str(counter)

    pass1 = [CLAUSE_NUMBER_PATTERN.sub(_assign, text or "") for text in section_texts]

    unresolved: list[str] = []

    def _ref(match: "re.Match[str]") -> str:
        anchor = match.group(1)
        if anchor in anchors:
            return str(anchors[anchor])
        unresolved.append(f"ClauseRef:{anchor}")
        return match.group(0)

    pass2 = [CLAUSE_REF_PATTERN.sub(_ref, text) for text in pass1]
    return pass2, sorted(set(unresolved))
```

> `nonlocal counter` in a module-level function closure is fine. The two `sub` closures are defined once, not per loop iteration.

### Part B — `LucidPM/pages/lease_package_builder.py`: import + shared filter

**B1.** Extend the `lease_merge` import (lines 78-82):

```python
from LucidPM.lease_merge import (
    get_lease_merge_context,
    render_text_template,
    validate_template_tokens,
    apply_clause_numbering,
)
```

**B2.** Add a module-level constant + helper near the top of the file (e.g. just after `RESPONSIVE_COMPACT_GRID_STYLE`, ~line 95):

```python
# Tokens resolved outside the per-section context: SectionNumber is injected
# per-section by the legacy dynamic-heading path; ClauseNumber is resolved
# document-wide by apply_clause_numbering(). Neither should ever be reported as
# a missing token.
DOCUMENT_LEVEL_TOKENS = {"SectionNumber", "ClauseNumber"}


def _drop_document_level_tokens(tokens) -> list:
    return [t for t in (tokens or []) if str(t) not in DOCUMENT_LEVEL_TOKENS]
```

**B3.** Fix `_validate_tokens_before_generation()` — replace the doubled `SectionNumber` filter block with one call:

```python
            validation = validate_template_tokens(content, context)
            unresolved = _drop_document_level_tokens(validation.get("missing", []))
            if unresolved:
                label = p.template_section_label or p.section_name
                errors.append(f"{label}: " + ", ".join(sorted(set(unresolved))[:10]))
```

### Part C — wire `apply_clause_numbering()` into the four paths

The pattern is identical everywhere: build the ordered list of raw text (only for sections that actually render as text — never static PDFs), run the pass, block on unresolved refs, then use the numbered text in place of the original Content.

#### C1. `generate_package()`

After `context = get_lease_merge_context(...)` and the `token_errors` check (~line 1499), **before** `pdf_paths_to_merge: list[str] = []`:

```python
            # Resolve document-wide clause numbering on raw Content, in document
            # order, before per-section token rendering. Static/PDF-only sections
            # contribute "" and never advance the counter.
            numbered_contents, unresolved_refs = apply_clause_numbering(
                [
                    str(p.content or "") if self._has_renderable_text(p) else ""
                    for p in selected
                ]
            )
            if unresolved_refs:
                self.form_error = _format_actionable_errors(
                    "Fix these clause cross-references before generating "
                    "(no included clause defines this anchor):",
                    unresolved_refs,
                )
                return
```

Then in the `for idx, p in enumerate(selected, start=1):` loop, change the first line from:

```python
                content = str(p.content or "").strip()
```
to:
```python
                content = str(numbered_contents[idx - 1] or "").strip()
```

Leave every other reference to `p.content` / `_uses_dynamic_section_number(p)` as-is — those legitimately inspect the original Content for the untouched `{{SectionNumber}}` path.

#### C2. `generate_merge_preview()`

Same insert after `context = get_lease_merge_context(...)` (~line 1681), before the `for idx, section in enumerate(selected, start=1):` loop:

```python
            numbered_contents, unresolved_refs = apply_clause_numbering(
                [
                    str(s.content or "") if self._has_renderable_text(s) else ""
                    for s in selected
                ]
            )
            if unresolved_refs:
                self.merge_error = _format_actionable_errors(
                    "Preview blocked. Fix these clause cross-references "
                    "(no included clause defines this anchor):",
                    unresolved_refs,
                )
                return
```

In the loop, change `content = str(section.content or "").strip()` to `content = str(numbered_contents[idx - 1] or "").strip()`.

#### C3 / C4. `preview_regenerate_selected_generated_package()` and `regenerate_selected_generated_package()` — **do NOT wire the numbering pass in**

*(Revised after code review — an earlier draft of this handoff wired `apply_clause_numbering` into these two paths. That was wrong and has been removed from the implementation.)*

Regeneration is **snapshot-based**: `LeasePackageSections` rows are frozen at generation, and their `ContentSnapshot` already contains fully-resolved literal clause numbers. `apply_clause_numbering` only sees tokens *still present* in the text, so running it over a mix of frozen snapshots and one hand-edited section would restart the counter from 1 and misnumber the edited section.

So in both methods: leave `text_to_render = content or snapshot` and `unresolved = validation.get("missing", []) or []` **unchanged from their pre-handoff form.** Add only a comment explaining why the pass is deliberately not run here.

A manual edit in the generated-section editor that (re)introduces `{{ClauseNumber}}` is caught as an unresolved token by the existing post-render guard and blocks regeneration — which is the intended behavior: manual edits should use a literal number, and renumbering is done by generating a fresh package.

> Frozen `ContentSnapshot` values keep their resolved numbers. Regenerate has never picked up newly-inserted template sections and still won't — generate a fresh package to renumber. Documented in Part F.

### Part D — token picker (`LucidPM/pages/lease_documents.py`)

In `_available_token_buttons_panel()` (~line 3239), add a new group. Put it right after the `"Header"` group (after line 3254) so it's near the top:

```python
            _token_group("Clause Numbering", [
                "{{ClauseNumber}}",
                "{{ClauseNumber:Anchor}}",
                "{{ClauseRef:Anchor}}",
            ], target_id),
```

Add a one-line caption via an extra `rx.text` inside that group, or rely on the panel's existing "Click a token to insert it" note plus the doc. Suggested caption text: *"Use inside bulletText: `<para bulletText=\"{{ClauseNumber}}.\">`. Replace `Anchor` with a short name to cross-reference a clause elsewhere with `{{ClauseRef:Anchor}}`."*

Leave `{{SectionNumber}}` in the "Header" group (back-compat) but it is no longer the recommended path.

### Part E — Production `TenantCRM` data update (LeaseTemplateID 2 clauses)

Run against **`TenantCRM` only** (Production). The Test DB's `LeaseTemplateID = 2` is a different template — do not touch it. **Do not touch the inactive "Option" section, lds 41** — no Content change, no metadata change, nothing. Do these as `UPDATE dbo.LeaseDocumentSections SET Content = ? WHERE LeaseDocumentSectionID = ?` statements. Keep a copy of the pre-update Content for each row in the commit message or a scratch file.

Five active rows, `bulletText` swap only — the surrounding wording, tokens, and `<para>` attributes stay exactly as they are:

| lds ID | Change |
|---|---|
| **46** (Article 1 / Effective Date) | In Content, replace `bulletText="1."` with `bulletText="{{ClauseNumber}}."` |
| **47** (Article 2 / Extension) | Replace `bulletText="2."` with `bulletText="{{ClauseNumber}}."` |
| **49** (Holdover) | Replace `bulletText="3."` with `bulletText="{{ClauseNumber}}."`. **Leave** "Section 3 of the Lease" as-is (refers to the original lease, not this amendment). |
| **50** (Force and Effect) | Replace all three `bulletText="4."`, `bulletText="5."`, `bulletText="6."` with `bulletText="{{ClauseNumber}}."` (three occurrences, in document order — Estoppel, Ratification, Counterparts). |

After this change, with the "Option" section excluded (its normal state), the amendment renders: 1 Effective Date, 2 Extension of Term, 3 Holdover, 4 Estoppel, 5 Ratification, 6 Counterparts — and inserting any new `{{ClauseNumber}}` clause between them renumbers everything below automatically.

**Cross-references:** none of the five active clauses currently reference another amendment clause by number, so there is no `{{ClauseRef:...}}` to add here. When Mark next authors a clause that needs to point at another *active* clause, he tags the target with `{{ClauseNumber:SomeName}}` and references it with `{{ClauseRef:SomeName}}`. (The "Section 5 of the First Amendment" text in the sample PDF was a manual post-generation edit pointing at the still-inactive Option clause; it's not in the template and is not addressed here.)

### Part F — docs

- **`LucidoPM_ProjectContext_v2_1.md`** — add a "Clause numbering" subsection under the lease-generation architecture: the three tokens, the two-pass document-order resolution, that it runs before per-section token rendering, that static PDFs don't count, the optional-section cross-ref caveat, and the regenerate-doesn't-renumber-inserted-sections note.
- **`CLAUDE.md` → "Where We Left Off"** — record this handoff shipping and that `{{SectionNumber}}` is now legacy/superseded by `{{ClauseNumber}}`.

---

## Do Not Touch

| What | Why |
|---|---|
| `_uses_dynamic_section_number`, `_section_consumes_section_number`, `_inject_display_label_after_section_number`, `_compose_section_render_text` and every other `{{SectionNumber}}` code path | Kept working for back-compat. The new pass runs *before* rendering and on a different token, so there is zero interaction. |
| The inactive "Option" section — `LeaseDocumentSections` id **41**, `LeaseTemplateSectionID` 1053 — its Content, its `{{SectionNumber}}` token, its `ArticleNumber`/`DisplayLabel` | Mark's explicit instruction: do not touch the inactive clause. Migrating it to `{{ClauseNumber:Option}}` is a deferred follow-up, not this handoff. |
| The three per-section render loops' overall structure | Explicitly not consolidating them in this handoff — minimal, surgical edits only. |
| `TOKEN_PATTERN` | `{{ClauseNumber:...}}` / `{{ClauseRef:...}}` are deliberately outside it. Do not widen it to include colons. |
| `lease_documents_pdf.py` (the renderer) | `bulletText="3."` after substitution is just a normal attribute value; `_para_tag_flowable` already handles it. No renderer change. |
| Test DB `LeaseTemplateID = 2` ("NEW CORE LEASE") | Unrelated template, same ID by coincidence. Data changes are Production `TenantCRM` only. |
| `LeaseDocumentSections` schema, `LeaseTemplateSections`, `LeasePackageSections` | No schema change anywhere. |
| Recital bullets (`bulletText="A."` in lds 44) and sub-item bullets (`bulletText="a."` in lds 48) | Those are not top-level numbered clauses; they stay literal. |

---

## Validation Checklist

- [ ] `apply_clause_numbering(["<para bulletText='{{ClauseNumber}}.'>x</para>", "y {{ClauseRef:Z}}", "{{ClauseNumber:Z}} z"])` returns numbers `1` / `2` and resolves the ref to `2`; forward reference works.
- [ ] `apply_clause_numbering` with an undefined `{{ClauseRef:Missing}}` returns it in the second tuple element and leaves the token in the text.
- [ ] `apply_clause_numbering` on text with no clause tokens returns it byte-for-byte unchanged (idempotency).
- [ ] Generate a package from Production `TenantCRM` `LeaseTemplateID = 2` (Option stays excluded — its normal state): clauses render 1 (Effective Date), 2 (Extension), 3 (Holdover), 4 (Estoppel), 5 (Ratification), 6 (Counterparts). No `{{...}}` leaks into the PDF. No "missing token" error for `ClauseNumber`.
- [ ] Temporarily insert a new `{{ClauseNumber}}` clause between Article 2 and Holdover → Holdover becomes 4, Estoppel 5, Ratification 6, Counterparts 7 automatically; remove it afterward.
- [ ] Temporarily add a section with `Section {{ClauseNumber:Foo}}` and another (always-included) with `see Section {{ClauseRef:Foo}}` → the ref resolves to Foo's number, including when the ref clause sits *before* the Foo clause (forward reference).
- [ ] Temporarily add `see Section {{ClauseRef:Missing}}` to an included clause → generation is blocked with a clear "no included clause defines this anchor: ClauseRef:Missing" message (not a raw token in the PDF, not a stack trace).
- [ ] Merge Preview shows the same numbering as the generated PDF.
- [ ] Regenerate an existing pre-change generated package: still succeeds, numbers unchanged (snapshots are idempotent).
- [ ] Edit a generated section's text to include a `{{ClauseNumber}}` token, save, regenerate → the token resolves in the new version.
- [ ] Section Library token picker shows a "Clause Numbering" group with the three buttons; clicking inserts at cursor.
- [ ] The inactive "Option" section (lds 41) is byte-for-byte unchanged in the DB — Content, `ArticleNumber`, `DisplayLabel` all as before.
- [ ] All 17 registered pages compile; `reflex run --backend-only` starts clean.

---

## How to Deliver This

Per `CLAUDE.md`: edit live files in place, no `_vN` files.

1. Part A — `lease_merge.py` helper + patterns.
2. Part B + C — `lease_package_builder.py` import, shared filter, and the four wiring points.
3. Part D — `lease_documents.py` token picker.
4. Part E — Production `TenantCRM` data update: four `LeaseDocumentSections` Content edits (ids 46, 47, 49, 50 — `bulletText` swap only). Keep the pre-edit Content values. **lds 41 is not touched.**
5. Part F — docs + `CLAUDE.md`.
6. Verify against the checklist.
7. Commit (e.g. "Add {{ClauseNumber}}/{{ClauseRef}} dynamic clause numbering for lease packages"). The Production data edits can be a second commit ("Switch Amendment Template 2 active clauses to {{ClauseNumber}}").

If `lease_package_builder.py` has no un-archived `_vN` siblings, per `CLAUDE.md`'s incremental-cleanup rule, move any `lease_package_builder_v*.py` / `pages/lease_package_builder/` duplicates into `Archived Versions/` after the change is verified, as a separate commit. Same for `lease_merge_v*.py` / `lease_documents_pdf` is untouched so leave its siblings.

---

## File Locations

```
C:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\lease_merge.py                     ← Part A
  LucidPM\pages\lease_package_builder.py     ← Parts B, C
  LucidPM\pages\lease_documents.py           ← Part D
  LucidoPM_ProjectContext_v2_1.md  (TenantCRM root)  ← Part F
  CLAUDE.md                                  ← Part F

Production DB: TenantCRM  (red banner)  — Part E data update, LeaseTemplateID 2, active rows only (lds 46/47/49/50)
Frontend: http://localhost:3000   Backend: http://localhost:8000
```

---

*One document-wide two-pass numbering function in `lease_merge.py`, wired into four render/validate paths in the package builder, plus a `bulletText` swap on the four active numbered-clause rows of Amendment Template 2 (`"N."` → `"{{ClauseNumber}}."`). The legacy `{{SectionNumber}}` machinery — and the one inactive clause that uses it — stay untouched; migrating that clause is a deferred follow-up. Cross-references via named anchors; referencing a clause that isn't in the package is a documented hard-block, not a silent wrong number.*
