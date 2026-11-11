# Reference assets

This folder is for redistributable example media accompanying Comfy Recipe workflows.
Personal source media and cached previews are not examples.

## Bundled assets

| Path | Role | Size | SHA-256 | Source / licence |
|---|---|---|---|---|
| `images/character_sheet.png` | Layout sheet for a **person** (character turnaround: full-body front/side/back, three-quarter portrait, four bare-head expression close-ups, detail close-ups of shirt, watch and rings, the cap on its own, and the sneaker; no tattoo). `comfy_onboarding action=reference_sheet kind=person` copies it to `input/` as `image_2` of `qwen-image-2-1-i2i` (tutorial steps 2-3). | 1376 x 768 PNG | `f0e4771aad1e57ab562f033b92cfd703868a21e50acfbc09885b0a362329b806` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; AI-generated. |
| `images/pet_sheet.png` | Layout sheet for a **pet**: Miskinou, an orange mackerel tabby cat (11 views: face, profiles, back, sitting, standing, walking); formerly `character-sheets/miskinou_sheet.png`. `kind=pet`; also the character reference `ref_image_2` / `<Picture 3>` (node 165) of `minimax-h3-r2v-mix`. | 1376 x 768 PNG | `4e8c7f988b32e93eeb6d49d3b09d0c4072d919e4e793138bba0fc3ccae70865c` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; AI-generated. |
| `images/object_sheet.png` | Layout sheet for an **object** (closed/open rows, 3/4, front, left, right, rear views). `kind=object`. | 1376 x 768 PNG | `bd5a6625fdcadd4d872a51ca59cd99aa00360c338cafe035b8e08f49bfc58dbc` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; AI-generated. |
| `images/outdoor_sheet.png` | Layout sheet for an **outdoor location** (four equal panels with even 4 px borders: street level, high angle, night, building detail); formerly `location_sheet.png`. `kind=location`. | 1376 x 768 PNG | `65624be9b83e0463bc2ff1ac65c2e03ae3675fefc583e95400abbd8c17e75b6e` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; AI-generated. |
| `images/indoor_sheet.png` | Layout sheet for an **indoor room**. `kind=indoor`. | 1679 x 937 PNG | `7a2b8d3c9de9143f635395312b9bd75c3db7713c87d2bb5c181f390b385a2756` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; AI-generated. |
| `images/placeholder.png` | Plain white 544 x 960 (9:16) placeholder. Keeps an optional Load Image valid when its input is switched off (ComfyUI validates every connected loader), e.g. node 151 (last-frame guide, `<Picture 2>`) of `minimax-h3-r2v-mix` when Use Last Frame is off. | 544 x 960 PNG | `3c6966dadfe102027b2f40832e58f29e0a42506a20c02e3b56fbc840de87a63e` | Supplied by the plugin author (Julien) for redistribution with Comfy Recipe; plain white image, no third-party content. |

- `images/`: reference/starter images and layout sheets (PNG, JPEG or WebP). The layout sheets are only a
  grid/view template: a new sheet takes their layout, never their subject.
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
The first-image text-to-image tutorial (step 1) requires no input asset.
