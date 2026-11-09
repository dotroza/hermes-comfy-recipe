# Reference assets

This folder is for redistributable example media accompanying Comfy Recipe workflows.
No images, character sheets or videos are bundled yet. Personal source media and cached previews are not examples.

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
