from __future__ import annotations

import json
import os
from typing import Any

from .prompt import SYSTEM_PROMPT, build_user_prompt
from .schema import AnalysisResult
from .text_utils import validate_article


def local_model_dependencies_available() -> bool:
    try:
        import accelerate  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _extract_json_object(raw: str) -> dict[str, Any]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回 JSON 对象")
    return json.loads(raw[start : end + 1])


class LocalTransformersAnalyzer:
    """Optional local backend used by the Streamlit model mode.

    The default model is Qwen3-8B. For a 16 GB GPU, set JP_ANALYZER_4BIT=1.
    The model loads lazily so demo mode does not download any weights.
    """

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv(
            "JP_ANALYZER_MODEL", "Qwen/Qwen3-8B"
        )
        self.tokenizer = None
        self.model = None

    def _load(self) -> None:
        if self.model is not None and self.tokenizer is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "未安装模型依赖。请先执行 pip install -r requirements-model.txt"
            ) from exc

        kwargs: dict[str, Any] = {
            "device_map": "auto",
            "low_cpu_mem_usage": True,
        }
        if torch.cuda.is_available():
            kwargs["torch_dtype"] = torch.float16
        if os.getenv("JP_ANALYZER_4BIT", "0") == "1":
            try:
                from transformers import BitsAndBytesConfig

                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                )
            except Exception as exc:
                raise RuntimeError("4-bit 量化依赖不可用，请检查 bitsandbytes") from exc

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            **kwargs,
        )

    def analyze(
        self,
        text: str,
        *,
        level: str = "N3",
        focus: list[str] | None = None,
    ) -> AnalysisResult:
        error = validate_article(text)
        if error:
            raise ValueError(error)
        self._load()
        assert self.tokenizer is not None
        assert self.model is not None

        focus = focus or ["全部"]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(text, level, focus) + "\n/no_think",
            },
        ]
        if getattr(self.tokenizer, "chat_template", None):
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            prompt = SYSTEM_PROMPT + "\n\n" + build_user_prompt(text, level, focus)

        inputs = self.tokenizer(prompt, return_tensors="pt")
        model_device = next(self.model.parameters()).device
        inputs = {key: value.to(model_device) for key, value in inputs.items()}
        output = self.model.generate(
            **inputs,
            max_new_tokens=1500,
            do_sample=False,
            repetition_penalty=1.05,
        )
        generated = output[0, inputs["input_ids"].shape[-1] :]
        raw = self.tokenizer.decode(generated, skip_special_tokens=True)
        payload = _extract_json_object(raw)
        result = AnalysisResult.from_dict(payload)
        missing_readings = [
            point.term
            for point in result.points
            if point.kind == "vocabulary" and not point.reading.strip()
        ]
        if missing_readings:
            result.warnings.append(
                "部分词汇缺少平假名读音：" + "、".join(missing_readings)
            )
        raw_points = payload.get("points", [])
        missing_frequency = [
            str(item.get("term", "未命名知识点"))
            for item in raw_points
            if not isinstance(item.get("exam_frequency"), int)
        ]
        if missing_frequency:
            result.warnings.append(
                "部分知识点没有有效考频，暂按三星显示："
                + "、".join(missing_frequency)
            )
        result.mode = f"model:{self.model_id}"
        return result

