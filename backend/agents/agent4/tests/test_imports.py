from pathlib import Path


def test_expected_files_exist():
    root = Path(__file__).resolve().parents[1]

    required = [
        "adapter.py",
        "manifest.json",
        "requirements.txt",
        "README.md",
        "src/slot_runner.py",
        "src/report_runtime.py",
        "src/assemble_report.py",
        "src/validate_report.py",
        "src/image_binding.py",
        "src/renderers_separate.py",
        "src/system_prompt.txt",
        "src/platform_report_schema_v3.json",
    ]

    missing = [
        x
        for x in required
        if not (root / x).is_file()
    ]

    assert not missing, (
        "Missing package files: "
        + str(missing)
    )
