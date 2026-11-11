# Catalog submission

Authoritative rules: <https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission>

## Release checklist (owner actions)

- [ ] Review the local diff and the security disclosures in both READMEs. Confirm redistribution rights for all artwork,
  including the project icon. Do not treat an AI-generated label or a public URL as permission.
- [ ] Run `python scripts/run_tests.py` and `python -m compileall -q plugin tests scripts`.
- [ ] Run `hermes plugins validate ./plugin --install-deps --json`: every check passes and warnings are empty.
  No Python dependencies are declared in the plugin; this does not test the separate ComfyUI environment resolver.
- [ ] Fully quit/reopen Hermes to activate Python changes; use Reload desktop plugins for JavaScript changes.
  Smoke-test sidebar kickoff, agent-driven pane opening, session naming, progress cards and onboarding routing.
  Repository tests are not proof that an already-running Hermes loaded the changes.
- [ ] Keep `version` and `requires_hermes` truthful. Current manifest: `"0.4.0"`, `">=0.23.1"`.
  Windows 11 / Hermes 0.23.1 is the local verification target; do not claim macOS/Linux execution or older Hermes compatibility.
- [ ] Commit and push the reviewed plugin changes **yourself**. No catalog entry may pin uncommitted work.
- [ ] From a clean checkout, run `python scripts/prepare_catalog.py` to print the final catalog YAML.
  It refuses a dirty tree, reads the manifest at HEAD, checks the catalog README/screenshots exist at that SHA,
  quotes the version, matches capabilities and compatibility floor, and pins screenshots to that exact commit.
  It does not commit, push, open a PR or verify that HEAD is publicly reachable.
- [ ] Confirm the full SHA is publicly fetchable, clone that exact SHA into a disposable directory, and rerun the
  validator there. This is the tree the catalog reviewer and CI will see.
- [ ] Add the generated output as **one file**, `plugin-catalog/comfy-recipe.yaml`, in a PR to
  `NousResearch/hermes-agent`. Do not copy plugin source or these preparation scripts into that PR.
- [ ] Paste/adapt the PR body below, attach the existing screenshots, wait for catalog CI and maintainer review.

The generated entry uses `subdir: "plugin"`, so the catalog site reads **plugin/README.md**, not the root README.
That file deliberately includes requirements, disclosures and repo-relative screenshot/document links.
No banner image is declared: the existing project icon is square, not the suggested 2:1 card artwork.

## PR description draft

### Add Comfy Recipe (community)

I am the owner/maintainer of <https://github.com/dotroza/hermes-comfy-recipe>.

Comfy Recipe brings visible ComfyUI sessions into Hermes Desktop beside the chat. It offers consent-based managed
installation or existing-instance discovery, workflow/model readiness checks, a four-step tutorial, live progress
cards, optional headless workflow runs with timings and ffmpeg media preparation.

**Public Hermes surfaces:** nine registered tools, the `pre_llm_call` hook, `/comfy`, twelve registered skills;
Desktop SDK sidebar/route/palette contributions, tool-media renderers and status-bar contributions. Public
`hermes_constants.get_hermes_home` and `hermes_state.SessionDB` are used for profile-scoped cosmetic session naming.
The agent opens the controllable preview through `desktop_preview`; no private renderer bridge, core mutation,
self-updater, credential-store access or monkey patching.

**Rule 13 disclosures:**

- Network: localhost/configured ComfyUI API, official GitHub ComfyUI/uv releases, Python distributions via uv,
  package/PyTorch indexes, workflow-declared or explicit model links (bundled Hugging Face/CDN), and Manager/node
  registries/upstreams. Cloud runs send prompts/media to the selected provider after explicit approval.
- Local access: process command lines, Desktop/StabilityMatrix installation settings, selected ComfyUI workflows,
  models/model-sharing configuration, selected media, generated files beside inputs, optional copies into ComfyUI,
  managed workflow/startup/settings files and the active profile's session-title metadata.
- Subprocesses: uv/Python/git/package installation and hardware/process utilities, external comfy-cli, ffmpeg/ffprobe.
  Installer/download/node workers, ComfyUI and watchdog may run beyond a turn. By default only the managed ComfyUI
  is stopped when its Hermes owners close; users can opt to keep it running.
- Downloaded code: installed uv is reused; fallback bootstrap is official uv 0.13.7 with source-committed archive
  SHA-256 pins and executable-only extraction. uv installs Python/dependencies separately. ComfyUI follows a
  release tag (default branch on lookup failure). Approved custom nodes run as user code; not sandboxed.
- Stored data: local instance/setup/tutorial/download state, logs, prompts/overrides in headless run records,
  timings/contact sheets and potential prompt/workflow metadata in ComfyUI outputs. Reset is not data deletion.
- Credentials: no declared secrets/OAuth clients, credential-store access or token handling in this plugin;
  ComfyUI's official API-node UI owns cloud sign-in. Paid runs require separate explicit consent.
- No added telemetry/usage reporting, automatic approvals or plugin self-updating. Upstream software has its own policies.

**Verification:** paste the actual release-checkout validator output and test summary here before opening the PR.
Do not claim catalog CI, fresh managed installation or every workflow/provider has passed before testing them.

**Screenshots:** generation, image editing and reference-sheet creation are in `docs/screenshots/` and linked by
exact SHA in the generated entry.

**Known limitations:** Windows 11 verified; other OS paths not live-verified. Models/custom nodes/hardware are
separate requirements. Cloud workflows require ComfyUI sign-in/credits. Cosmetic session-title failures retain
Hermes defaults; public-tool pane opening can take an extra model round trip.
