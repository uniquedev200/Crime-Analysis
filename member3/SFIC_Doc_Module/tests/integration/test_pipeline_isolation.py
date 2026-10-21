"""Integration tests for cross-case data isolation.

Test requirements (PLAN.md Section 8 H3 task card & Gate 3):
- Back-to-back and concurrent processing of Case A and Case B
- Zero cross-case contamination: assert no Case A strings in Case B prompts or outputs,
  and no Case B strings in Case A prompts or outputs.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from atlas.llm.mock import MockProvider
from atlas.pipeline.runner import PipelineRunner
from atlas.pipeline.status import load_case_result


@pytest.mark.gate3
def test_back_to_back_case_isolation(tmp_path: Path) -> None:
    """Back-to-back processing of Case A and Case B exhibits zero cross-case contamination."""
    # Unique sentinel tokens for each case
    sentinel_a = "SENTINEL_ALPHA_UNIQUE_A_98124"
    sentinel_b = "SENTINEL_BETA_UNIQUE_B_54321"

    doc_a = tmp_path / "doc_a.txt"
    doc_a.write_text(f"Evidence document for Case A. Notes: {sentinel_a}", encoding="utf-8")

    doc_b = tmp_path / "doc_b.txt"
    doc_b.write_text(f"Evidence document for Case B. Notes: {sentinel_b}", encoding="utf-8")

    out_dir = tmp_path / "isolation_outputs"

    client_a = MockProvider()
    runner_a = PipelineRunner(llm_client=client_a)
    result_a = runner_a.run(
        case_id="CASE-ISO-A",
        file_paths=[doc_a],
        provider="mock",
        output_dir=out_dir,
    )

    client_b = MockProvider()
    runner_b = PipelineRunner(llm_client=client_b)
    result_b = runner_b.run(
        case_id="CASE-ISO-B",
        file_paths=[doc_b],
        provider="mock",
        output_dir=out_dir,
    )

    # 1. Assert no Case A strings in Case B captured prompts
    for p in client_b.captured_prompts:
        prompt_text = json.dumps(p, ensure_ascii=False)
        assert sentinel_a not in prompt_text
        assert "CASE-ISO-A" not in prompt_text

    # 2. Assert no Case B strings in Case A captured prompts
    for p in client_a.captured_prompts:
        prompt_text = json.dumps(p, ensure_ascii=False)
        assert sentinel_b not in prompt_text
        assert "CASE-ISO-B" not in prompt_text

    # 3. Assert outputs on disk contain zero cross-case sentinel strings
    run_b_dir = out_dir / "CASE-ISO-B" / result_b.run.run_id
    for f in run_b_dir.iterdir():
        if f.is_file():
            content = f.read_text(encoding="utf-8")
            assert sentinel_a not in content
            assert "CASE-ISO-A" not in content

    run_a_dir = out_dir / "CASE-ISO-A" / result_a.run.run_id
    for f in run_a_dir.iterdir():
        if f.is_file():
            content = f.read_text(encoding="utf-8")
            assert sentinel_b not in content
            assert "CASE-ISO-B" not in content


@pytest.mark.gate3
def test_concurrent_case_isolation(tmp_path: Path) -> None:
    """Concurrent processing of Case A and Case B exhibits zero cross-case contamination."""
    sentinel_x = "SECRET_TOKEN_CASE_X_777"
    sentinel_y = "SECRET_TOKEN_CASE_Y_888"

    doc_x = tmp_path / "doc_x.txt"
    doc_x.write_text(f"Investigation report X with token: {sentinel_x}", encoding="utf-8")

    doc_y = tmp_path / "doc_y.txt"
    doc_y.write_text(f"Investigation report Y with token: {sentinel_y}", encoding="utf-8")

    out_dir = tmp_path / "concurrent_outputs"

    def run_case_x() -> str:
        runner = PipelineRunner()
        res = runner.run(
            case_id="CASE-CONCUR-X",
            file_paths=[doc_x],
            provider="mock",
            output_dir=out_dir,
        )
        return res.run.run_id

    def run_case_y() -> str:
        runner = PipelineRunner()
        res = runner.run(
            case_id="CASE-CONCUR-Y",
            file_paths=[doc_y],
            provider="mock",
            output_dir=out_dir,
        )
        return res.run.run_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_x = executor.submit(run_case_x)
        future_y = executor.submit(run_case_y)

        run_id_x = future_x.result()
        run_id_y = future_y.result()

    result_x = load_case_result("CASE-CONCUR-X", run_id=run_id_x, output_dir=out_dir)
    result_y = load_case_result("CASE-CONCUR-Y", run_id=run_id_y, output_dir=out_dir)

    assert result_x is not None
    assert result_y is not None

    # Inspect all written files for Case X and Case Y
    dir_x = out_dir / "CASE-CONCUR-X" / run_id_x
    for f in dir_x.iterdir():
        if f.is_file():
            content = f.read_text(encoding="utf-8")
            assert sentinel_y not in content
            assert "CASE-CONCUR-Y" not in content

    dir_y = out_dir / "CASE-CONCUR-Y" / run_id_y
    for f in dir_y.iterdir():
        if f.is_file():
            content = f.read_text(encoding="utf-8")
            assert sentinel_x not in content
            assert "CASE-CONCUR-X" not in content
