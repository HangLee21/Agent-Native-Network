"""Local subprocess adapter: no silent substitution for model failures."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

from .runtime import encode, sha, write_json

TOOL_PROMPT = (
    "This is a synthetic compatibility check, not a real scene. "
    "You are an independent node. Use only the following private/local and fully arrived evidence. "
    "Return exactly one JSON object, no Markdown or explanation. Allowed tools: "
    '{"tool":"request","peer":"a declared peer","query":"text","deadline_s":5}; '
    '{"tool":"respond","request_id":"an arrived request ID","body":"text","evidence_refs":["visible ID"]}; '
    '{"tool":"consume","message_id":"an arrived evidence message ID"}; '
    '{"tool":"finish","answer":"brief description of your image","evidence_refs":["visible local ID"]}. '
    "Do not invent unseen evidence or messages. Context follows:\n"
)


class SmolVLMBackend:
    label = "smolvlm_local_model"

    def __init__(self, python, model_dir, revision, output_dir, worker_path,
                 *, max_new_tokens=128, per_call_s=180, total_s=720, environment=None):
        self.python, self.model_dir, self.revision = str(python), str(model_dir), revision
        self.out = Path(output_dir)
        self.worker_path = str(worker_path)
        self.max_new_tokens, self.per_call_s, self.total_s = max_new_tokens, per_call_s, total_s
        self.environment = environment
        self.attempts = 0
        self.forward_started = 0
        self.accumulated_worker_s = 0.0

    def decide(self, node_id, context):
        if self.attempts >= 4 or self.accumulated_worker_s >= self.total_s:
            raise RuntimeError("A0 invocation/total wall budget exhausted")
        self.attempts += 1
        case = self.out / f"call-{self.attempts:02d}"
        case.mkdir(exist_ok=False)
        images = [record for record in context["private_and_arrived_evidence"].values()
                  if record.get("kind") == "private_image"]
        spec = dict(node_id=node_id, context_sha256=sha(encode(context)),
                    source_revision=self.revision, model_dir=self.model_dir,
                    images=images, prompt=TOOL_PROMPT + encode(context).decode("utf-8"),
                    max_new_tokens=self.max_new_tokens, max_generation_s=min(170, self.per_call_s))
        write_json(case / "spec.json", spec)
        command = [self.python, "-B", self.worker_path, "--spec", str(case / "spec.json"),
                   "--result", str(case / "result.json")]
        started = time.monotonic()
        timed_out = False
        with (case / "stdout.txt").open("w", encoding="utf-8") as stream:
            try:
                process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                         env=self.environment, timeout=min(self.per_call_s, self.total_s - self.accumulated_worker_s))
                code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out, code = True, -999
        elapsed = time.monotonic() - started
        self.accumulated_worker_s += elapsed
        result_path = case / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        self.forward_started += int(result.get("actual_forward_started", False))
        write_json(case / "process.json", dict(command=command, exit_code=code, timed_out=timed_out, wall_seconds=elapsed))
        if code != 0 or result.get("status") != "generated":
            raise RuntimeError(f"model call failed: {case.name}; exit={code}; {result.get('error', result.get('status', 'no result'))}")
        if result["output_tokens"] > self.max_new_tokens:
            raise RuntimeError("backend exceeded output token cap")
        return result["raw_output"]
