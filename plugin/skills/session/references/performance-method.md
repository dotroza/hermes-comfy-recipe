# Finding where the time goes in a ComfyUI run

Base advice on measured runs (`comfy_result`, `comfy_workflows action=timings`), not guesses.

## 1. Per-stage breakdown
`comfy_result` gives it directly. From the raw log (`<root>/user/comfyui*.log`, or `GET <url>/internal/logs`), use
per-run markers: `got prompt`, `Requested to load`, `prepared for dynamic VRAM loading. <N>MB Staged` (current builds;
older ones print `loaded completely/partially`), `patches attached`,
`Generating tokens`, `N/N [mm:ss, s/it]`, `Prompt executed in`. The gap between model load and the first step is
loading/patching overhead.

## 1b. A run that is still going
`comfy_result latest` returns only `status: running` until the job ends, and `timings` is empty for a workflow that
never finished. Read progress from `GET <url>/internal/logs/raw` (tqdm lines appear only when a step completes) and
the values actually running from `GET <url>/queue` -> `queue_running[0][2]` (node id -> class_type + inputs). Linked
widgets are invisible on the canvas: e.g. a graph can drive `Math Expression.a` from `Video Info` output 2 = the
reference clip's SOURCE duration, so the output length silently follows the reference. Compute frame counts from
there and compare against the last run that worked one variable at a time before naming a cause.

## 2. Usual causes, cheapest fix first
0. **The graph's own speed switches** - check them first. The bundled MiniMax H3 graphs pick steps through
   `If/Else Switch (Steps)` between `Int (Full)` (20) and `Int (Lightning LoRA)` (4) from
   `Boolean (Enable Lightning LoRA)`, saved OFF. Frames = `Float (Duration)` x 24, padded by a math node
   (3 s -> 73, 5 s -> 124, 6.4 s -> 158).
00. **Video length cliff** (output frames x megapixels, not steps, is the hard limit). Measured on a 24 GB RTX 3090,
   0.5 MP, Lightning ON: f2lf graph (w6a8 model) 73 frames ~49 s/step, 295 s total; 124-158 frames stayed on step 1
   for 5-15+ min and one finished at ~173 s/step (35 min). r2v graph (int8 model, 32B encoder, 1 ref video) 73 frames
   ~100 s/step, 681 s total. No OOM: Windows spills to system RAM (GPU 99 % but ~170 W of 350 W). Shrinking the
   reference video (60->24 fps, 1080p->544x960) did NOT help. Offer shorter output, lower megapixels or 3 s segments;
   never re-run a stalled length unchanged.
000. **Reference pictures** ride along every MiniMax step: mix graph at 0.5 MP, 73 frames, Lightning: 21-26 s/step
   with 1-2 pictures, 34-84 s/step with three (first frame + placeholder + sheet). Remove pictures the run does not need.
1. **Prompt enhancer / LLM node running to its token cap** (TextGenerate-style nodes with "thinking" on and a huge
   `max_length`): turn thinking off, cap at a few hundred tokens, or let the agent write the prompt instead.
2. **Too many reference images**: each connected image adds tokens to every step (cost grows faster than linearly).
   Connect only the ones needed, keep them around 1 MP.
3. **Models that don't fit together in VRAM** (diffusion model + text encoder + enhancer): compare file sizes on disk
   with free VRAM from `comfy_instances`. Lighter quantised encoders, or a dedicated GPU (`--cuda-device N`), help.
4. **LoRA re-patching every run** (`patches attached` followed by a long pause): with dynamic VRAM management the
   patched weights are rebuilt each run; `--highvram` or a model with the speed-up merged in avoids it. Measured:
   MiniMax H3 r2v + 4-step LoRA (208 patches) spent 281 s of 681 s outside sampling.
5. **Sampler steps**: distilled "lightning"/"turbo" LoRAs or models trade a little quality for 4–8 steps at CFG 1
   (the negative prompt is ignored at CFG 1).
6. **Slow drift over consecutive video runs** (s/it rising): memory fragmentation — restart ComfyUI between batches
   (ask the user; never restart it yourself).

## 3. GPU checks
- High utilisation and power = real compute, not offloading.
- Prefer ComfyUI's per-device free VRAM (`/system_stats`) over `nvidia-smi`'s memory column on multi-GPU machines.
- `argv` in `/system_stats` shows launch options such as `--cuda-device`.

## 3b. "Make it fit my VRAM"
Read `Staged` sizes and `Native ops / emulated ops` from the log, list the model's variants with the HF tree API
(`/api/models/<repo>/tree/main?recursive=true`), reuse byte-identical files already on disk (hard link), present ranked
options and download only after the user picks.

## 4. Before wiring a new LoRA
Read the safetensors header (JSON after the 8-byte length): key names, rank, dtype, block count; compare with the base
model. After the first run, search the log for `lora key not loaded`.
