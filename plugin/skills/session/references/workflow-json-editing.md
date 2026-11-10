# Editing ComfyUI UI-format workflow JSON (layout-preserving)

Keep the user's organised graph (groups, notes, subgraphs, positions). Never convert to API format to edit.

## Ground rules
- Edit the current workflow in place by default. Adding a Load Image node and wiring IMAGE to `image_2` is a routine
  edit of that graph, not a reason to open a different workflow.
- Duplicate only for substantial restructuring (many coordinated changes including group/subgraph internals), or when
  the user explicitly asks. Explain a substantial fork first. Only an intentional separate copy gets a new UUID.
- Prefer supported visible node/link controls. A disk wiring fallback requires explicit user approval, except the
  standing consent below for matching loaders to the user's media ("API-mode wiring"). Before using
  it, preserve the live unsaved graph state; the last saved JSON is not a substitute for the active dirty tab. If live
  state cannot be safely preserved with the available tools, stop and explain the limitation and ask how to proceed.
  Do not auto-save, discard edits, or duplicate a saved/bundled graph as a workaround.
- Create a backup (`<name>.bak-<purpose>.json`) before approved disk edits; it is recovery data, not a duplicate working tab.
  Retain the same workflow identity and path. Never change prompts, numbers, seeds or selected images through JSON.
- Load, modify in Python, `json.dump(..., ensure_ascii=False, indent=2)`.
- After every edit verify: (a) no link references a missing node (subgraph io nodes are -10 input / -20 output),
  (b) every target input's `link` equals the link id pointing at it, (c) a flattened diff against the source lists
  only the intended changes — report them.
- Bump counters: top `last_node_id` / `last_link_id`, subgraph `state.lastNodeId` / `lastLinkId`.
- Place new nodes in free space (check `pos`/`size` bounding boxes).
- The open tab does not automatically adopt disk edits. After the approved fallback, reopen the same workflow only
  with the user's agreement and after preserving unsaved state; verify the actual node and connection in the pane.
  Closing/reopening the pane alone is not proof that the new wiring replaced its cached graph.

## API-mode wiring (loaders to the user's media) — verified procedure
Standing user consent: when the request needs more/fewer Load Image / Load Video / Load Audio nodes than the graph has
connected, add/delete them and wire them through the file without asking again. Values are still set in the window.
1. Back up the current disk file to `<install>/.comfy-recipe/backups/<name>.disk-before-save.<ts>.json`.
2. Save the LIVE tab from the window: `Menu` -> hover `File` -> `Save` (title loses `*`). This is how the unsaved
   state is preserved; back up the saved file too (`<name>.live-saved.<ts>.json`).
3. Read the saved graph (it is the truth, not the bundled file): loaders, their `pos`/`size`, the target node's inputs.
4. Edit only nodes and links: remove the extra loader and its links (clear the target input's `link`), add the new
   loader where the removed one stood or in the loaders' column, append links, set target `link` and source `links`,
   bump `last_node_id` / `last_link_id`. Give the new node schema-default widget values only (`GET <url>/object_info/
   <type>` for outputs/inputs); VHS nodes take a dict `widgets_values`. Real file/number values are chosen visibly.
5. Close the clean tab (`close-workflow-button`), reopen it from the Workflows sidebar, verify each socket connected
   (`pane-recipe.md` §1b.1), then set media/prompt/numbers in the window and Run.
Example (MiniMax H3 r2v): `VHS_LoadVideo` outputs `IMAGE`(0) -> `ref_videos.ref_video_0`, `audio`(2) ->
`ref_video_audios.ref_video_audio_0`; LoadImage `IMAGE` -> `ref_images.ref_image_N`.

## Formats
- Top-level links: arrays `[id, origin_id, origin_slot, target_id, target_slot, type]`.
- Subgraph links (`definitions.subgraphs[i].links`): dicts `{id, origin_id, origin_slot, target_id, target_slot, type}`.
- Subgraph instance node: `inputs` order == subgraph `inputs` order; `widgets_values` maps 1:1 to inputs that carry a
  `widget`. User-renamed controls appear as `label`.

## Recipes
- **Read the wiring** (which LoadImage feeds a socket): the input's `link` is a link id; in the top-level links array
  `l[0]` is the link id and `l[1]` the source node id (common mistake: reading `l[0]` as the source). That node id is the
  `#<id>` badge in the pane. Unconnected nodes never run (ComfyUI only queues nodes reachable from an output).
- **Insert a node between two** (e.g. a LoRA loader after the model loader): retarget the existing link to the new
  node's slot 0, add a link new → old target, update both nodes' `links` / `link` fields.
- **Expose an inner widget on the subgraph node**: append a subgraph input `{id: uuid, name, type, linkIds:[L], pos}`,
  add link `{origin_id:-10, origin_slot:<new index>, target_id:<inner>, target_slot:<widget input index>}`, set the inner
  input's `link`, append the outer input `{name, type, widget:{name}, link:null}` and its value to `widgets_values`.
  Append at the end to avoid renumbering existing slots.
- **Connect a LoadImage to a subgraph image socket**: append a top-level link to `(subgraph_node, slot)`, set that outer
  input's `link`, add the id to the LoadImage output `links`.
- **"Missing required input: images" on a Save node**: feed it directly from the producing node's output.
