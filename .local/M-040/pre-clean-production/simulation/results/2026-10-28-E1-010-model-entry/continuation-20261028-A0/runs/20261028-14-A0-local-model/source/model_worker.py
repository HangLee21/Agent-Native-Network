"""One strictly local SmolVLM forward. Run only through the gated A0 controller.

No downloading, remote Python, fixture answers, or network-client calls here.
The controller enforces the subprocess wall limit including load time.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True)
    p.add_argument("--result", required=True)
    args = p.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    began = time.monotonic()
    result = dict(backend="smolvlm_local_model", actual_forward_started=False,
                  source_revision=spec["source_revision"], status="loading",
                  node_id=spec["node_id"], context_sha256=spec["context_sha256"],
                  max_new_tokens=spec["max_new_tokens"], python=sys.executable)

    def save():
        result["wall_seconds"] = time.monotonic() - began
        Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    try:
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                          USE_TF="0", USE_FLAX="0")
        import torch
        from PIL import Image
        from transformers import AutoModelForImageTextToText, AutoProcessor
        result["versions"] = {name: importlib.metadata.version(name) for name in
                              ("torch", "transformers", "Pillow", "tokenizers", "huggingface-hub", "safetensors")}
        torch.set_num_threads(1)
        torch.manual_seed(0)
        if not torch.cuda.is_available():
            raise RuntimeError("A0 requires available CUDA; no silent CPU fallback")
        free_gpu, total_gpu = torch.cuda.mem_get_info()
        result.update(free_gpu_before_load_bytes=free_gpu, total_gpu_bytes=total_gpu)
        if free_gpu < 2684354560:
            raise RuntimeError("less than 2.5GiB free GPU memory before loading")
        device = "cuda:0"
        dtype = torch.float16
        processor = AutoProcessor.from_pretrained(spec["model_dir"], local_files_only=True, trust_remote_code=False)
        # Prevent default multi-tile upsampling of a 64px compatibility fixture.
        processor.image_processor.do_resize = False
        model = AutoModelForImageTextToText.from_pretrained(
            spec["model_dir"], local_files_only=True, trust_remote_code=False,
            torch_dtype=dtype, low_cpu_mem_usage=True, attn_implementation="eager")
        model.to(device)
        model.eval()
        images = []
        for record in spec["images"]:
            data = Path(record["path"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("private input image changed")
            with Image.open(record["path"]) as image:
                images.append(image.convert("RGB"))
        messages = [{"role": "user", "content": [*({"type": "image"} for _ in images),
                                                        {"type": "text", "text": spec["prompt"]}]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=text, images=images, return_tensors="pt")
        inputs = {key: value.to(device=device, dtype=dtype) if value.is_floating_point() else value.to(device)
                  for key, value in inputs.items()}
        result.update(status="prepared", input_tokens=int(inputs["input_ids"].shape[-1]),
                      input_tensor_shapes={key: list(value.shape) for key, value in inputs.items()},
                      chat_template_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                      image_processor_do_resize=False, device=device, dtype=str(dtype),
                      load_and_preprocess_seconds=time.monotonic() - began)
        save()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        generation_start = time.monotonic()
        result.update(status="generating", actual_forward_started=True)
        save()
        with torch.inference_mode():
            generated = model.generate(**inputs, do_sample=False,
                                       max_new_tokens=spec["max_new_tokens"], max_time=spec["max_generation_s"])
        torch.cuda.synchronize()
        new_tokens = generated[:, inputs["input_ids"].shape[-1]:]
        raw = processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
        result.update(status="generated", raw_output=raw, output_tokens=int(new_tokens.shape[-1]),
                      output_utf8_bytes=len(raw.encode("utf-8")), generation_seconds=time.monotonic() - generation_start,
                      peak_allocated_gpu_bytes=torch.cuda.max_memory_allocated(),
                      peak_reserved_gpu_bytes=torch.cuda.max_memory_reserved())
        save()
        return 0
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        save()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
