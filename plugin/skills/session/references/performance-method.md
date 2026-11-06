# Finding where the time goes in a ComfyUI run

Base advice on measured runs (`comfy_result`, `comfy_workflows action=timings`), not guesses.

## 1. Per-stage breakdown
`comfy_result` gives it directly. From the raw log (`<root>/user/comfyui*.log`, or `GET <url>/internal/logs`), use
per-run markers: `got prompt`, `Requested to load`, `loaded completely/partially`, `patches attached`,
`Generating tokens`, `N/N [mm:ss, s/it]`, `Prompt executed in`. The gap between model load and the first step is
loading/patching overhead.

## 2. Usual causes, cheapest fix first
1. **Prompt enhancer / LLM node running to its token cap** (TextGenerate-style nodes with "thinking" on and a huge
   `max_length`): turn thinking off, cap at a few hundred tokens, or let the agent write the prompt instead.
2. **Too many reference images**: each connected image adds tokens to every step (cost grows faster than linearly).
   Connect only the ones needed, keep them around 1 MP.
3. **Models that don't fit together in VRAM** (diffusion model + text encoder + enhancer): compare file sizes on disk
   with free VRAM from `comfy_instances`. Lighter quantised encoders, or a dedicated GPU (`--cuda-device N`), help.
4. **LoRA re-patching every run** (`patches attached` followed by a long pause): with dynamic VRAM management the
   patched weights are rebuilt each run; `--highvram` or a model with the speed-up merged in avoids it.
5. **Sampler steps**: distilled "lightning"/"turbo" LoRAs or models trade a little quality for 4–8 steps at CFG 1
   (the negative prompt is ignored at CFG 1).
6. **Slow drift over consecutive video runs** (s/it rising): memory fragmentation — restart ComfyUI between batches
   (ask the user; never restart it yourself).

## 3. GPU checks
- High utilisation and power = real compute, not offloading.
- Prefer ComfyUI's per-device free VRAM (`/system_stats`) over `nvidia-smi`'s memory column on multi-GPU machines.
- `argv` in `/system_stats` shows launch options such as `--cuda-device`.

## 4. Before wiring a new LoRA
Read the safetensors header (JSON after the 8-byte length): key names, rank, dtype, block count; compare with the base
model. After the first run, search the log for `lora key not loaded`.
