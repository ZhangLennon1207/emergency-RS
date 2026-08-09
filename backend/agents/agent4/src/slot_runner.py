import json
import re

TAG_RE = re.compile(
    r"^\s*<zh-CN>\s*(.*?)\s*</zh-CN>\s*"
    r"<en-US>\s*(.*?)\s*</en-US>\s*$",
    flags=re.S,
)


INSTRUCTIONS = {
    "finding_bilingual":
        (
            "Generate a concise bilingual formal report finding "
            "from the supplied verified claim. Preserve the "
            "verification strength and add no new facts."
        ),

    "limitation_bilingual":
        (
            "Generate a concise bilingual report limitation from "
            "the supplied rejected or pending verified claim. "
            "Make clear that it is not a formal disaster finding."
        ),

    "summary_bilingual":
        (
            "Generate a concise bilingual executive summary using "
            "only the supplied verified findings. Add no new facts "
            "and do not present the result as an authoritative "
            "field conclusion."
        ),
}


RISK_TERMS = [
    "death",
    "deaths",
    "dead",
    "fatality",
    "fatalities",
    "injured",
    "injuries",
    "casualties",
    "economic loss",
    "financial loss",
    "government response",
    "rescue operation",
    "compensation",

    "死亡",
    "伤亡",
    "受伤",
    "经济损失",
    "财产损失",
    "政府响应",
    "救援行动",
    "赔偿",
]


def _numbers(text):
    return set(
        re.findall(
            r"(?<![A-Za-z])\d+(?:\.\d+)?%?",
            str(text),
        )
    )


def _parse(text):
    text = str(
        text
    ).strip()

    m = TAG_RE.match(
        text
    )

    if not m:
        return None

    return {
        "zh-CN":
            m.group(1).strip(),

        "en-US":
            m.group(2).strip(),
    }


def audit_slot(
    payload,
    bilingual,
):
    if not bilingual:
        return {
            "pass":
                False,

            "errors": [
                "unrecoverable_bilingual_format"
            ],
        }

    source = json.dumps(
        payload,
        ensure_ascii=False,
    ).lower()

    output = (
        bilingual[
            "zh-CN"
        ]
        + "\n"
        + bilingual[
            "en-US"
        ]
    ).lower()

    errors = []

    for term in RISK_TERMS:
        t = term.lower()

        if (
            t in output
            and t not in source
        ):
            errors.append(
                "new_high_risk_fact"
            )
            break

    unexpected_numbers = (
        _numbers(
            output
        )
        -
        _numbers(
            source
        )
    )

    if unexpected_numbers:
        errors.append(
            "new_numeric_fact"
        )

    return {
        "pass":
            not errors,

        "errors":
            sorted(
                set(
                    errors
                )
            ),

        "unexpected_numbers":
            sorted(
                unexpected_numbers
            ),
    }


class Agent4SlotRunner:

    def __init__(
        self,
        base_model,
        adapter,
        system_prompt,
    ):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._torch = torch
        self.base_model = (
            base_model
        )

        self.adapter = adapter

        self.system_prompt = (
            system_prompt
        )

        quant = (
            BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=(
                    torch.bfloat16
                ),
            )
        )

        self.tokenizer = (
            AutoTokenizer
            .from_pretrained(
                base_model,
                trust_remote_code=True,
            )
        )

        base = (
            AutoModelForCausalLM
            .from_pretrained(
                base_model,
                device_map="auto",
                trust_remote_code=True,
                torch_dtype=torch.bfloat16,
                quantization_config=quant,
            )
        )

        self.model = (
            PeftModel
            .from_pretrained(
                base,
                adapter,
            )
        )

        self.model.eval()

    def _generate_raw(
        self,
        task_type,
        payload,
        retry=False,
    ):
        instruction = (
            INSTRUCTIONS[
                task_type
            ]
        )

        if retry:
            instruction += (
                "\nYour previous answer did not satisfy "
                "the output contract. Return exactly:\n"
                "<zh-CN>Chinese text</zh-CN>\n"
                "<en-US>English text</en-US>\n"
                "Do not output anything outside these tags."
            )

        user = (
            instruction
            + "\n\n"
            + json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

        messages = [
            {
                "role":
                    "system",

                "content":
                    self.system_prompt,
            },
            {
                "role":
                    "user",

                "content":
                    user,
            },
        ]

        prompt = (
            self.tokenizer
            .apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
        ).to(
            self.model.device
        )

        max_tokens = (
            420
            if task_type
            == "summary_bilingual"
            else 240
        )

        with self._torch.inference_mode():

            result = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=max_tokens,
            )

        generated = result[
            :,
            inputs.input_ids.shape[1]:
        ]

        return (
            self.tokenizer.decode(
                generated[0],
                skip_special_tokens=True,
            )
            .strip()
        )

    def generate(
        self,
        task_type,
        payload,
    ):
        raw = self._generate_raw(
            task_type,
            payload,
            retry=False,
        )

        parsed = _parse(
            raw
        )

        audit = audit_slot(
            payload,
            parsed,
        )

        retry_used = False
        raw_retry = None

        if not audit[
            "pass"
        ]:

            retry_used = True

            raw_retry = (
                self._generate_raw(
                    task_type,
                    payload,
                    retry=True,
                )
            )

            retry_parsed = (
                _parse(
                    raw_retry
                )
            )

            retry_audit = (
                audit_slot(
                    payload,
                    retry_parsed,
                )
            )

            if retry_audit[
                "pass"
            ]:
                parsed = (
                    retry_parsed
                )

                audit = (
                    retry_audit
                )

        return {
            "bilingual":
                parsed,

            "audit":
                audit,

            "retry_used":
                retry_used,

            "raw_output":
                raw,

            "raw_retry_output":
                raw_retry,
        }
