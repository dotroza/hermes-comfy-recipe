# Reference assets

This folder is for redistributable example media accompanying Comfy Recipe workflows.
Personal source media and cached previews are not examples.

## Bundled assets

| Path | Role | Size | SHA-256 | Source / licence |
|---|---|---|---|---|
| `character-sheets/miskinou_sheet.png` | Character sheet of Miskinou, an orange mackerel tabby cat (11 views: face, profiles, back, sitting, standing, walking). Character reference for MiniMax H3 character swaps: `ref_image_2` / `<Picture 3>` (node 162) of `minimax-h3-r2v-mix`. | 1376 x 768 PNG | `4e8c7f988b32e93eeb6d49d3b09d0c4072d919e4e793138bba0fc3ccae70865c` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; AI-generated sheet of his own cat. |
| `images/placeholder.png` | Plain white 544 x 960 (9:16) placeholder. Keeps an optional Load Image valid when its input is switched off (ComfyUI validates every connected loader), e.g. node 151 (last-frame guide, `<Picture 2>`) of `minimax-h3-r2v-mix` when Use Last Frame is off. | 544 x 960 PNG | `3c6966dadfe102027b2f40832e58f29e0a42506a20c02e3b56fbc840de87a63e` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; plain white image, no third-party content. |

- `images/`: reference/starter images (PNG, JPEG or WebP).
- `character-sheets/`: consistent multi-view/identity sheets (PNG, JPEG or WebP).
- `motion-videos/`: driving-motion clips (MP4 recommended; use broadly supported codecs).

Use descriptive portable filenames, such as `explorer-turnaround.png` or `walk-cycle.mp4`.
Keep examples short and reasonably sized. Document dimensions, duration/frame rate for video and the intended role.

## Before adding an asset

Verify redistribution permission. Record author, source URL, licence, attribution, modifications and any consent
requirements for identifiable people. A public download URL alone is not redistribution permission.
Do not commit private portraits, copyrighted music/video clips, credentials or model weights.

Future asset metadata must identify a stable workflow id, input role, package-relative path, SHA-256 hash,
licence and attribution. Paths must stay within `assets/`: no absolute paths, drive letters or `..` traversal.
An author-supplied manifest will be validated when real media is added; no empty media-install engine is supplied now.

## Using approved examples later

Copy only the selected example into the chosen ComfyUI `input/` folder. Reuse identical content where possible;
never overwrite an unrelated user file. Read back/verify the destination. Select the filename visibly using the
workflow's Load Image or Load Video control. Do not rewrite media widget values through JSON.
The first-image text-to-image tutorial requires no input asset.
