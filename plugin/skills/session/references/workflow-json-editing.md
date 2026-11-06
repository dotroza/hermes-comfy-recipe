# Editing ComfyUI UI-format workflow JSON (layout-preserving)

Keep the user's organised graph (groups, notes, subgraphs, positions). Never convert to API format to edit.

## Ground rules
- Back up first (`<name>.bak-<purpose>.json`) or write a sibling copy. A sibling copy needs a new top-level `id` (uuid4)
  so the frontend opens it as a separate tab.
- Load, modify in Python, `json.dump(..., ensure_ascii=False, indent=2)`.
- After every edit verify: (a) no link references a missing node (subgraph io nodes are -10 input / -20 output),
  (b) every target input's `link` equals the link id pointing at it, (c) a flattened diff against the source lists
  only the intended changes — report them.
- Bump counters: top `last_node_id` / `last_link_id`, subgraph `state.lastNodeId` / `lastLinkId`.
- Place new nodes in free space (check `pos`/`size` bounding boxes).
- The open tab does not see disk edits: close + reopen the preview pane, then reopen the workflow.

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
