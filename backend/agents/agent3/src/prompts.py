from pathlib import Path


_PROMPT = (
    Path(__file__).resolve().parent
    / "prompt_v3_1.txt"
)


def get_system_prompt():
    return _PROMPT.read_text(
        encoding="utf-8"
    ).strip()
