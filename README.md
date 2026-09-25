# model3d-studio

A web service where you provide drawings (CAD · PDF) and photos, and AI agents read the drawings, build 3D models
and review them in parallel for each member and section. Wherever the drawings are hard to interpret, the service
asks the user a question together with a crop of the relevant part of the drawing.

- Canonical rules: [Modeling rules knowledge base](docs/모델링규칙_지식베이스_v0.md)
- Canonical architecture: [Architecture and MCP configuration](docs/아키텍처_MCP구성_v0.md)
- M0 design document: [Repository bootstrap](docs/superpowers/specs/2026-08-27-m0-repo-bootstrap-design.md)

## Structure

| Path | Contents |
|---|---|
| `worker/` | Python pipeline (`m3d` CLI): drawing reading · modeling · verification |
| `web/` | React + Vite front end |
| `contracts/` | DB types shared by web and worker (a plain file directory with no build tooling) |
| `supabase/migrations/` | Canonical schema |
| `data/manifests/` | SHA256 manifests of the samples (committed) |
| `data/fixtures/` | Copies of the reference answers and the catalog (committed) |
| `data/samples/` | Copies of the original drawings, 413 MB (**gitignored**) |
| `data/derived/` | Conversion outputs — page PNGs · sheet_text · reports (**gitignored**) |

## Getting started

1. Copy `.env.example` to `.env` and fill in the values (design document §12).
2. Create the virtual environment and install:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

3. Collect the samples and apply the database schema:

```powershell
.\worker\.venv\Scripts\m3d.exe samples collect
.\worker\.venv\Scripts\m3d.exe db apply
.\worker\.venv\Scripts\m3d.exe seed ab1-p4p5
.\worker\.venv\Scripts\m3d.exe convert ab1-p4p5
.\worker\.venv\Scripts\m3d.exe catalog ab1-p4p5
```

The next two commands incur Anthropic API costs (design document §2-1 · §8 — drawing reading and review):

```powershell
.\worker\.venv\Scripts\m3d.exe read ab1-p4p5
.\worker\.venv\Scripts\m3d.exe review ab1-p4p5
```

Crop generation does not call the LLM — it only cuts PNGs at the ambiguity coordinates already stored in the
database, so it costs nothing:

```powershell
.\worker\.venv\Scripts\m3d.exe crops ab1-p4p5
```

4. Web:

```powershell
npm --prefix web ci
npm --prefix web run dev
```

## Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-m0.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify-m2a.ps1
```

`verify-m2a.ps1` runs only with `--cache-only`, so it makes no real LLM calls (a cost-free, idempotent check).
Without the local cache (`data/derived/ab1-p4p5/llm-cache`, gitignored) it ends in failure — that is expected.

`make` is not available in this environment. The `m3d` CLI doubles as the task runner.

## Cautions

- The reference originals under `SAMPLE_SOURCE_DIR` · `REFERENCE_MODELS_DIR` are **read-only**.
- `SUPABASE_SERVICE_KEY` · `SUPABASE_DB_URL` · `ANTHROPIC_API_KEY` · `ANTHROPIC_WORKSPACE_ID` are for the worker
  only — never put them in the web bundle or commit them. See `.env.example` for the list of values.
- `m3d read` · `m3d review` require a `.env` in which both values (`ANTHROPIC_API_KEY` · `ANTHROPIC_WORKSPACE_ID`)
  are filled in.
- Do not claim completion without verification. Report a failure as a failure, together with its output.

## Question cards (M2b)

After the drawings have been read, the ambiguities are answered in the web app, producing a canonical set of
dimensions that includes the decisions. None of the following incurs **Anthropic API costs**.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe publish ab1-p4p5 # crop PNGs → private Storage bucket "crops" (requires SUPABASE_URL · SUPABASE_SERVICE_KEY)
.\worker\.venv\Scripts\m3d.exe ssot ab1-p4p5 # data/derived/ab1-p4p5/ssot/ — versioned measurement summary (.md) + ssot.json (the version increases only when the content changes)
cd web; npm run dev # http://localhost:5173 — log in with an account created in the Supabase dashboard (Authentication → Users)
```

Cards: number keys `1`–`4` select an option, `0` means "don't know" (the recommended option is adopted
provisionally), `Enter` decides, `←`/`→` move between cards. Decisions accumulate as history in `decisions`, and
`ambiguities.status` changes to decided or provisional. Re-reading (`read`/`review`) preserves ambiguities that
already have a decision.

## 3D models (M3)

The SSOT (plus the decisions) is carried into a `ModelSpec`; a deterministic builder produces precise P4–P5 models
(GLB), which go through triple verification (self-check → independent re-measurement → rendering) and are then
compared with the reference answers (measure v2 · GLB). These commands **do not call the LLM** (no cost). Outputs
go to `data/derived/<dataset>/model/` (gitignored).

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe modelspec ab1-p4p5 # ssot.json → modelspec.json (per-field provenance statistics: ssot/decision/default/derived)
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5 --pilot # pilot: main body and diaphragms only → model/pilot/{sections/,AB1_P4P5.glb,selfcheck*.json,build.json} (approval gate)
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5 # all members → model/{sections/P4P5/<group>.glb ×10, AB1_P4P5.glb (assembled), selfcheck.json, selfcheck_sections.json, build.json}
.\worker\.venv\Scripts\m3d.exe measure ab1-p4p5 # independent re-measurement (does not reference the builder; 5mm/0/0.5°) → measure.json (fail>0 → exit 1)
.\worker\.venv\Scripts\m3d.exe render ab1-p4p5 # 4 true-scale orthographic views → renders/{side_context,front_section,bottom_iso,interior_cells}.png
.\worker\.venv\Scripts\m3d.exe compare-model ab1-p4p5 # compare with the reference measure v2 · GLB → compare.json (REFERENCE_MODELS_DIR when --ref is omitted)
.\worker\.venv\Scripts\m3d.exe publish-model ab1-p4p5 # sections · assembled model · renders · verification JSON → private bucket "models" + builds/build_sections (skipped when unchanged; --force, --pilot)
```

When the `ModelSpec` schema changes, regenerate `modelspec.json` — `build` warns when it finds fields that are
missing from the saved file. Acceptance criteria: `data/derived/ab1-p4p5/model/acceptance-m3.md` (design document
§1 ①–⑥).

## 3D review (M4)

The model is produced as 10 section GLBs (segments/member groups) plus an assembled model and uploaded to the
private bucket `models`. In the web app each section is opened on its own and reviewed down to its interior, and
approvals and rejections are recorded. **No LLM calls** at any step.

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe build ab1-p4p5 # model/sections/P4P5/<group>.glb ×10 + AB1_P4P5.glb (assembled) + selfcheck_sections.json + build.json
.\worker\.venv\Scripts\m3d.exe render ab1-p4p5 # renders/*.png + renders/views.json (view contract)
.\worker\.venv\Scripts\m3d.exe publish-model ab1-p4p5 # Storage upload + builds/build_sections (skipped when unchanged · --force · --pilot)
cd web; npm run dev # http://localhost:5173/p/ab1-p4p5/model
```

Screen: on the left, the section tree (visibility check · isolate · status badge · build version); in the center,
the three.js canvas (4 presets · z/x section clipping · click a member → node name); on the right, the verification
panel (section self-check · re-measurement · summary of the reference comparison · renders · downloads ·
approval/rejection record). Approvals accumulate as history in `approvals`, and a trigger updates
`build_sections.status`/`builds.status`. Acceptance criteria: `data/derived/ab1-p4p5/model/acceptance-m4.md`.

## LLM modeling (M5)

Pressing "Build with LLM" for a section on the web review screen creates a job in the `jobs` queue. The worker on
my PC receives section-builder code from Sonnet 5, runs and scores it in a sandbox (comparison with the reference
answer + LEGO-style assembly re-measurement), and uploads the result as an agent build. **Incurs API charges** —
cumulative cap `MODEL_AGENT_BUDGET_USD` in `.env` (default 5).

```powershell
$env:PYTHONUTF8='1'
.\worker\.venv\Scripts\m3d.exe worker --once # process one job from the queue (without --once it runs as a daemon)
```

M5 scope: one section, the diaphragms (P4P5/DIA). Outputs: `data/derived/ab1-p4p5/model/agent/<job>/` (code ·
attempts · scores · prompts · crops). Acceptance: `model/acceptance-m5.md`.

### M6 — Diaphragms PASS: more information + self-rendering (2026-09-07)

M5's best attempt (b4) got the plates, openings, chain and re-measurement right and only the 3D placement of the
stiffeners wrong. M6 supplied information the LLM did not have and attached meaning to the numbers (design document
`docs/superpowers/specs/2026-09-07-m6-diaphragm-pass-design.md`, acceptance report
`data/derived/ab1-p4p5/model/acceptance-m6.md`).

- **Meaning of spec fields**: the `description` of the diaphragm and bearing fields in `ModelSpec` goes into the
  `doc` of the prompt excerpt — the axis along which each tuple component extends (`[x]·[y]·[z]`), the one-sided
  attachment convention, placement outside openings, and the definition of the inner face of the web.
- **KB §5 stiffener conventions**, two lines (thickness runs in the plane of the plate, projection along the plate
  normal / support-diaphragm stiffeners only on the span-side face, opening stiffeners only on the +z face) —
  automatically reflected in the system prompt through `kb_excerpt`.
- **Scoring feedback**: the definition "node bbox = full extent of plate + stiffeners", per-axis delta sentences
  ("the reference extends 90 mm further toward +z"), node role labels (support/ordinary diaphragm), and hints on
  keeping plates, chains, and projection ≠ thickness.
- **Self-rendering**: after a scoring failure, three images made only from the agent's section GLB (DIA01 front iso
  · side chain line · DIA13 iso) are attached to the prompt for the next attempt
  (`model/agent/<job>/agent/critique<n>/`). The reference renders are not provided.
- **Budget input**: web modal "Budget cap ($)" (default 5, 0.5–50) → `jobs.budget_usd` = the cumulative cap per
  stage. A job's `cost_usd` includes retry calls. The bbox check allows 0.1 mm for float32 rounding.

Demonstration (4 jobs · 14 attempts · 17 calls · $1.78, cap $8): maximum bbox deviation 326 mm (M5) → **8 mm**
(job 1) → 90 mm (job 2, which read the projection of the opening stiffeners as thickness) → **5.001 mm** (job 3,
0 fails on every check, triangle count identical to the reference) → **job 4, attempt 2 PASS** (b9, bbox 5.001 mm,
0 check fails). Jobs 1–3 were FAIL under the rule in force when they ran (≤ 5.000 mm). After confirming that job 3's
5.001 mm is exactly the float32 rounding of 5 mm (INS), a 0.1 mm allowance was added to the check (job 3 passes an
offline re-score, `model/agent/rescore/`), and then, by the user's decision, job 4 was run and its PASS was
confirmed on screen and in the database. b8 remains FAIL under the rule in force when it ran.

### M7 — Spreading to 8 sections (2026-09-07)

The infrastructure was generalized so that the LLM can build the 8 sections other than the diaphragms (SP04 · HST ·
SLAB · BRG · FRM · RIB · CS · WG) (design document `docs/superpowers/specs/2026-09-07-m7-section-spread-design.md`,
acceptance report `data/derived/ab1-p4p5/model/acceptance-m7.md`).

- **One table of section metadata**, `agent/sections_meta.py`: regular expressions for reading evidence ·
  representative nodes · role labels · spec excerpt keys · section conventions (notes), all in one place. A new
  member group becomes a target with a single line here.
- **Extended ctx**, `SectionContext`: the full profile of the main body, including the top surface of the steel
  deck plate · crown · underside of the bottom plate · plate thicknesses · 4 colors · `zone_loft`. The main body
  (BOX) is not a spreading target, because the ctx is its geometry.
- **Descriptions for every spec field**: every field of the 10 sub-models of `ModelSpec` states its axis, units and
  placement rules. Values that the reference builder does not use for geometry are marked as such.
- **Node-name contract**: each section's contract carries the full set of reference node names (scoring requires the
  node sets to match).
- **Three self-render views**: front and side of the representative member + **an iso view of the whole section**.
  Errors in count, spacing and left/right placement show up only in the whole-section view.
- **Batch queue**: select several sections → "LLM modeling for N selected" → `m3d worker --poll --drain` processes
  them in order.
- **Full assembly**: `m3d agent-assemble` gathers each section's passing agent output, creates the assembled build,
  verifies it and uploads it.

Usage: in the web app at `/p/<slug>/model`, choose the sections, set a budget and create the jobs, then run
`m3d worker --poll 2 --drain`; when it finishes, run `m3d agent-assemble`.

### M8 — Acceptance rule without reference answers (2026-09-07)

Up to M7, acceptance depended on a bbox comparison with the output of the deterministic builder. A new bridge has no
such reference answer. M8 changed the check to three layers: **geometric soundness → spec-derived re-measurement →
human approval** (design document `docs/superpowers/specs/2026-09-07-m8-reference-free-rule-design.md`, acceptance
report `data/derived/ab1-p4p5/model/acceptance-m8.md`).

- **Geometric soundness**, `model/sanity.py`: parts outside the envelope · floating members · duplicate
  placements. Catches major accidents without interpreting the spec.
- **Stronger re-measurement**: re-measurement rows are tagged by section, and the number of items was increased from
  49 to 95. Splice plates and horizontal stiffeners, which previously had 0 items, are now covered, and members that
  are long in z are measured with cross-section slices instead of a bbox.
- **Acceptance rule**: `soundness fail 0 ∧ section self-check fail 0 ∧ assembled self-check fail 0 ∧ re-measurement
  fail 0 for that section`. The comparison with a reference answer remains only as reference information
  (`score.reference`). Calling with `ref_dir=None` checks without a reference answer.
- **Regression check**, `m3d verify-rule`: runs the new rule over the agent outputs that already exist and produces
  a confusion table of (deviation band × pass). It costs nothing, so it is rerun whenever the rule changes.

Result: across 32 existing outputs, **0 false passes · 0 false fails** (all 21 with a deviation of ≥100 mm fail,
all 4 with ≤5 mm pass). Errors that M6 and M7 could catch only by comparison with a reference answer — the
cross-beam anchorage (1.7 m), the diaphragm stiffeners (326 mm) and the splice plates (157 mm) — are now caught
without one. Demonstration: the two sections that previously had 0 re-measurement items, horizontal stiffeners and
splice plates, passed on the first attempt under the new rule ($0.28).
