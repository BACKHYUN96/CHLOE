#!/usr/bin/env python3
"""Pinned upstream converter with F32 code-predictor FFN-down matrices for numeric stability.

In ggml's F16 matmul path the activation is converted to F16 for a dot product.
The 0.6B CustomVoice code predictor can exceed that range. F32 down projections
avoid the overflow without quantizing weights or changing generation settings.
"""
import argparse
import importlib.util
from pathlib import Path
import gguf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    upstream = Path(__file__).resolve().parents[1] / "external/qwen3-tts.cpp/scripts/convert_tts_to_gguf.py"
    spec = importlib.util.spec_from_file_location("chloe_upstream_converter", upstream)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class StableConverter(module.Qwen3TTSConverter):
        def _convert_dtype(self, tensor, tensor_name=""):
            if tensor_name.startswith("code_pred.") and ".ffn_down.weight" in tensor_name:
                return tensor.float().numpy(), gguf.GGMLQuantizationType.F32
            return super()._convert_dtype(tensor, tensor_name)

    StableConverter(input_dir=args.input, output_path=args.output, output_type="f16").convert()


if __name__ == "__main__":
    main()
