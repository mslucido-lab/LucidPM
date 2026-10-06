Refine Lease Template process to make the flow more intuitive.  AFter using for some time now, the 2 most common modules you're working with are Package Templates and Section Library. Package templates seem to be the main entity that contains the individual sections so this module is used when creating or modifying template.  You would also use it to discover which sections are in which template.  Section Library is used most frequently for modifying  the body of a section.  Parse and section is used when creating a new section.  Load is the least used module only when loading a new PDF and splitting it.

Right now the flow is not intuitive and I find myself hopping around between the modules. It would also be great to copy sections to make it easier to modify certain parts within a section.

THe token display is getting large so we may need to look at a better way to present those to the user and for searching/discovering.  Maybe even a hover over description for each would help.

When working in the section library I also find myself having to flip back and forth to the parse & section module because not all the section fields are listed in the library.


Clickable prototype: https://claude.ai/code/artifact/3ef97d8a-0fc8-43a7-8799-d2f88b5b13a9

It's wired to your real Production data — the 4 templates (Shared 36, Amendment Standard 10, Month-to-Month 11, Option Extension 4), all 61 sections, ~120 tokens. Nothing writes back to LucidPM; your edits persist in the browser (localStorage) with a Reset button up top.

What actually works:

Template rail → pick one, its slots load in the middle
Slots — click to open the section, reorder with ▲▼, remove, + Add existing section / + New section
Full section editor (right) — every field: type, internal name, exhibit, article #, display label, tag, reusable/active, content. Save enables on edit, shows a dirty dot.
Token picker — type to filter ~120 tokens across name + description; each row shows a live value; ƒ marks computed tokens; click inserts at cursor
Duplicate… — makes "Copy of X", opens it, optional one-click "add to this template"
Used in: N templates — the reverse lookup, click a name to jump the rail
Browse all sections — the slide-over: search / filter by type / group by tag or type, "in N tpl" counts, opens a section into the editor (no template needed)
Try: open Amendment Template – Standard → click the Force and Effect slot → search "rent" in the token picker → hit Duplicate.

Still the four questions from before, now that you can feel it:

Browse as a slide-over (current) vs a full tab?
Token preview values need a lease — pin one sample lease per template, or a global "preview as…" picker?
Merge Duplicate with the existing "Save Draft as New Section", or keep both?
Anything in the flow that's wrong once you click through it?