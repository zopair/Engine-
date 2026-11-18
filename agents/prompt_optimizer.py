from __future__ import annotations

import importlib



def optimize_instructions(prompt: str) -> str:
    try:
        dspy = importlib.import_module("dspy")
    except ImportError:
        return prompt

    try:
        class StructuredAnswer(dspy.Signature):
            question = dspy.InputField(desc="The user question")
            instructions = dspy.OutputField(desc="Concise, unambiguous instructions for the language model")

        optimizer = dspy.Predict(StructuredAnswer)
        result = optimizer(question=prompt)
        instructions = getattr(result, "instructions", None)
        return instructions.strip() if isinstance(instructions, str) and instructions.strip() else prompt
    except Exception:
        return prompt
