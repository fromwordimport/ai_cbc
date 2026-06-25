"""Celery tasks for async HB/MNL analysis.

Offloads CPU-intensive MCMC sampling (2-5 minutes for NUTS) from the
FastAPI event loop to a background worker process.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
from celery import Celery
from celery.signals import worker_process_init
from motor.motor_asyncio import AsyncIOMotorClient

from aicbc.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "aicbc.analysis",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,
)

_mongo_client: AsyncIOMotorClient[Any] | None = None
_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent event loop for this worker process.

    Celery prefork workers run tasks in the child process main thread.
    Motor/Beanie require a single long-lived event loop; creating and
    closing loops per operation (as ``asyncio.run`` does) leaves Motor
    bound to a closed loop.  We therefore keep one loop open for the
    lifetime of the worker.
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def _run_async(coro: Any) -> Any:
    """Run an async coroutine on the worker's persistent event loop."""
    return _get_worker_loop().run_until_complete(coro)


@worker_process_init.connect  # type: ignore[untyped-decorator]
def init_mongo_for_worker(**kwargs: object) -> None:
    """Initialize MongoDB/Beanie in each Celery worker process.

    The FastAPI main process initializes Beanie during lifespan, but Celery
    worker pool processes are separate and must set up their own Motor client
    before any Mongo-backed store can be used.
    """
    use_memory = os.environ.get("USE_MEMORY_STORE", "").lower() in ("1", "true", "yes")
    env = settings.environment.lower()
    is_dev_without_mongo = env in ("development", "dev", "testing", "test") and (
        not settings.database.mongodb_url
        or settings.database.mongodb_url == "mongodb://localhost:27017"
    )
    if use_memory or is_dev_without_mongo:
        logger.info("worker_using_memory_store")
        return

    from beanie import init_beanie

    from aicbc.core.models.db_documents import ALL_DOCUMENT_MODELS

    global _mongo_client

    async def _init() -> None:
        global _mongo_client
        _mongo_client = AsyncIOMotorClient(
            settings.database.mongodb_url,
            maxPoolSize=settings.database.mongodb_max_connections,
        )
        await init_beanie(
            database=_mongo_client[settings.database.mongodb_database],
            document_models=ALL_DOCUMENT_MODELS,
        )

    loop = _get_worker_loop()
    try:
        loop.run_until_complete(_init())
        from aicbc.core import store_mongo

        store_mongo.set_worker_loop(loop)
        logger.info("worker_mongodb_beanie_initialized")
    except Exception:
        logger.exception("worker_mongodb_init_failed")
        raise


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "aicbc.analysis.*": {"queue": "analysis"},
        "aicbc.analysis.run_persona_generation_task": {"queue": "persona_generation"},
    },
    result_expires=300,  # Results expire after 5 minutes to reduce Redis memory/commands
    result_extended=False,  # Do not store task name/args in result backend
    task_ignore_result=True,  # Most tasks only need state (PENDING/STARTED/SUCCESS), not return value
)

logger = structlog.get_logger("aicbc.analysis.tasks")


def _save_dead_letter(
    task_name: str,
    analysis_id: str | None,
    study_id: str | None,
    exception: Exception,
) -> None:
    """Persist a dead-letter record for a failed task."""
    from aicbc.core.models.db_documents import DeadLetterDocument

    async def _insert() -> None:
        doc = DeadLetterDocument(
            task_name=task_name,
            analysis_id=analysis_id,
            study_id=study_id,
            exception=f"{type(exception).__name__}: {exception}",
        )
        await doc.insert()

    try:
        _run_async(_insert())
    except Exception:
        logger.exception("dead_letter_insert_failed")


@celery_app.task(
    bind=True,
    name="aicbc.analysis.run_analysis_task",
    time_limit=600,  # Hard timeout: 10 minutes (HB NUTS worst-case)
    soft_time_limit=540,  # Soft timeout: 9 minutes (allows graceful cleanup)
)
def run_analysis_task(
    self,
    study_id: str,
    analysis_id: str,
    model_type: str,
    config_json: str,
) -> dict:
    """Run HB or MNL conjoint analysis as a background Celery task.

    Encapsulates the full analysis pipeline:
      1. Retrieve study attributes and response dataset from stores
      2. Validate and preprocess (long-format encoding)
      3. Fit the model (HB via PyMC NUTS, or MNL via statsmodels)
      4. Extract importance, WTP, and convergence diagnostics
      5. Persist all derived results in AnalysisStore

    The API route enqueues this task and returns ``202 Accepted``
    immediately, unblocking the event loop.  Callers poll
    ``GET /analysis/{analysis_id}/status`` for progress.

    Args:
        study_id: Study identifier used to look up attributes and dataset.
        analysis_id: Unique analysis job identifier.
        model_type: ``"hb"``, ``"mnl"``, or ``"latent_class"``.
        config_json: JSON-serialized :class:`~aicbc.analysis.models.AnalyzeRequest`
            fields (n_draws, n_tune, n_chains, target_accept).

    Returns:
        dict with ``status`` and ``analysis_id`` on completion.

    Raises:
        ValueError: If the study or dataset is missing, or validation fails.
    """
    from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine
    from aicbc.analysis.engines.mnl_engine import MNLEngine
    from aicbc.analysis.models import (
        AnalysisResultResponse,
        ConvergenceDiagnostics,
        ImportanceResponse,
        ImportanceStats,
        PriceCoefficientSummary,
        WTPAttribute,
        WTPComparison,
        WTPResponse,
    )
    from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
    from aicbc.analysis.results.importance import aggregate_importance, compute_importance
    from aicbc.analysis.results.wtp import WTPCalculator
    from aicbc.analysis.store import get_analysis_store
    from aicbc.core.security.input_sanitizer import sanitize_id
    from aicbc.core.store import get_questionnaire_store, get_response_store
    from aicbc.questionnaire.models import AttributeType

    # ── Input sanitization (defence-in-depth) ────────────────────────────
    study_id = sanitize_id(study_id, field_name="study_id")
    analysis_id = sanitize_id(analysis_id, field_name="analysis_id")

    log = logger.bind(study_id=study_id, analysis_id=analysis_id, model_type=model_type)
    log.info("analysis_task_started")

    config = json.loads(config_json)
    analysis_store = get_analysis_store()

    # ── Mark RUNNING ───────────────────────────────────────────────────
    job = analysis_store.update_job_status(analysis_id, "RUNNING", progress=0.0)
    if job is not None:
        job.started_at = datetime.now(UTC)
        analysis_store.save_job(job)

    try:
        # ── Retrieve data ────────────────────────────────────────────
        q_store = get_questionnaire_store()
        study = q_store.get_study(study_id)
        if study is None:
            raise ValueError(f"Study '{study_id}' not found")

        attributes = study.attributes

        r_store = get_response_store()
        dataset = r_store.get_dataset(study_id)
        if dataset is None:
            raise ValueError(f"No response dataset for study '{study_id}'")

        # ── Validate (fail-fast) ─────────────────────────────────────
        validation = validate_dataset(dataset, attributes)
        if not validation["valid"]:
            raise ValueError(f"Dataset validation failed: {validation['errors']}")

        analysis_store.update_job_status(analysis_id, "RUNNING", progress=10.0)

        # ── Preprocess ───────────────────────────────────────────────
        log.info("analysis_preprocessing")
        df_long = to_long_format(dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        analysis_store.update_job_status(analysis_id, "RUNNING", progress=25.0)

        # ── Fit model ────────────────────────────────────────────────
        log.info("analysis_fitting_model")
        if model_type == "hb":
            requested_chains = config.get("n_chains", 4)
            n_chains = min(requested_chains, settings.hb_max_chains)
            n_cores = (
                settings.hb_cores if settings.hb_cores is not None else config.get("n_cores", 1)
            )
            requested_draws = config.get("n_draws", 1000)
            requested_tune = config.get("n_tune", 1000)
            max_draws = settings.hb_max_draws
            hb_config = HBConfig(
                n_draws=requested_draws,
                n_tune=requested_tune,
                n_chains=n_chains,
                n_cores=n_cores,
                target_accept=config.get("target_accept", 0.9),
                max_draws=max_draws,
            )
            engine = HBEngine(hb_config)
            result = engine.fit(df_long, feature_cols)
        elif model_type == "mnl":
            engine = MNLEngine()
            result = engine.fit(df_long, feature_cols)
        else:
            # latent_class / unknown: fallback to HB
            hb_config = HBConfig()
            engine = HBEngine(hb_config)
            result = engine.fit(df_long, feature_cols)

        analysis_store.update_job_status(analysis_id, "RUNNING", progress=75.0)

        # ── Compute timing ───────────────────────────────────────────
        started = job.started_at if job and job.started_at else datetime.now(UTC)
        processing_time = (datetime.now(UTC) - started).total_seconds()

        # ── Build AnalysisResultResponse ─────────────────────────────
        util_df = pd.DataFrame.from_dict(result.individual_utilities, orient="index")

        # Compute price_std BEFORE importance (used by both importance and WTP)
        price_attrs = [a for a in attributes if a.type == AttributeType.PRICE]
        price_col = price_attrs[0].id if price_attrs else "price"
        price_std = 1.0
        if price_attrs:
            prices = [float(lv.value) for lv in price_attrs[0].levels]
            price_std = float(np.std(prices, ddof=0)) if len(prices) > 1 else 1.0

        # Importance — pass price_std to correct for z-score encoding
        importance_df = compute_importance(util_df, attributes, price_std=price_std)
        importance_agg = aggregate_importance(importance_df)
        importance_dict = {
            attr_id: float(row["mean"]) for attr_id, row in importance_agg.iterrows()
        }

        # Convergence diagnostics — handle both HB (MCMC) and MNL (MLE)
        is_hb = model_type == "hb"
        diag = result.diagnostics if is_hb and result.diagnostics else {}
        convergence = ConvergenceDiagnostics(
            rhat_max=result.rhat_max if hasattr(result, "rhat_max") else 0.0,
            rhat_by_param=(diag.get("rhat_by_param", {}) if is_hb else {}),
            ess_bulk_min=(int(result.ess_bulk_min) if hasattr(result, "ess_bulk_min") else 0),
            ess_tail_min=(int(result.ess_tail_min) if hasattr(result, "ess_tail_min") else 0),
            ess_by_param=(diag.get("ess_by_param", {}) if is_hb else {}),
            converged=result.converged,
            reliable_ess=(diag.get("reliable_ess", False) if is_hb else result.converged),
            divergences=diag.get("divergences", 0) if is_hb else 0,
            tree_depth_max=diag.get("tree_depth_max", 0) if is_hb else 0,
        )

        # WTP
        if price_col in util_df.columns:
            wtp_calc = WTPCalculator(util_df, price_col=price_col, price_std=price_std)
            wtp_data = wtp_calc.compute_all_wtp(attributes)
        else:
            wtp_data = {}

        analysis_response = AnalysisResultResponse(
            analysis_id=analysis_id,
            study_id=study_id,
            status="COMPLETED",
            model_type=model_type,
            convergence=convergence,
            population_params={
                "mu": result.population_mu,
                "sigma": result.population_sigma,
            },
            individual_utilities=result.individual_utilities,
            importance=importance_dict,
            wtp=wtp_data,
            processing_time_seconds=processing_time,
            completed_at=datetime.now(UTC),
        )

        # ── Persist all derived results ──────────────────────────────
        analysis_store.save_result(analysis_response)
        analysis_store.save_convergence(analysis_id, convergence)

        # Importance — overall, by_segment, and individual distribution
        overall_dict: dict[str, ImportanceStats] = {}
        for attr_id, row in importance_agg.iterrows():
            overall_dict[attr_id] = ImportanceStats(
                mean=float(row["mean"]),
                std=float(row["std"]),
                median=float(row["median"]),
                min=float(row["min"]),
                max=float(row["max"]),
                q25=float(row["q25"]),
                q75=float(row["q75"]),
                ci_95_lower=float(row.get("ci_95_lower", row["mean"])),
                ci_95_upper=float(row.get("ci_95_upper", row["mean"])),
            )

        # Individual distribution (for box/violin plots)
        individual_dict: dict[str, dict[str, float]] = {}
        for resp_id, imp_row in importance_df.iterrows():
            individual_dict[resp_id] = {col: float(imp_row[col]) for col in importance_df.columns}

        # By-segment importance (aggregated per segment)
        by_segment: dict[str, dict[str, ImportanceStats]] | None = None
        # Build segment labels from dataset response metadata
        segment_map: dict[str, list[str]] = {}
        for record in dataset.choice_records:
            seg = getattr(record, "segment", None) or "unknown"
            segment_map.setdefault(seg, []).append(record.respondent_id)

        if len(segment_map) > 1:
            by_segment = {}
            for seg_label, resp_ids in segment_map.items():
                seg_ids = [rid for rid in resp_ids if rid in importance_df.index]
                if len(seg_ids) < 2:
                    continue  # skip segments with too few respondents
                seg_df = importance_df.loc[seg_ids]
                seg_agg = aggregate_importance(seg_df)
                by_segment[seg_label] = {}
                for attr_id, row in seg_agg.iterrows():
                    by_segment[seg_label][attr_id] = ImportanceStats(
                        mean=float(row["mean"]),
                        std=float(row["std"]),
                        median=float(row["median"]),
                        min=float(row["min"]),
                        max=float(row["max"]),
                        q25=float(row["q25"]),
                        q75=float(row["q75"]),
                        ci_95_lower=float(row.get("ci_95_lower", row["mean"])),
                        ci_95_upper=float(row.get("ci_95_upper", row["mean"])),
                    )

        importance_resp = ImportanceResponse(
            overall=overall_dict,
            by_segment=by_segment,
            individual=individual_dict if individual_dict else None,
        )
        analysis_store.save_importance(analysis_id, importance_resp)

        # WTP
        if price_col in util_df.columns:
            price_summary = wtp_calc.price_coefficient_summary()
            wtp_resp = WTPResponse(
                wtp_values={
                    attr_id: WTPAttribute(
                        comparisons=[
                            WTPComparison(
                                from_level=c["from_level"],
                                to_level=c["to_level"],
                                wtp_mean=c["wtp_mean"],
                                wtp_median=c["wtp_median"],
                                wtp_std=c["wtp_std"],
                                ci_95_lower=c["ci_95_lower"],
                                ci_95_upper=c["ci_95_upper"],
                                n_valid=c["n_valid"],
                            )
                            for c in attr_data["comparisons"]
                        ]
                    )
                    for attr_id, attr_data in wtp_data.items()
                },
                price_coefficient_summary=PriceCoefficientSummary(
                    mean=price_summary["mean"],
                    median=price_summary["median"],
                    std=price_summary["std"],
                    negative_rate=price_summary["negative_rate"],
                    n_positive_outliers=price_summary["n_positive_outliers"],
                ),
            )
            analysis_store.save_wtp(analysis_id, wtp_resp)

        # ── Mark COMPLETED ───────────────────────────────────────────
        analysis_store.update_job_status(analysis_id, "COMPLETED", progress=100.0)

        log.info("analysis_task_completed")
        return {"status": "COMPLETED", "analysis_id": analysis_id}

    except Exception as exc:
        log.exception("analysis_task_failed")
        import traceback

        err_summary = f"{type(exc).__name__}: {exc}"
        err_traceback = traceback.format_exc()
        job = analysis_store.update_job_status(analysis_id, "FAILED", progress=0.0)
        if job is not None:
            metadata = getattr(job, "metadata", None)
            if metadata is not None:
                metadata["error"] = err_summary
                metadata["traceback"] = err_traceback[-2000:]
            analysis_store.save_job(job)
        _save_dead_letter(
            task_name="aicbc.analysis.run_analysis_task",
            analysis_id=analysis_id,
            study_id=study_id,
            exception=exc,
        )
        raise


@celery_app.task(
    bind=True,
    name="aicbc.analysis.run_latent_class_task",
    time_limit=900,  # 15 minutes — LCM can be slower than HB
    soft_time_limit=780,
)
def run_latent_class_task(
    self,
    study_id: str,
    analysis_id: str,
    config_json: str,
) -> dict:
    """Fit a latent class model as a background Celery task.

    Stores a generic :class:`AnalysisResultResponse` so the standard status
    endpoint works, and persists the full :class:`LatentClassResponse` as a
    derivative artefact for ``GET /analysis/{id}/latent-class``.
    """
    from aicbc.analysis.engines.latent_class_engine import LatentClassConfig, LatentClassEngine
    from aicbc.analysis.models import (
        AnalysisResultResponse,
        ConvergenceDiagnostics,
        LatentClassResponse,
    )
    from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
    from aicbc.analysis.store import get_analysis_store
    from aicbc.core.security.input_sanitizer import sanitize_id
    from aicbc.core.store import get_questionnaire_store, get_response_store

    study_id = sanitize_id(study_id, field_name="study_id")
    analysis_id = sanitize_id(analysis_id, field_name="analysis_id")

    log = logger.bind(study_id=study_id, analysis_id=analysis_id, model_type="latent_class")
    log.info("latent_class_task_started")

    config = json.loads(config_json)
    analysis_store = get_analysis_store()

    job = analysis_store.update_job_status(analysis_id, "RUNNING", progress=0.0)
    if job is not None:
        job.started_at = datetime.now(UTC)
        analysis_store.save_job(job)

    try:
        q_store = get_questionnaire_store()
        study = q_store.get_study(study_id)
        if study is None:
            raise ValueError(f"Study '{study_id}' not found")
        attributes = study.attributes

        r_store = get_response_store()
        dataset = r_store.get_dataset(study_id)
        if dataset is None:
            raise ValueError(f"No response dataset for study '{study_id}'")

        validation = validate_dataset(dataset, attributes)
        if not validation["valid"]:
            raise ValueError(f"Dataset validation failed: {validation['errors']}")

        analysis_store.update_job_status(analysis_id, "RUNNING", progress=15.0)

        df_long = to_long_format(dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        analysis_store.update_job_status(analysis_id, "RUNNING", progress=30.0)

        lc_config = LatentClassConfig(
            n_classes=config.get("n_classes", 3),
            n_draws=config.get("n_draws", 500),
            n_tune=config.get("n_tune", 500),
            n_chains=config.get("n_chains", 2),
            target_accept=config.get("target_accept", 0.9),
            random_seed=42,
        )
        engine = LatentClassEngine(lc_config)
        result = engine.fit(df_long, feature_cols)

        analysis_store.update_job_status(analysis_id, "RUNNING", progress=80.0)

        started = job.started_at if job and job.started_at else datetime.now(UTC)
        processing_time = (datetime.now(UTC) - started).total_seconds()

        lc_response = LatentClassResponse(
            analysis_id=analysis_id,
            study_id=study_id,
            n_classes=lc_config.n_classes,
            converged=result.converged,
            rhat_max=result.rhat_max,
            ess_bulk_min=result.ess_bulk_min,
            ess_tail_min=result.ess_tail_min,
            class_probs=result.class_probs,
            class_utilities=result.class_utilities,
            individual_class_probs=result.individual_class_probs,
            assigned_class=result.assigned_class,
            processing_time_seconds=processing_time,
            completed_at=datetime.now(UTC),
        )
        analysis_store.save_latent_class_result(analysis_id, lc_response.model_dump(mode="json"))

        # Save a lightweight AnalysisResultResponse so the standard result/status
        # endpoints can mark the job as COMPLETED.
        generic_result = AnalysisResultResponse(
            analysis_id=analysis_id,
            study_id=study_id,
            status="COMPLETED",
            model_type="latent_class",
            convergence=ConvergenceDiagnostics(
                rhat_max=result.rhat_max,
                rhat_by_param=result.diagnostics.get("rhat_by_param", {})
                if result.diagnostics
                else {},
                ess_bulk_min=float(result.ess_bulk_min),
                ess_tail_min=float(result.ess_tail_min),
                ess_by_param=result.diagnostics.get("ess_by_param", {})
                if result.diagnostics
                else {},
                converged=result.converged,
                reliable_ess=result.diagnostics.get("reliable_ess", False)
                if result.diagnostics
                else False,
                divergences=result.diagnostics.get("divergences", 0) if result.diagnostics else 0,
                tree_depth_max=result.diagnostics.get("tree_depth_max", 0)
                if result.diagnostics
                else 0,
            ),
            population_params={"mu": {}, "sigma": {}}
            if not result.class_utilities
            else {
                "mu": result.class_utilities.get("class_0", {}),
                "sigma": dict.fromkeys(result.class_utilities.get("class_0", {}), 0.0),
            },
            individual_utilities={
                rid: dict(probs.items()) for rid, probs in result.individual_class_probs.items()
            },
            importance={},
            wtp={},
            processing_time_seconds=processing_time,
            completed_at=datetime.now(UTC),
        )
        analysis_store.save_result(generic_result)
        analysis_store.save_convergence(analysis_id, generic_result.convergence)

        analysis_store.update_job_status(analysis_id, "COMPLETED", progress=100.0)
        log.info("latent_class_task_completed")
        return {"status": "COMPLETED", "analysis_id": analysis_id}

    except Exception as exc:
        log.exception("latent_class_task_failed")
        analysis_store.update_job_status(analysis_id, "FAILED", progress=0.0)
        _save_dead_letter(
            task_name="aicbc.analysis.run_latent_class_task",
            analysis_id=analysis_id,
            study_id=study_id,
            exception=exc,
        )
        raise


@celery_app.task(
    bind=True,
    name="aicbc.analysis.run_persona_generation_task",
    time_limit=1800,  # 30 minutes for large batches
    soft_time_limit=1500,
)
def run_persona_generation_task(
    self,
    job_id: str,
    request_json: str,
) -> dict:
    """Run persona batch generation as a background Celery task."""
    from datetime import UTC, datetime

    from aicbc.agents.consumer_generator import ConsumerGeneratorAgent
    from aicbc.core.models.db_documents import PersonaGenerationJobDocument
    from aicbc.core.store import get_store
    from aicbc.monitoring.metrics import record_persona_generation_task

    request = json.loads(request_json)
    study_id = request["study_id"]
    count = request["count"]
    seed = request.get("seed")
    life_stages = request.get("life_stages")

    log = logger.bind(job_id=job_id, study_id=study_id, count=count)
    log.info("persona_generation_task_started")

    async def _update_status(status: str, progress: float, **fields) -> None:
        doc = await PersonaGenerationJobDocument.find_one(
            PersonaGenerationJobDocument.job_id == job_id
        )
        if doc is None:
            return
        doc.status = status
        doc.progress = progress
        for key, value in fields.items():
            setattr(doc, key, value)
        doc.updated_at = datetime.now(UTC)
        await doc.save()

    _run_async(_update_status("RUNNING", 0.0))

    start_time = time.perf_counter()
    try:
        agent = ConsumerGeneratorAgent()
        loop = _get_worker_loop()
        profiles, states, summary = agent.generate_batch_on_loop(
            loop=loop,
            study_id=study_id,
            count=count,
            life_stages=life_stages,
            seed=seed,
            max_concurrency=3,
        )

        store = get_store()
        saved = 0
        for profile in profiles:
            # acsave expects async store; get_store returns sync wrapper in worker context
            if store.save(profile):
                saved += 1

        total_cost = sum(p.generation_metadata.cost_cny for p in profiles)
        elapsed = time.perf_counter() - start_time

        _run_async(
            _update_status(
                "COMPLETED",
                100.0,
                generated=saved,
                failed=summary["failed"],
                total_cost_cny=round(total_cost, 4),
                data={"summary": summary, "states": [s.model_dump(mode="json") for s in states]},
            )
        )
        record_persona_generation_task(study_id, elapsed, count)
        log.info("persona_generation_task_completed", generated=saved, elapsed=elapsed)
        return {"status": "COMPLETED", "job_id": job_id, "generated": saved}

    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        log.exception("persona_generation_task_failed")
        _run_async(
            _update_status(
                "FAILED",
                0.0,
                data={"error": f"{type(exc).__name__}: {exc}"},
            )
        )
        record_persona_generation_task(study_id, elapsed, count)
        raise
