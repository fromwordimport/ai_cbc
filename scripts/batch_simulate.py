"""Batch simulation script — run a small-scale end-to-end CBC study.

Usage:
    uv run python scripts/batch_simulate.py \
        --n-personas 10 \
        --study-id dw-pilot \
        --seed 42 \
        --output-dir ./outputs

This script wires together:
  1. Persona generation (SeedGenerator + ProfileGenerator)
  2. Bias auditing (BiasAuditor)
  3. Questionnaire generation (QuestionnaireGenerator)
  4. Choice simulation (CBCChoiceSimulator)
  5. Dataset export (CBCRawDataset → JSON/CSV)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure src is on the path when run as a script
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import structlog

from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer
from aicbc.core.scoring.bias_auditor import BiasAuditor
from aicbc.core.simulation.cbc_choice_simulator import CBCChoiceSimulator
from aicbc.cost.fuse import CostFuse, CostFuseError
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.questionnaire.generator import QuestionnaireGenerator
from aicbc.questionnaire.models import DesignAlgorithm, DesignParameters
from aicbc.questionnaire.response_models import CBCRawDataset, DatasetMetadata

logger = structlog.get_logger("aicbc.batch_simulate")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small-scale CBC batch simulation")
    parser.add_argument("--n-personas", type=int, default=10, help="Number of personas to generate")
    parser.add_argument("--study-id", type=str, default="dw-pilot", help="Study identifier")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output-dir", type=str, default="./outputs", help="Output directory")
    parser.add_argument("--deterministic", action="store_true", help="Use deterministic choice simulation")
    parser.add_argument("--bias-audit", action="store_true", default=True, help="Run bias audit on generated personas")
    parser.add_argument("--skip-validation", action="store_true", default=False, help="Skip schema/logic validation")
    return parser.parse_args()


def run_batch_simulation(
    n_personas: int,
    study_id: str,
    seed: int,
    output_dir: Path,
    deterministic: bool = False,
    bias_audit: bool = True,
    skip_validation: bool = False,
) -> dict[str, object]:
    """Run the full batch simulation pipeline."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log = logger.bind(study_id=study_id, n_personas=n_personas, seed=seed)
    log.info("batch_simulation_start")

    overall_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Cost fuse setup
    # ------------------------------------------------------------------
    cost_fuse = CostFuse()
    total_cost_cny = 0.0
    cost_fuse_triggered = False

    # ------------------------------------------------------------------
    # Step 1: Generate personas
    # ------------------------------------------------------------------
    seed_gen = SeedGenerator(seed=seed)
    profile_gen = ProfileGenerator()
    authenticity_scorer = AuthenticityScorer()
    bias_auditor = BiasAuditor()

    personas = []
    failed = 0
    bias_findings_total = 0
    auth_scores = []

    safe_study_id = study_id.replace("-", "_")
    for i in range(n_personas):
        # Pre-call cost fuse check
        allowed, fuse_status, _ = cost_fuse.pre_call_check(study_id=study_id)
        if not allowed:
            log.error("cost_fuse_triggered", status=fuse_status.value, index=i)
            cost_fuse_triggered = True
            break

        persona_id = f"persona-{safe_study_id}-{i + 1:03d}"
        try:
            seed_config = seed_gen.generate_seed()
            persona = profile_gen.generate(persona_id, seed_config)
        except CostFuseError as exc:
            log.error("persona_generation_cost_fuse", index=i, error=str(exc))
            cost_fuse_triggered = True
            break
        except Exception as exc:
            log.warning("persona_generation_failed", index=i, error=str(exc))
            failed += 1
            continue

        # Quality checks
        auth_result = authenticity_scorer.score(persona)
        persona.authenticity_score = auth_result.total_score
        auth_scores.append(auth_result.total_score)

        # Bias audit
        if bias_audit:
            audit = bias_auditor.audit(persona)
            persona.bias_audit_status = audit.status
            bias_findings_total += len(audit.findings)
            if not audit.passed:
                log.warning(
                    "bias_audit_failed",
                    persona_id=persona.persona_id,
                    findings=len(audit.findings),
                )
        else:
            persona.bias_audit_status = "PENDING"

        personas.append(persona)
        total_cost_cny += persona.generation_metadata.cost_cny
        log.info(
            "persona_generated",
            index=i,
            persona_id=persona.persona_id,
            segment=persona.segment,
            authenticity=auth_result.total_score,
            bias_passed=persona.bias_audit_status == "PASSED",
            cost_cny=persona.generation_metadata.cost_cny,
        )

    log.info("persona_generation_complete", generated=len(personas), failed=failed, total_cost_cny=round(total_cost_cny, 2))

    # Save personas
    personas_path = output_dir / f"{study_id}_personas.json"
    with open(personas_path, "w", encoding="utf-8") as f:
        json.dump([p.model_dump(mode="json") for p in personas], f, ensure_ascii=False, indent=2)
    log.info("personas_exported", path=str(personas_path))

    # ------------------------------------------------------------------
    # Step 2: Generate questionnaire
    # ------------------------------------------------------------------
    qgen = QuestionnaireGenerator()
    study = qgen.create_study(
        study_id=study_id,
        product_category="洗碗机",
        research_goal="小批量模拟验证",
        design_parameters=DesignParameters(
            n_choice_sets=12,
            n_alternatives=3,
            algorithm=DesignAlgorithm.D_OPTIMAL,
            seed=seed,
        ),
    )
    questionnaire = qgen.generate_questionnaire(study, seed=seed)
    log.info(
        "questionnaire_generated",
        n_choice_sets=len(questionnaire.choice_sets),
        d_efficiency=questionnaire.d_efficiency,
    )

    # Save questionnaire
    q_path = output_dir / f"{study_id}_questionnaire.json"
    with open(q_path, "w", encoding="utf-8") as f:
        json.dump(questionnaire.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Step 3: Simulate choices
    # ------------------------------------------------------------------
    simulator = CBCChoiceSimulator(attributes=study.attributes)
    all_records = []
    summaries = []

    for idx, persona in enumerate(personas):
        try:
            raw_slice, persona_response = simulator.simulate(
                persona=persona,
                questionnaire=questionnaire,
                deterministic=deterministic,
                seed=seed + idx,
            )
        except Exception as exc:
            log.error("simulation_failed", persona_id=persona.persona_id, error=str(exc))
            continue

        # Fix respondent_index
        for record in raw_slice.choice_records:
            record.respondent_index = idx

        all_records.extend(raw_slice.choice_records)
        summaries.append({
            "persona_id": persona.persona_id,
            "segment": persona.segment,
            "n_choice_sets": len(persona_response.responses),
            "completion_status": persona_response.completion_status,
        })

    log.info("choice_simulation_complete", simulated=len(summaries))

    # ------------------------------------------------------------------
    # Step 4: Export dataset
    # ------------------------------------------------------------------
    dataset = CBCRawDataset(
        metadata=DatasetMetadata(
            study_id=study_id,
            n_respondents=len(summaries),
            n_choice_sets=questionnaire.design_parameters.n_choice_sets,
            n_alternatives=questionnaire.design_parameters.n_alternatives,
            attributes=[attr.model_dump(mode="json") for attr in study.attributes],
        ),
        choice_records=all_records,
    )

    dataset_path = output_dir / f"{study_id}_raw_dataset.json"
    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(dataset.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    log.info("dataset_exported", path=str(dataset_path), n_records=len(all_records))

    # ------------------------------------------------------------------
    # Step 5: Bias audit batch report
    # ------------------------------------------------------------------
    if bias_audit and personas:
        batch_audit = bias_auditor.audit_batch(personas)
        audit_path = output_dir / f"{study_id}_bias_audit.json"
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(batch_audit, f, ensure_ascii=False, indent=2)
        log.info("bias_audit_exported", path=str(audit_path), **batch_audit)
    else:
        batch_audit = {}
        audit_path = None

    # ------------------------------------------------------------------
    # Step 6: Cost tracking report
    # ------------------------------------------------------------------
    fuse_status, fuse_details = cost_fuse.tracker.check_fuse_status(study_id=study_id)
    cost_report = {
        "total_cost_cny": round(total_cost_cny, 2),
        "fuse_status": fuse_status.value,
        "cost_breakdown": {
            "study_cost_cny": round(fuse_details["costs_cny"]["study"], 2),
            "daily_cost_cny": round(fuse_details["costs_cny"]["daily"], 2),
            "weekly_cost_cny": round(fuse_details["costs_cny"]["weekly"], 2),
            "monthly_cost_cny": round(fuse_details["costs_cny"]["monthly"], 2),
        },
        "budget_thresholds": fuse_details["thresholds"],
        "consumption_ratios": fuse_details["ratios"],
        "cost_fuse_triggered": cost_fuse_triggered,
    }

    cost_path = output_dir / f"{study_id}_cost_report.json"
    with open(cost_path, "w", encoding="utf-8") as f:
        json.dump(cost_report, f, ensure_ascii=False, indent=2)
    log.info("cost_report_exported", path=str(cost_path), **cost_report)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    elapsed = round(time.perf_counter() - overall_start, 3)
    summary = {
        "study_id": study_id,
        "n_personas_requested": n_personas,
        "n_personas_generated": len(personas),
        "n_personas_failed": failed,
        "n_simulated": len(summaries),
        "d_efficiency": questionnaire.d_efficiency,
        "a_efficiency": questionnaire.a_efficiency,
        "authenticity": {
            "scores": auth_scores,
            "mean": round(sum(auth_scores) / len(auth_scores), 2) if auth_scores else 0,
            "min": min(auth_scores) if auth_scores else 0,
            "max": max(auth_scores) if auth_scores else 0,
        },
        "bias_audit": batch_audit,
        "cost_report": cost_report,
        "elapsed_seconds": elapsed,
        "output_files": {
            "personas": str(personas_path),
            "questionnaire": str(q_path),
            "dataset": str(dataset_path),
            "cost_report": str(cost_path),
        },
    }

    if audit_path:
        summary["output_files"]["bias_audit"] = str(audit_path)

    summary_path = output_dir / f"{study_id}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log.info("batch_simulation_complete", summary_path=str(summary_path), elapsed_seconds=elapsed)

    return summary


if __name__ == "__main__":
    args = _parse_args()
    summary = run_batch_simulation(
        n_personas=args.n_personas,
        study_id=args.study_id,
        seed=args.seed,
        output_dir=Path(args.output_dir),
        deterministic=args.deterministic,
        bias_audit=args.bias_audit,
        skip_validation=args.skip_validation,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
