# Firmware / support-status research recipe

Distilled procedure for the recurring question class: "is there updated or custom firmware for device X?" (validated end-to-end on a consumer DAP firmware-absence query: official-absence + forum-absence + GitHub-absence triangulated in ~10 tool calls).

## Evidence hierarchy — check in this order

1. **Vendor download page for the EXACT model.** Look at the TYPES list, not the marketing: a model with firmware available lists a firmware file type; a model with none lists only Manual / USB Driver. State "no firmware file published, as of <date>" — absence on the vendor's own channel is the primary evidence for "no update exists".
2. **Official forum firmware category.** Fetch its RSS variant (`<category-url>.rss`) — the RSS lists every release thread complete at HTTP tier, while the category HTML is a JS SPA that returns nav-only without escalation. Absence of any thread for the exact model (through the current date) confirms the download page. Threads for SIBLING models carry date-stamped release cadence — that tells you whether updates are live-but-pending or the line is effectively EOL.
3. **Cross-flash hazard in sibling releases.** Sibling-model firmware notes often state in bold which models a release is NOT compatible with and what it bricks. Quote this verbatim in the report — it is a safety-critical finding, and it is also evidence that the vendor keeps model-specific firmware strictly separate (a "just flash the newer sibling's build" answer is wrong).
4. **Review-unit firmware versions.** Professional reviews published near launch state the shipping version of the sample. This gives the baseline version the current fleet sits on when no update has shipped.
5. **GitHub landscape for custom firmware.** Three probes, all via execute_code against `api.github.com` (NOT the web fetch tool — GitHub JSON floods context; see pitfall below): (a) `search/repositories?q=<model>+<custom-firmware terms>` per model name and nickname; (b) the upstream replacement-firmware project's supported-targets tree (`repos/<org>/<repo>/contents/<platform-dir>?ref=master`) — a target dir named after the model means official support, its absence means any port is unofficial; (c) follow the port author's own repos (`users/<user>/repos`) and the maintainer-referencing forks. Print only name / pushed_at / description.
6. **Community forums for hackability notes.** Search Head-Fi/xda/Discord-adjacent threads for the model name + custom firmware — snippets alone support or refute "nobody has ported it". A deleted-tool result (404 on the linked repo) still counts as negative evidence: note it as "tooling existed, now removed", never as a live option.

## Report shape for absence answers

- Lead with the absence verdict per channel: official = none published; custom = none exists; closest-alternative = <named port for the sibling model, one-click linked>.
- Include the update mechanism the user will use later (e.g. `update.bin` on microSD via System Update) so the next check is mechanical.
- Date-stamp every absence claim; a firmware-status report is only valid as of its check date.

## Pitfalls

- **Same-vendor model name match is NOT compatibility.** Successor/sibling DAP models sharing an SoC run model-specific firmware images; cross-flashing bricks the device. Never recommend a sibling build.
- **Upstream OSS 'platform' support ≠ model support.** A mainline open-source firmware can support the SoC family (e.g. one device per SoC in the tree) without supporting your model — check the target directory, not the SoC's datasheet.
- **api.github.com via web fetch = context flood.** GitHub REST responses embed the full repo object per hit; enumerate via execute_code and filter the print.
- **JS SPA product pages hide their listing.** If the download page TYPES list looks suspiciously empty, confirm against the RSS/forum channel before declaring absence — but note the reverse also holds: an empty TYPES list on a JS-rendered vendor page after prewarmed fetch IS the evidence.
