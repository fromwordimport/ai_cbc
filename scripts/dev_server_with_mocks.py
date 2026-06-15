"""Development server with mocked LLM for endpoint verification.

This script creates a minimal FastAPI app with only the personas and health
routes, bypassing the full ``aicbc.main`` import chain.  On Windows the full
import chain pulls in ``pandas`` and ``prometheus_client`` which currently
crash the Python process on import (likely a C-extension / DLL issue), so
starting from the lean app avoids those broken dependencies for local dev.
"""

import json
import os
import re
import sys
from typing import Any
from unittest.mock import MagicMock

# Add project src/ to Python path so 'aicbc' imports work when running
# this script directly from the scripts/ directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware

from aicbc.api.dependencies import (
    get_authenticity_scorer,
    get_bias_auditor,
    get_llm_client,
    get_logic_validator,
    get_profile_generator,
    get_schema_validator,
    get_seed_generator,
)
from aicbc.api.routes import personas
from aicbc.core.store import get_store
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.llm.client import LLMResponse, Provider
from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    PersonaProfile,
    TensionCombination,
)

# Build minimal FastAPI app (skip analysis / monitoring middleware that pull
# in broken Windows dependencies)
app = FastAPI(
    title="AI_CBC Dev API",
    description="Minimal dev server with mocked LLM",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register health endpoint directly (avoid health_router which also registers /cost-status)
@app.get("/api/v1/health")
async def health_check():
    from datetime import datetime, timezone
    return {
        "status": "healthy",
        "version": "0.1.0",
        "environment": "development",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

app.include_router(personas.router, prefix="/api/v1", tags=["Personas"])


# ---------------------------------------------------------------------------
# Mock /api/v1/cost-status endpoint for Settings page
# ---------------------------------------------------------------------------
@app.get("/api/v1/cost-status")
async def cost_status():
    return {
        "fuse_status": "NORMAL",
        "total_cost_cny": 12.50,
        "daily_cost_cny": 3.20,
        "daily_budget_cny": 50.0,
        "warning": False,
    }


# ---------------------------------------------------------------------------
# Admin Settings
# ---------------------------------------------------------------------------
@app.get("/api/v1/admin/settings")
async def get_admin_settings():
    return _MOCK_ADMIN_SETTINGS


@app.put("/api/v1/admin/settings")
async def update_admin_settings(request: dict[str, Any]):
    _MOCK_ADMIN_SETTINGS.update(request)
    return _MOCK_ADMIN_SETTINGS


# ---------------------------------------------------------------------------
# Mock study endpoints for Dashboard and other pages
# ---------------------------------------------------------------------------

_MOCK_STUDIES: list[dict[str, Any]] = [
    {
        "study_id": "demo-study-001",
        "product_category": "洗碗机",
        "research_goal": "评估消费者对不同品牌、容量和价格档位洗碗机的偏好",
        "target_segments": ["一线城市年轻家庭", "新一线品质追求者"],
        "status": "COMPLETED",
        "n_attributes": 5,
        "n_choice_sets": 12,
        "n_alternatives": 3,
        "algorithm": "d_optimal",
        "include_none": True,
        "created_at": "2026-06-10T10:00:00Z",
        "attributes": [
            {"id": "price", "name": "价格", "type": "price", "description": None,
             "levels": [{"value": "1999", "label": "1999元", "description": None},
                         {"value": "3999", "label": "3999元", "description": None},
                         {"value": "5999", "label": "5999元", "description": None},
                         {"value": "8999", "label": "8999元", "description": None}]},
            {"id": "brand", "name": "品牌", "type": "categorical", "description": None,
             "levels": [{"value": "brand_1", "label": "华菱", "description": None},
                         {"value": "brand_2", "label": "美的", "description": None},
                         {"value": "brand_3", "label": "方太", "description": None},
                         {"value": "brand_4", "label": "西门子", "description": None}]},
            {"id": "capacity", "name": "容量", "type": "categorical", "description": None,
             "levels": [{"value": "capacity_1", "label": "8套", "description": None},
                         {"value": "capacity_2", "label": "14套", "description": None},
                         {"value": "capacity_3", "label": "18套", "description": None},
                         {"value": "capacity_4", "label": "24套", "description": None}]},
            {"id": "energy", "name": "能效等级", "type": "categorical", "description": None,
             "levels": [{"value": "energy_1", "label": "一级", "description": None},
                         {"value": "energy_2", "label": "二级", "description": None},
                         {"value": "energy_3", "label": "三级", "description": None}]},
            {"id": "spray_arm", "name": "喷淋臂类型", "type": "categorical", "description": None,
             "levels": [{"value": "spray_arm_1", "label": "上下双层", "description": None},
                         {"value": "spray_arm_2", "label": "三层", "description": None},
                         {"value": "spray_arm_3", "label": "多向旋喷", "description": None}]},
            {"id": "installation", "name": "安装方式", "type": "categorical", "description": None,
             "levels": [{"value": "installation_1", "label": "嵌入式", "description": None},
                         {"value": "installation_2", "label": "独立式", "description": None},
                         {"value": "installation_3", "label": "台式", "description": None},
                         {"value": "installation_4", "label": "水槽式", "description": None}]},
            {"id": "drying", "name": "烘干方式", "type": "categorical", "description": None,
             "levels": [{"value": "drying_1", "label": "余热", "description": None},
                         {"value": "drying_2", "label": "热交换", "description": None},
                         {"value": "drying_3", "label": "热风", "description": None},
                         {"value": "drying_4", "label": "晶蕾", "description": None}]},
        ],
        "prohibited_pairs": [
            {"conditions": [{"attribute_id": "capacity", "level_value": "capacity_1"}, {"attribute_id": "installation", "level_value": "installation_1"}]},
            {"conditions": [{"attribute_id": "price", "level_value": "1999"}, {"attribute_id": "drying", "level_value": "drying_4"}]},
            {"conditions": [{"attribute_id": "price", "level_value": "1999"}, {"attribute_id": "spray_arm", "level_value": "spray_arm_3"}]},
            {"conditions": [{"attribute_id": "installation", "level_value": "installation_4"}, {"attribute_id": "capacity", "level_value": "capacity_4"}]}
        ],
    },
    {
        "study_id": "demo-study-002",
        "product_category": "扫地机器人",
        "research_goal": "新产品线定价策略调研",
        "target_segments": ["年轻白领", "宠物家庭"],
        "status": "READY",
        "n_attributes": 4,
        "n_choice_sets": 8,
        "n_alternatives": 3,
        "algorithm": "orthogonal",
        "include_none": False,
        "created_at": "2026-06-12T08:30:00Z",
        "attributes": [
            {"id": "brand", "name": "品牌", "type": "categorical", "description": None,
             "levels": [{"value": "brand_1", "label": "品牌A", "description": None},
                         {"value": "brand_2", "label": "品牌B", "description": None}]},
            {"id": "suction", "name": "吸力", "type": "categorical", "description": None,
             "levels": [{"value": "suction_1", "label": "2000Pa", "description": None},
                         {"value": "suction_2", "label": "4000Pa", "description": None},
                         {"value": "suction_3", "label": "6000Pa", "description": None}]},
            {"id": "navigation", "name": "导航", "type": "categorical", "description": None,
             "levels": [{"value": "navigation_1", "label": "随机", "description": None},
                         {"value": "navigation_2", "label": "激光", "description": None},
                         {"value": "navigation_3", "label": "视觉", "description": None}]},
            {"id": "price", "name": "价格", "type": "price", "description": None,
             "levels": [{"value": "1999", "label": "1999元", "description": None},
                         {"value": "2999", "label": "2999元", "description": None},
                         {"value": "3999", "label": "3999元", "description": None}]},
        ],
    },
]

_MOCK_ADMIN_SETTINGS: dict[str, Any] = {
    "llm": {
        "model_provider": "Anthropic",
        "model_name": "claude-sonnet-4-6",
        "temperature": 0.3,
        "max_tokens": 4096,
    },
    "cost_budget_daily": 1000.0,
    "cost_budget_monthly": 20000.0,
}


@app.get("/api/v1/studies")
async def list_studies(page: int = 1, page_size: int = 20):
    total = len(_MOCK_STUDIES)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "studies": _MOCK_STUDIES[start:end],
    }


@app.get("/api/v1/studies/{study_id}")
async def get_study(study_id: str):
    for s in _MOCK_STUDIES:
        if s["study_id"] == study_id:
            return s
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": f"Study '{study_id}' not found"})


# ---------------------------------------------------------------------------
# Mock questionnaire endpoint
# ---------------------------------------------------------------------------

def _get_study_attributes(study_id: str) -> list[dict[str, Any]]:
    """Get attributes for a study, falling back to default dishwasher attributes."""
    for s in _MOCK_STUDIES:
        if s["study_id"] == study_id:
            return s.get("attributes", _DEFAULT_ATTRIBUTES)
    return _DEFAULT_ATTRIBUTES


_DEFAULT_ATTRIBUTES = [
    {"id": "price", "name": "价格", "type": "price", "description": None,
     "levels": [{"value": "1999", "label": "1999元", "description": None},
                 {"value": "3999", "label": "3999元", "description": None},
                 {"value": "5999", "label": "5999元", "description": None},
                 {"value": "8999", "label": "8999元", "description": None}]},
    {"id": "brand", "name": "品牌", "type": "categorical", "description": None,
     "levels": [{"value": "brand_1", "label": "华菱", "description": None},
                 {"value": "brand_2", "label": "美的", "description": None},
                 {"value": "brand_3", "label": "方太", "description": None},
                 {"value": "brand_4", "label": "西门子", "description": None}]},
    {"id": "capacity", "name": "容量", "type": "categorical", "description": None,
     "levels": [{"value": "capacity_1", "label": "8套", "description": None},
                 {"value": "capacity_2", "label": "14套", "description": None},
                 {"value": "capacity_3", "label": "18套", "description": None},
                 {"value": "capacity_4", "label": "24套", "description": None}]},
    {"id": "energy", "name": "能效等级", "type": "categorical", "description": None,
     "levels": [{"value": "energy_1", "label": "一级", "description": None},
                 {"value": "energy_2", "label": "二级", "description": None},
                 {"value": "energy_3", "label": "三级", "description": None}]},
    {"id": "spray_arm", "name": "喷淋臂类型", "type": "categorical", "description": None,
     "levels": [{"value": "spray_arm_1", "label": "上下双层", "description": None},
                 {"value": "spray_arm_2", "label": "三层", "description": None},
                 {"value": "spray_arm_3", "label": "多向旋喷", "description": None}]},
    {"id": "installation", "name": "安装方式", "type": "categorical", "description": None,
     "levels": [{"value": "installation_1", "label": "嵌入式", "description": None},
                 {"value": "installation_2", "label": "独立式", "description": None},
                 {"value": "installation_3", "label": "台式", "description": None},
                 {"value": "installation_4", "label": "水槽式", "description": None}]},
    {"id": "drying", "name": "烘干方式", "type": "categorical", "description": None,
     "levels": [{"value": "drying_1", "label": "余热", "description": None},
                 {"value": "drying_2", "label": "热交换", "description": None},
                 {"value": "drying_3", "label": "热风", "description": None},
                 {"value": "drying_4", "label": "晶蕾", "description": None}]},
]


_MOCK_ATTRIBUTES = _DEFAULT_ATTRIBUTES  # Keep for backward compatibility


def _build_mock_questionnaire(study_id: str) -> dict[str, Any]:
    import random
    rng = random.Random(hash(study_id) % (2**31))
    attrs = _get_study_attributes(study_id)
    choice_sets = []
    for s in range(12):
        alts = []
        for a in range(3):
            attrs_dict: dict[str, Any] = {}
            for attr in attrs:
                # New format: levels is [{value, label}, ...]
                levels = attr.get("levels", [])
                if levels and isinstance(levels[0], dict):
                    level = rng.choice(levels)
                    attrs_dict[attr.get("id", attr["name"])] = level["value"]
                else:
                    # Fallback for old format string levels
                    attrs_dict[attr.get("id", attr["name"])] = rng.choice(levels)
            alts.append({"alt_id": a + 1, "attributes": attrs_dict})
        choice_sets.append({"set_id": s + 1, "alternatives": alts})
    return {
        "study_id": study_id,
        "choice_sets": choice_sets,
        "design_params": {
            "algorithm": "d_optimal",
            "d_efficiency": round(rng.uniform(0.85, 0.98), 4),
            "n_attributes": len(attrs),
            "n_choice_sets": 12,
            "n_alternatives": 3,
            "include_none": True,
        },
        "created_at": "2026-06-12T10:00:00Z",
    }


@app.get("/api/v1/studies/{study_id}/questionnaire")
async def get_questionnaire(study_id: str):
    return _build_mock_questionnaire(study_id)


# ---------------------------------------------------------------------------
# Mock questionnaire generation — POST /studies/{study_id}/generate
# ---------------------------------------------------------------------------


@app.post("/api/v1/studies/{study_id}/generate")
async def generate_questionnaire(study_id: str):
    """Mock questionnaire generation — returns design stats with D-efficiency."""
    import random
    rng = random.Random(hash(study_id) % (2**31))
    d_eff = round(rng.uniform(0.88, 0.97), 4)
    quality_msg = "优秀" if d_eff >= 0.93 else "良好"
    attrs = _get_study_attributes(study_id)
    return {
        "study_id": study_id,
        "status": "COMPLETED",
        "d_efficiency": d_eff,
        "algorithm": "d_optimal",
        "n_attributes": len(attrs),
        "n_choice_sets": 12,
        "n_alternatives": 3,
        "include_none": True,
        "message": f"问卷生成完成，D效率={d_eff}，设计质量{quality_msg}。",
    }


# ---------------------------------------------------------------------------
# Mock response simulation — POST /studies/{study_id}/simulate-responses
# ---------------------------------------------------------------------------


@app.post("/api/v1/studies/{study_id}/simulate-responses")
async def simulate_responses(study_id: str, request: Request):
    """Mock virtual-consumer response simulation."""
    body = await request.json()
    persona_ids: list[str] = body.get("persona_ids", [])
    mode = body.get("mode", "stochastic")
    summaries: list[dict[str, Any]] = []
    for pid in persona_ids:
        summaries.append({
            "persona_id": pid,
            "simulated": True,
            "n_choice_sets_answered": 12,
        })
    return {
        "study_id": study_id,
        "questionnaire_id": f"q-{study_id}-001",
        "simulated": len(persona_ids),
        "failed": 0,
        "summaries": summaries,
    }


# ---------------------------------------------------------------------------
# Mock dataset export — GET /studies/{study_id}/responses/export
# ---------------------------------------------------------------------------


@app.get("/api/v1/studies/{study_id}/responses/export")
async def export_dataset(study_id: str):
    """Mock raw CBC dataset export with synthetic choice records."""
    import random
    rng = random.Random(hash(study_id) % (2**31))
    n_respondents = 3
    n_choice_sets = 12
    choice_records: list[dict[str, Any]] = []
    for resp_idx in range(n_respondents):
        for set_idx in range(n_choice_sets):
            choice_records.append({
                "record_id": f"rec-{resp_idx * n_choice_sets + set_idx + 1:04d}",
                "respondent_id": f"p-{resp_idx + 1:03d}",
                "set_id": set_idx + 1,
                "chosen": rng.randint(1, 4),  # 1-3 = alt, 4 = none
                "response_time_ms": rng.randint(2000, 15000),
            })
    return {
        "study_id": study_id,
        "n_respondents": n_respondents,
        "n_choice_sets": n_choice_sets,
        "n_alternatives": 3,
        "n_total_records": len(choice_records),
        "choice_records": choice_records,
    }


# ---------------------------------------------------------------------------
# Mock analysis endpoint — returns a completed AnalysisJobStatus
# ---------------------------------------------------------------------------

_MOCK_ANALYSIS_JOBS: dict[str, dict[str, Any]] = {}


@app.post("/api/v1/studies/{study_id}/analyze")
async def analyze_study(study_id: str, request: dict[str, Any] | None = None):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    analysis_id = f"ar-{study_id}-001"
    job = {
        "analysis_id": analysis_id,
        "study_id": study_id,
        "status": "COMPLETED",
        "model_type": (request or {}).get("model_type", "hb"),
        "queued_at": now,
        "started_at": now,
        "completed_at": now,
        "estimated_duration_seconds": 2,
        "progress_percent": 100,
    }
    _MOCK_ANALYSIS_JOBS[analysis_id] = job
    return job


@app.get("/api/v1/studies/{study_id}/analysis/{analysis_id}")
async def get_analysis_result(study_id: str, analysis_id: str):
    return {
        "analysis_id": analysis_id,
        "study_id": study_id,
        "status": "COMPLETED",
        "model_type": "hb",
        "convergence": {
            "rhat_max": 1.003,
            "rhat_by_param": {"brand_0": 1.001, "brand_1": 1.003, "capacity_0": 1.002, "price": 1.001},
            "ess_bulk_min": 1250,
            "ess_tail_min": 980,
            "ess_by_param": {"brand_0": 1200, "brand_1": 1100, "capacity_0": 950, "price": 1300},
            "converged": True,
            "reliable_ess": True,
            "divergences": 0,
            "tree_depth_max": 8,
        },
        "population_params": {
            "mu": {"brand_0": -0.12, "brand_1": 0.35, "capacity_0": 0.28, "capacity_1": 0.15, "price": -0.42},
            "sigma": {"brand_0": 0.45, "brand_1": 0.38, "capacity_0": 0.52, "capacity_1": 0.41, "price": 0.33},
        },
        "individual_utilities": {},
        "importance": {"品牌": 32.5, "容量": 24.3, "安装方式": 18.7, "能效等级": 14.2, "价格": 10.3},
        "wtp": {
            "wtp_values": {
                "品牌": {
                    "comparisons": [
                        {"from_level": "品牌A", "to_level": "品牌B", "wtp_mean": 850, "wtp_median": 820, "wtp_std": 200, "ci_95_lower": 500, "ci_95_upper": 1200, "n_valid": 150},
                        {"from_level": "品牌A", "to_level": "品牌C", "wtp_mean": 1200, "wtp_median": 1150, "wtp_std": 300, "ci_95_lower": 700, "ci_95_upper": 1700, "n_valid": 150},
                    ]
                },
                "容量": {
                    "comparisons": [
                        {"from_level": "8套", "to_level": "13套", "wtp_mean": 600, "wtp_median": 580, "wtp_std": 150, "ci_95_lower": 350, "ci_95_upper": 850, "n_valid": 150},
                        {"from_level": "8套", "to_level": "16套", "wtp_mean": 1100, "wtp_median": 1050, "wtp_std": 250, "ci_95_lower": 700, "ci_95_upper": 1500, "n_valid": 150},
                    ]
                },
            },
            "price_coefficient_summary": {
                "mean": -0.42, "median": -0.41, "std": 0.33,
                "negative_rate": 0.95, "n_positive_outliers": 2,
            },
        },
        "processing_time_seconds": 1.8,
        "completed_at": "2026-06-12T12:00:00Z",
    }


@app.get("/api/v1/studies/{study_id}/analysis/{analysis_id}/importance")
async def get_importance(study_id: str, analysis_id: str):
    return {
        "overall": {
            "品牌": {"mean": 32.5, "std": 5.2, "ci_95_lower": 28.1, "ci_95_upper": 36.9},
            "容量": {"mean": 24.3, "std": 4.8, "ci_95_lower": 20.5, "ci_95_upper": 28.1},
            "安装方式": {"mean": 18.7, "std": 4.1, "ci_95_lower": 15.4, "ci_95_upper": 22.0},
            "能效等级": {"mean": 14.2, "std": 3.5, "ci_95_lower": 11.5, "ci_95_upper": 16.9},
            "价格": {"mean": 10.3, "std": 2.9, "ci_95_lower": 8.0, "ci_95_upper": 12.6},
        }
    }


@app.get("/api/v1/studies/{study_id}/analysis/{analysis_id}/convergence")
async def get_convergence(study_id: str, analysis_id: str):
    return {
        "rhat_max": 1.003,
        "rhat_by_param": {"brand_0": 1.001, "brand_1": 1.003, "capacity_0": 1.002, "price": 1.001},
        "ess_bulk_min": 1250,
        "ess_tail_min": 980,
        "ess_by_param": {"brand_0": 1200, "brand_1": 1100, "capacity_0": 950, "price": 1300},
        "converged": True,
        "reliable_ess": True,
        "divergences": 0,
        "tree_depth_max": 8,
    }


@app.get("/api/v1/studies/{study_id}/analysis/{analysis_id}/wtp")
async def get_wtp(study_id: str, analysis_id: str):
    return {
        "wtp_values": {
            "品牌": {
                "comparisons": [
                    {"from_level": "品牌A", "to_level": "品牌B", "wtp_mean": 850, "wtp_median": 820, "wtp_std": 200, "ci_95_lower": 500, "ci_95_upper": 1200, "n_valid": 150},
                    {"from_level": "品牌A", "to_level": "品牌C", "wtp_mean": 1200, "wtp_median": 1150, "wtp_std": 300, "ci_95_lower": 700, "ci_95_upper": 1700, "n_valid": 150},
                ]
            },
            "容量": {
                "comparisons": [
                    {"from_level": "8套", "to_level": "13套", "wtp_mean": 600, "wtp_median": 580, "wtp_std": 150, "ci_95_lower": 350, "ci_95_upper": 850, "n_valid": 150},
                    {"from_level": "8套", "to_level": "16套", "wtp_mean": 1100, "wtp_median": 1050, "wtp_std": 250, "ci_95_lower": 700, "ci_95_upper": 1500, "n_valid": 150},
                ]
            },
        },
        "price_coefficient_summary": {
            "mean": -0.42, "median": -0.41, "std": 0.33,
            "negative_rate": 0.95, "n_positive_outliers": 2,
        },
    }


@app.get("/api/v1/studies/{study_id}/analysis/{analysis_id}/status")
async def get_analysis_status(study_id: str, analysis_id: str):
    return {
        "analysis_id": analysis_id,
        "study_id": study_id,
        "status": "COMPLETED",
        "model_type": "hb",
        "queued_at": "2026-06-12T11:00:00Z",
        "started_at": "2026-06-12T11:00:01Z",
        "completed_at": "2026-06-12T11:02:00Z",
        "estimated_duration_seconds": 120,
        "progress_percent": 100,
    }


# ---------------------------------------------------------------------------
# Mock market simulation — POST /studies/{study_id}/analysis/{analysis_id}/simulate-market
# ---------------------------------------------------------------------------


@app.post("/api/v1/studies/{study_id}/analysis/{analysis_id}/simulate-market")
async def simulate_market(study_id: str, analysis_id: str, request: Request):
    """Mock market simulation — predicts share-of-choice for product scenarios."""
    import random
    body = await request.json()
    rng = random.Random(hash(study_id + analysis_id + json.dumps(body, sort_keys=True)) % (2**31))
    scenarios: list[dict[str, Any]] = body.get("scenarios", [])
    if not scenarios:
        return {"scenarios": []}

    n = len(scenarios)
    raw_shares = [rng.uniform(15, 45) for _ in range(n)]
    total = sum(raw_shares)
    shares: list[dict[str, Any]] = []
    for i, sc in enumerate(scenarios):
        share = round(raw_shares[i] / total * 100, 1)
        ci_half = round(rng.uniform(2.0, 6.0), 1)
        shares.append({
            "name": sc.get("name", f"场景{i + 1}"),
            "predicted_share": share,
            "share_ci_95_lower": round(max(0.0, share - ci_half), 1),
            "share_ci_95_upper": round(min(100.0, share + ci_half), 1),
        })

    # Normalise so shares sum to exactly 100%
    total_shares = sum(s["predicted_share"] for s in shares)
    if total_shares > 0:
        adj = 100.0 / total_shares
        for s in shares:
            s["predicted_share"] = round(s["predicted_share"] * adj, 1)

    result: dict[str, Any] = {"scenarios": shares}

    # Optional by-segment breakdown
    segment_filter = body.get("segment_filter")
    if segment_filter:
        segments = [segment_filter] if isinstance(segment_filter, str) else segment_filter
    else:
        segments = ["一线城市年轻家庭", "新一线品质追求者"]
    by_segment: dict[str, list[dict[str, Any]]] = {}
    for seg in segments:
        seg_raw = [rng.uniform(10, 50) for _ in range(n)]
        seg_total = sum(seg_raw)
        seg_shares: list[dict[str, Any]] = []
        for i, sc in enumerate(scenarios):
            seg_share = round(seg_raw[i] / seg_total * 100, 1)
            seg_ci = round(rng.uniform(2.5, 7.0), 1)
            seg_shares.append({
                "name": sc.get("name", f"场景{i + 1}"),
                "predicted_share": seg_share,
                "share_ci_95_lower": round(max(0.0, seg_share - seg_ci), 1),
                "share_ci_95_upper": round(min(100.0, seg_share + seg_ci), 1),
            })
        by_segment[seg] = seg_shares
    result["by_segment"] = by_segment
    return result


# ---------------------------------------------------------------------------
# Mock segment comparison — GET /studies/{study_id}/analysis/{analysis_id}/segment-comparison
# ---------------------------------------------------------------------------


@app.get("/api/v1/studies/{study_id}/analysis/{analysis_id}/segment-comparison")
async def get_segment_comparison(
    study_id: str,
    analysis_id: str,
    segment_a: str = "",
    segment_b: str = "",
):
    """Mock inter-segment statistical comparison across attributes."""
    import random
    rng = random.Random(hash(study_id + analysis_id + segment_a + segment_b) % (2**31))

    attributes = ["品牌", "容量", "安装方式", "能效等级", "价格"]
    per_attribute: list[dict[str, Any]] = []
    for attr in attributes:
        t_stat = round(rng.uniform(-3.5, 3.5), 3)
        p_val = round(rng.uniform(0.001, 0.15), 4)
        significant = p_val < 0.05
        cohens_d = round(abs(t_stat) / rng.uniform(2.0, 4.0), 3)
        per_attribute.append({
            "attribute": attr,
            "method": "independent_t_test",
            "t_statistic": t_stat,
            "p_value": p_val,
            "corrected_p_value": None,
            "significant": significant,
            "cohens_d": cohens_d,
            "mean_a": round(rng.uniform(20, 40), 2),
            "mean_b": round(rng.uniform(15, 35), 2),
            "ci_95_lower": round(-cohens_d * 1.5, 3),
            "ci_95_upper": round(cohens_d * 1.5, 3),
        })

    return {
        "segment_a": segment_a or "一线城市年轻家庭",
        "segment_b": segment_b or "新一线品质追求者",
        "n_a": 75,
        "n_b": 75,
        "overall_test": {
            "method": "Hotelling_T2",
            "statistic": round(rng.uniform(5.0, 15.0), 2),
            "p_value": round(rng.uniform(0.001, 0.05), 4),
            "significant": True,
        },
        "per_attribute": per_attribute,
        "interpretation": "两组在品牌和价格属性上存在显著差异，一线城市年轻家庭更重视品牌溢价，新一线品质追求者更关注性价比。",
    }


@app.post("/api/v1/studies")
async def create_study(request: Request):
    from datetime import datetime, timezone
    body = await request.json()
    raw_id = body.get("study_id", f"study-{len(_MOCK_STUDIES) + 1:03d}")
    existing_ids = {s["study_id"] for s in _MOCK_STUDIES}
    study_id = raw_id
    counter = 1
    while study_id in existing_ids:
        study_id = f"{raw_id}-{counter}"
        counter += 1

    # Support custom attributes; fallback to default dishwasher attributes
    custom_attrs = body.get("attributes")
    attrs = custom_attrs if custom_attrs else _DEFAULT_ATTRIBUTES

    new_study = {
        "study_id": study_id,
        "product_category": body.get("product_category", "未指定"),
        "research_goal": body.get("research_goal", ""),
        "target_segments": body.get("target_segments", []),
        "status": "READY",
        "n_attributes": len(attrs),
        "n_choice_sets": 12,
        "n_alternatives": 3,
        "algorithm": "d_optimal",
        "include_none": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "attributes": attrs,
    }
    _MOCK_STUDIES.append(new_study)
    return new_study


@app.delete("/api/v1/studies/{study_id}", status_code=204)
async def delete_study(study_id: str):
    """Delete a study and its associated data from the mock store."""
    from fastapi.responses import JSONResponse
    for i, s in enumerate(_MOCK_STUDIES):
        if s["study_id"] == study_id:
            del _MOCK_STUDIES[i]
            return None  # 204 No Content
    return JSONResponse(status_code=404, content={"detail": f"Study '{study_id}' not found"})


# ---------------------------------------------------------------------------
# Study attribute design endpoints — GET / PUT /studies/{study_id}/design
# ---------------------------------------------------------------------------

@app.get("/api/v1/studies/{study_id}/design")
async def get_study_design(study_id: str):
    """Return the attribute-and-level design for a study."""
    for s in _MOCK_STUDIES:
        if s["study_id"] == study_id:
            return {
                "study_id": study_id,
                "attributes": s.get("attributes", _DEFAULT_ATTRIBUTES),
                "prohibited_pairs": s.get("prohibited_pairs", []),
                "n_attributes": s.get("n_attributes", len(s.get("attributes", _DEFAULT_ATTRIBUTES))),
            }
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": f"Study '{study_id}' not found"})


@app.put("/api/v1/studies/{study_id}/design")
async def update_study_design(study_id: str, request: Request):
    """Update the attribute-and-level design for a study."""
    from fastapi.responses import JSONResponse
    body = await request.json()
    new_attrs = body.get("attributes")
    if not new_attrs or not isinstance(new_attrs, list):
        return JSONResponse(status_code=422, content={"detail": "'attributes' must be a non-empty list"})

    raw_pairs = body.get("prohibited_pairs", [])
    if not isinstance(raw_pairs, list):
        return JSONResponse(status_code=422, content={"detail": "'prohibited_pairs' must be a list"})

    # Build validation maps from new attributes
    valid_attr_ids = {attr.get("id") for attr in new_attrs if attr.get("id")}
    valid_levels: dict[str, set] = {}
    for attr in new_attrs:
        attr_id = attr.get("id")
        if attr_id:
            levels = attr.get("levels", [])
            valid_levels[attr_id] = {lv.get("value") for lv in levels if isinstance(lv, dict)}

    for pair in raw_pairs:
        conditions = pair.get("conditions", [])
        if len(conditions) < 2:
            return JSONResponse(status_code=400, content={"detail": "each prohibited pair must contain at least 2 conditions"})
        pair_attr_ids = [c.get("attribute_id") for c in conditions]
        if len(pair_attr_ids) != len(set(pair_attr_ids)):
            return JSONResponse(status_code=400, content={"detail": "duplicate attribute_ids are not allowed within a prohibited pair"})
        for cond in conditions:
            attr_id = cond.get("attribute_id")
            level_value = cond.get("level_value")
            if attr_id not in valid_attr_ids:
                return JSONResponse(status_code=400, content={"detail": f"attribute_id '{attr_id}' in prohibited pair does not exist"})
            if level_value not in valid_levels.get(attr_id, set()):
                return JSONResponse(status_code=400, content={"detail": f"level_value '{level_value}' for attribute '{attr_id}' in prohibited pair is invalid"})

    for i, s in enumerate(_MOCK_STUDIES):
        if s["study_id"] == study_id:
            s["attributes"] = new_attrs
            s["n_attributes"] = len(new_attrs)
            s["prohibited_pairs"] = raw_pairs
            return {
                "study_id": study_id,
                "attributes": new_attrs,
                "prohibited_pairs": raw_pairs,
                "n_attributes": len(new_attrs),
            }
    return JSONResponse(status_code=404, content={"detail": f"Study '{study_id}' not found"})


# ---------------------------------------------------------------------------
# Mock persona converse — POST /personas/{persona_id}/converse
# ---------------------------------------------------------------------------


@app.post("/api/v1/personas/{persona_id}/converse")
async def converse(persona_id: str, request: Request):
    import random
    body = await request.json()
    question: str = body.get("question", "")
    rng = random.Random(hash(persona_id + question) % (2**31))

    # Map question topics to curated answer pools
    question_lower = question.lower()
    if any(kw in question_lower for kw in ["购买", "洗碗机", "考虑", "为啥", "纠结"]):
        pool = [
            "我买洗碗机主要是因为实在受不了每天洗碗了。我和我老公都上班，晚上回家还要做饭洗碗，真的很累。有了洗碗机以后，每天至少省出半小时。",
            "说实话我纠结了很久。厨房就那么点大，放个洗碗机挺占地方的。但是后来算了一笔账，每天洗碗至少半小时，一年就是180个小时，这个时间成本太高了。",
            "品牌嘛，我比较看重口碑。一开始只知道西门子，后来在什么值得买上看了很多横评，发现国产的美的、海尔也不错，性价比高很多。",
            "我觉得最重要的是清洁效果，要是洗不干净还不如手洗。其次是容量，建议能买大的就买大的，锅也能放进去洗。",
        ]
    elif any(kw in question_lower for kw in ["价格", "预算", "贵", "便宜", "多少钱", "花费"]):
        pool = [
            "预算的话，我觉得4000到6000之间比较合适。太便宜的洗不干净，太贵的溢价太高。我之前看中的那款是4999的，双11估计能降到3999。",
            "我的预算控制在5000以内。说实话洗碗机这种东西，多花一两千买个好的值得，毕竟要用好几年呢。",
        ]
    elif any(kw in question_lower for kw in ["安装", "厨房", "空间", "尺寸", "大小"]):
        pool = [
            "我家厨房不大，大概6平米。装修的时候没留洗碗机的位置，现在只能买独立式的放在旁边。安装师傅说可以接三通从水槽下面走水管。",
            "安装其实不复杂，关键是提前确认好尺寸和水电位置。我买的13套的，深度要600mm，提前量好了才下单的。",
        ]
    elif any(kw in question_lower for kw in ["能效", "耗电", "耗水", "节能", "电费"]):
        pool = [
            "能效我肯定选一级的，虽然贵一点但长期省下来的水电费早就回本了。而且一级能效的烘干效果也好很多。",
            "我对比过，一级能效每次大概用0.8度电、10升水，算下来一次不到5毛钱，比手洗还省水呢。",
        ]
    elif any(kw in question_lower for kw in ["品牌", "型号", "哪个好", "推荐"]):
        pool = [
            "我对比了西门子、美的和海尔三个品牌。西门子品质好但溢价太高，美的性价比最高售后网点也多，海尔烘干稍微弱一点。最后我倾向美的。",
            "品牌方面我做过不少功课。个人觉得没必要非要进口的，现在国产品牌技术差距不大了。关键是看具体型号的评测，有些所谓大牌的低端款还不如国产中端款。",
        ]
    else:
        pool = [
            "这个问题挺有意思的。我觉得买洗碗机这件事，关键还是看自己的生活习惯和厨房条件。如果家里人口多又经常做饭，那绝对值得。",
            "嗯，怎么说呢，我觉得洗碗机是那种'买了就后悔没早买'的东西。身边朋友几乎都这么说。",
            "每个人情况不一样吧。我同事家买了基本闲置，因为他们基本不做饭。但像我们这样天天做饭的家庭，洗碗机是刚需。",
        ]

    answer = rng.choice(pool)
    emotions = ["满意", "纠结", "兴奋", "理性", "犹豫", "坚定"]
    emotion = rng.choice(emotions)

    return {
        "persona_id": persona_id,
        "turn_number": rng.randint(1, 5),
        "researcher_question": question,
        "consumer_response": answer,
        "emotion_tag": emotion,
        "inconsistency_flag": rng.random() < 0.05,
    }


def _mock_resp(content: dict[str, Any] | str, model: str = "claude-sonnet-4-6") -> LLMResponse:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return LLMResponse(
        content=text,
        model=model,
        provider=Provider.ANTHROPIC,
        prompt_tokens=100,
        completion_tokens=200,
        total_tokens=300,
        estimated_cost_usd=0.003,
        latency_seconds=0.5,
        raw_response=None,
    )


# City/income/occupation/age pools for varied mock persona generation
_CITY_VARIANTS: list[str] = [
    "一线城市", "新一线城市", "二线城市", "三线城市", "四线城市",
    "五线城市", "县城", "农村",
]
_INCOME_VARIANTS: list[str] = [
    "3万元以下", "3-8万元", "8-15万元", "15-30万元", "30-50万元",
    "50-100万元", "100万元以上",
]
_OCCUPATION_VARIANTS: list[tuple[str, str, str]] = [
    ("互联网产品经理", "本科", "已婚无孩", "自有住房（89㎡三居室）"),
    ("小学教师", "本科", "已婚育有一子（5岁）", "自有住房（70㎡两居室）"),
    ("医学生（研二）", "硕士在读", "未婚", "合租房（15㎡次卧）"),
    ("国企退休职工", "大专", "已婚子女独立", "自有住房（105㎡三居室）"),
    ("自由职业摄影师", "本科", "未婚", "租房（40㎡开间）"),
    ("外企销售经理", "硕士", "已婚无孩", "自有住房（120㎡三居室）"),
    ("便利店店员", "高中", "未婚", "合租房（12㎡隔断间）"),
    ("建筑工地包工头", "初中", "已婚育有两子（8岁/12岁）", "自建房（乡镇）"),
]
_AGE_VARIANTS: list[str] = [
    "22岁", "26岁", "28岁", "31岁", "35岁", "42岁", "48岁", "55岁", "63岁",
]
_GENDER_VARIANTS: list[str] = ["男", "女"]

_CORE_VALUES_POOL: list[list[str]] = [
    ["效率", "品质生活", "家庭至上"],
    ["性价比为王", "健康", "稳定"],
    ["自由独立", "极简主义", "社交认同"],
    ["事业成就", "个人成长", "财富积累"],
    ["家庭幸福", "安全", "传统价值观"],
    ["创新探索", "体验至上", "自我表达"],
]
_CORE_ANXIETIES_POOL: list[list[str]] = [
    ["时间不够用", "家务分工矛盾"],
    ["育儿焦虑", "同辈压力"],
    ["35岁职业危机", "健康焦虑"],
    ["经济压力", "未来不确定性"],
    ["养老焦虑", "身份迷茫"],
    ["同辈压力", "FOMO（错失恐惧）"],
]
_TENSION_POOL: list[dict[str, Any]] = [
    {
        "labels": ["精致品质", "凑单退单高手"],
        "narrative_explanation": "她追求精致生活却总在凑单后退掉不需要的商品，源于既想享受品质又害怕浪费的深层焦虑。小时候家境普通让她对浪费极度敏感，成年后收入提升让她有能力追求品质，但童年匮乏感仍在潜意识中支配消费决策。",
    },
    {
        "labels": ["高收入", "极简主义"],
        "narrative_explanation": "年收入40万却坚持极简生活，源于童年物质匮乏的记忆。通过控制消费获得安全感，但内心深处渴望通过消费证明自我价值。这种矛盾让他在大促时疯狂囤货后又大量退货。",
    },
    {
        "labels": ["理性比价", "为情绪价值买单"],
        "narrative_explanation": "平时精打细算到每一分钱，但在情绪低谷时会冲动购买高溢价商品寻求安慰。大脑说不要、身体很诚实，每次冲动后都陷入自责和退货的循环。",
    },
    {
        "labels": ["躺平/低欲望", "内卷/奋斗"],
        "narrative_explanation": "口头禅是'差不多得了'但内心极度渴望被认可，这种45度青年的矛盾状态源于对未来的不确定感和对成功的渴望同时存在。",
    },
    {
        "labels": ["本土主义/国潮信仰", "全球化/世界公民"],
        "narrative_explanation": "对外展示国潮文化自信，私下却偏好进口商品的质量和设计。这种摇摆源于民族认同感和对更高品质生活追求之间的拉锯。",
    },
]
_SECRET_MOTIVATION_POOL: list[str] = [
    "用科技产品证明自己的生活品味，缓解同辈压力",
    "通过消费维持'好妈妈'人设，缓解育儿焦虑",
    "用'省钱'来获得掌控感，弥补工作中缺乏的自主权",
    "通过购买高端产品来弥补出身普通的自卑感",
    "购买的不是商品，是'被看见'和'被认可'",
]
_DEFENSE_MECHANISM_POOL: list[str] = [
    "合理化——把冲动消费解释为投资生活品质",
    "升华——将购物欲转化为'研究消费'的知识收集行为",
    "否认——声称不在意品牌溢价，实则深夜偷偷比价",
    "投射——批评他人消费主义，掩饰自己的购买冲动",
]


def _parse_seed_from_prompt(prompt: str) -> dict[str, str]:
    """Extract seed data from prompt text for varied mock responses.

    The prompt template uses Chinese labels in the seed section (e.g. 城市层级:)
    and English field names in previous_layers (e.g. city:).  Match both.
    """
    seed: dict[str, str] = {}
    patterns = {
        "city_tier": r"(?:城市层级|city)[：:]\s*(.+?)(?:\n|$)",
        "income_bracket": r"(?:收入档位|income)[：:]\s*(.+?)(?:\n|$)",
        "life_stage": r"(?:人生阶段|life_stage)[：:]\s*(.+?)(?:\n|$)",
        "anxieties": r"(?:核心焦虑|core_anxieties)[：:]\s*(.+?)(?:\n|$)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, prompt)
        if match:
            seed[key] = match.group(1).strip()
    return seed


def _make_l1(persona_idx: int, seed: dict[str, str]) -> dict[str, Any]:
    """Generate varied Layer 1 based on seed data or persona index."""
    city = seed.get("city_tier", _CITY_VARIANTS[persona_idx % len(_CITY_VARIANTS)])
    income = seed.get("income_bracket", _INCOME_VARIANTS[persona_idx % len(_INCOME_VARIANTS)])
    occ = _OCCUPATION_VARIANTS[persona_idx % len(_OCCUPATION_VARIANTS)]
    return {
        "age": _AGE_VARIANTS[persona_idx % len(_AGE_VARIANTS)],
        "gender": _GENDER_VARIANTS[persona_idx % len(_GENDER_VARIANTS)],
        "city": city,
        "income": income,
        "occupation": occ[0],
        "education": occ[1],
        "marital_status": occ[2],
        "living_type": occ[3],
    }


def _make_l2(persona_idx: int) -> dict[str, Any]:
    channels_pool = [
        ["京东自营", "天猫旗舰店", "山姆会员店"],
        ["拼多多", "1688", "闲鱼"],
        ["品牌官网", "线下专柜", "天猫旗舰店"],
        ["直播间", "抖音商城", "小红书"],
        ["社区团购", "美团买菜", "京东到家"],
        ["批发市场", "赶集", "小超市"],
    ]
    info_pool = [
        ["小红书", "什么值得买", "知乎", "同事推荐"],
        ["抖音", "快手", "微信群", "邻居推荐"],
        ["B站评测", "知乎", "微博热搜", "朋友圈"],
        ["线下体验", "店员推荐", "纸质传单"],
    ]
    return {
        "price_sensitivity": (
            "极度敏感，货比三家后才下单"
            if persona_idx % 3 == 0
            else "中等敏感，大件比价小件随意"
            if persona_idx % 3 == 1
            else "低敏感，方便和时间比价格更重要"
        ),
        "purchase_channels": channels_pool[persona_idx % len(channels_pool)],
        "decision_style": (
            "冲动消费型" if persona_idx % 4 == 0
            else "理性比价型" if persona_idx % 4 == 1
            else "跟风种草型" if persona_idx % 4 == 2
            else "习惯复购型"
        ),
        "brand_loyalty": (
            "低，每次换品牌尝鲜" if persona_idx % 3 == 0
            else "中等，好用的会复购"
            if persona_idx % 3 == 1
            else "高，认准品牌不轻易换"
        ),
        "information_source": info_pool[persona_idx % len(info_pool)],
    }


def _make_l3(persona_idx: int) -> dict[str, Any]:
    return {
        "core_values": _CORE_VALUES_POOL[persona_idx % len(_CORE_VALUES_POOL)],
        "core_anxieties": _CORE_ANXIETIES_POOL[persona_idx % len(_CORE_ANXIETIES_POOL)],
        "tension_combination": _TENSION_POOL[persona_idx % len(_TENSION_POOL)],
        "secret_motivation": _SECRET_MOTIVATION_POOL[persona_idx % len(_SECRET_MOTIVATION_POOL)],
        "defense_mechanism": _DEFENSE_MECHANISM_POOL[persona_idx % len(_DEFENSE_MECHANISM_POOL)],
    }


def _make_l4(persona_idx: int) -> dict[str, Any]:
    routines = [
        "早7点起床，地铁通勤40分钟，晚7点到家，周末打扫或上兴趣班",
        "早6点起床做早餐送孩子上学，上午去菜市场，下午做家务，晚饭后辅导作业",
        "早上8点起床走路去实验室，晚上10点回宿舍，周末也泡在实验室写论文",
        "早5:30起床晨练，上午去公园下棋，下午看孙子，晚饭后散步",
        "睡到自然醒，上午处理客户需求，下午外出拍摄，晚上修图到凌晨",
        "早9点打卡，经常加班到9点，回家后只想躺平刷手机，周末补觉",
    ]
    triggers = [
        "被小红书提升幸福感的小家电种草，叠加同事推荐",
        "孩子同学家长推荐，妈妈群讨论后心动",
        "合租室友买了以后强烈安利，亲眼看到效果后种草",
        "子女过年回家时建议购买，觉得有道理",
        "看到关注的UP主做了详细横评，被种草",
        "逛街时被促销员热情推荐，现场体验后心动",
    ]
    stress = [
        "焦虑时刷购物APP加购，冷静后删除，形成加购-删除循环",
        "压力大时暴饮暴食+深夜网购，收到货后有负罪感",
        "焦虑时大量搜集信息和评测，但迟迟不下单，陷入分析瘫痪",
        "用整理收纳和断舍离来对抗焦虑，购物欲反而下降",
    ]
    social = [
        "朋友圈极少发消费内容，但在私域社群活跃分享购物攻略",
        "朋友圈天天晒娃晒美食，对消费类话题保持低调",
        "社交平台活跃，经常发开箱测评，喜欢分享购物心得",
        "基本不发社交媒体，购物决策全靠自己研究不参考他人",
    ]
    return {
        "daily_routine": routines[persona_idx % len(routines)],
        "purchase_trigger": triggers[persona_idx % len(triggers)],
        "stress_response": stress[persona_idx % len(stress)],
        "social_behavior": social[persona_idx % len(social)],
    }


def _make_aux(persona_idx: int) -> dict[str, Any]:
    lang_pool = [
        # Persona 0: enthusiastic early adopter
        [
            "洗碗机真的是解放双手的神器，后悔没早买！",
            "对比了三个品牌最后还是选了性价比最高的那款，纠结了好几天说实话。",
            "安装师傅挺专业的，只用了半小时就全部搞定了，比我预想的简单多了。",
        ],
        # Persona 1: skeptical traditionalist
        [
            "说实话我不太相信这些电器，总觉得手洗才干净，可能是老一辈的观念吧。",
            "我妈说洗碗机费水费电不实用，我也拿不准到底要不要买。",
            "但是看同事家用着挺好的，又有点心动了，唉纠结。",
        ],
        # Persona 2: budget-conscious renter
        [
            "租的房子不能打孔，台式的又觉得占地方，烦死了。",
            "室友居然同意AA买洗碗机，太开心了！不过还得研究研究哪个性价比高。",
            "搬家的话还得带走，想想就头疼，但至少不用天天洗碗了。",
        ],
        # Persona 3: elderly tech adapter
        [
            "年纪大了腰不好，洗碗弯腰受不了，子女给买的，开始还挺抗拒的。",
            "刚买回来不太会用，按错了好几次，现在慢慢摸索着学会了，确实方便不少。",
            "就是按钮太多眼花缭乱的，只敢用标准模式，别的功能也不太懂。",
        ],
        # Persona 4: hardcore researcher
        [
            "看了B站十多个评测视频，参数倒背如流了属于是，但说实话大部分功能可能用不上。",
            "这个价格和功能配置，只能说懂的都懂，不懂的别乱推荐。",
            "避雷提醒，某品牌售后真的不行，亲身踩过坑，建议大家绕道。",
        ],
    ]
    dc_pool = [
        {"purchase_constraints": ["厨房空间有限", "预算控制在5000以内"], "decision_factors": ["清洁效果", "品牌口碑", "能耗等级", "安装便利性"], "ignored_factors": ["外观设计", "智能互联功能"]},
        {"purchase_constraints": ["租房不能改造", "预算2000以内"], "decision_factors": ["价格", "安装简便（免安装）", "体积小巧可带走"], "ignored_factors": ["品牌知名度", "大容量"]},
        {"purchase_constraints": ["新房装修预留位置", "预算8000以内"], "decision_factors": ["大容量（13套以上）", "除菌功能", "节能静音", "品牌售后"], "ignored_factors": ["外观颜色"]},
        {"purchase_constraints": ["厨房已装修无法嵌入式", "老人操作需简单"], "decision_factors": ["操作简单", "大字号显示", "安全童锁", "售后电话响应快"], "ignored_factors": ["智能APP功能", "时尚外观"]},
        {"purchase_constraints": ["合租共用厨房", "预算1500以内"], "decision_factors": ["免安装", "耗水量低", "噪音小"], "ignored_factors": ["品牌", "容量（4套即可）", "烘干功能"]},
    ]
    return {
        "language_samples": lang_pool[persona_idx % len(lang_pool)],
        "dishwasher_context": dc_pool[persona_idx % len(dc_pool)],
    }


# Build mock client that produces varied responses per persona
client = MagicMock()
_PERSONA_GENERATION_COUNT: dict[str, int] = {}

# Regex patterns to identify which prompt layer is being used
_re_layer_pattern = re.compile(r"Layer (\d)[：:]")
_re_aux_pattern = re.compile(r"代表性发言|语言样本.*洗碗机购买情境")


def _side_effect(*args: Any, **kwargs: Any) -> LLMResponse:
    """Mock LLM that produces varied persona data based on seed info in prompts."""
    messages = kwargs.get("messages", [])
    prompt = ""
    for msg in messages:
        if msg.get("role") == "user":
            prompt = msg.get("content", "")
            break

    # Determine persona index from seed data in prompt
    seed = _parse_seed_from_prompt(prompt)
    # Use a hash of the seed key to get consistent persona index
    seed_key = f"{seed.get('city_tier', '')}|{seed.get('income_bracket', '')}|{seed.get('life_stage', '')}"
    if seed_key not in _PERSONA_GENERATION_COUNT:
        _PERSONA_GENERATION_COUNT[seed_key] = len(_PERSONA_GENERATION_COUNT)
    persona_idx = _PERSONA_GENERATION_COUNT[seed_key]

    # Detect which layer/aux is being requested
    if _re_aux_pattern.search(prompt):
        return _mock_resp(_make_aux(persona_idx))

    layer_match = _re_layer_pattern.search(prompt)
    if layer_match:
        layer_num = int(layer_match.group(1))
        if layer_num == 1:
            return _mock_resp(_make_l1(persona_idx, seed))
        elif layer_num == 2:
            return _mock_resp(_make_l2(persona_idx))
        elif layer_num == 3:
            return _mock_resp(_make_l3(persona_idx))
        elif layer_num == 4:
            return _mock_resp(_make_l4(persona_idx))

    # Fallback: return varied L1 data
    return _mock_resp(_make_l1(persona_idx, seed))


client.generate.side_effect = _side_effect

# Override dependencies
app.dependency_overrides[get_llm_client] = lambda: client
app.dependency_overrides[get_seed_generator] = lambda: SeedGenerator(seed=42)
app.dependency_overrides[get_profile_generator] = lambda: ProfileGenerator(llm_client=client)
app.dependency_overrides[get_schema_validator] = SchemaValidator
app.dependency_overrides[get_logic_validator] = LogicValidator
app.dependency_overrides[get_store] = get_store


# Use real AuthenticityScorer for genuine score variation.
# For BiasAuditor, use a dev-friendly variant that produces varied but
# non-rejecting audit results (real auditor is too strict for mock data).
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer

_DEV_BIAS_STATUSES = ["PASSED", "PASSED", "PASSED", "PASSED", "PENDING", "PENDING", "FAILED"]


class _DevBiasAuditor:
    """Dev-mode bias auditor — returns varied statuses without rejecting personas.

    Uses the persona's content hash to deterministically assign a bias status
    (most PASSED, some PENDING, occasional FAILED for UI variety).
    Does NOT reject any persona — the real rejection logic is only needed in
    production where legal/compliance requirements apply.
    """

    def audit(self, persona: Any) -> Any:
        from dataclasses import dataclass, field

        @dataclass
        class _DevResult:
            status: str
            findings: list = field(default_factory=list)
            passed: bool = True  # Always pass in dev
            high_severity_count: int = 0
            critical_severity_count: int = 0

        # Deterministic variety based on persona_id suffix
        # Use the numeric suffix (e.g., -001, -002) to cycle through statuses
        suffix = persona.persona_id.split("-")[-1]
        try:
            idx = int(suffix) % len(_DEV_BIAS_STATUSES)
        except ValueError:
            idx = hash(persona.persona_id) % len(_DEV_BIAS_STATUSES)
        return _DevResult(status=_DEV_BIAS_STATUSES[idx])

    def audit_batch(self, personas: list[Any]) -> dict[str, Any]:
        results = [self.audit(p) for p in personas]
        n = len(results)
        passed = sum(1 for r in results if r.status == "PASSED")
        pending = sum(1 for r in results if r.status == "PENDING")
        failed = sum(1 for r in results if r.status == "FAILED")
        return {
            "total_audited": n,
            "passed": passed,
            "pending": pending,
            "failed": failed,
            "pass_rate": round(passed / n, 3) if n else 0,
            "total_findings": 0,
            "findings_by_category": {},
            "high_severity_findings": 0,
            "critical_severity_findings": 0,
        }


app.dependency_overrides[get_authenticity_scorer] = lambda: AuthenticityScorer()
app.dependency_overrides[get_bias_auditor] = lambda: _DevBiasAuditor()


# ---------------------------------------------------------------------------
# Seed demo personas so the front-end ResponseSimulator has consumers on boot
# ---------------------------------------------------------------------------


def _clamp_sample(text: str) -> str:
    """Ensure a language sample satisfies the 20-60 character validator."""
    if len(text) > 60:
        text = text[:59]
    if len(text) < 20:
        text = text + "，补充到满足长度要求。"
    return text


def _build_demo_persona(idx: int, study_id: str) -> PersonaProfile:
    """Build a valid PersonaProfile from existing mock helpers."""
    l1_data = _make_l1(idx, {})
    l2_data = _make_l2(idx)
    l3_data = _make_l3(idx)
    l4_data = _make_l4(idx)
    aux = _make_aux(idx)

    tension = l3_data["tension_combination"]
    samples = [_clamp_sample(s) for s in aux["language_samples"]]

    return PersonaProfile(
        persona_id=f"persona-{study_id}-{idx + 1:03d}",
        segment=f"{l1_data['occupation']}-{l1_data['city']}",
        layer1_demographics=Layer1Demographics(**l1_data),
        layer2_behavior=Layer2Behavior(**l2_data),
        layer3_psychology=Layer3Psychology(
            core_values=l3_data["core_values"],
            core_anxieties=l3_data["core_anxieties"],
            tension_combination=TensionCombination(**tension),
            secret_motivation=l3_data["secret_motivation"],
            defense_mechanism=l3_data["defense_mechanism"],
        ),
        layer4_scenarios=Layer4Scenarios(**l4_data),
        language_samples=samples,
        dishwasher_context=DishwasherContext(**aux["dishwasher_context"]),
        authenticity_score=float(7 + idx % 5),
        bias_audit_status=_DEV_BIAS_STATUSES[idx % len(_DEV_BIAS_STATUSES)],
        status="PUBLISHED",
        generation_metadata=GenerationMetadata(
            model="mock", version="0.1.0", seed=42 + idx, cost_cny=0.1
        ),
    )


@app.on_event("startup")
async def _seed_demo_personas() -> None:
    """Pre-populate the persona store with demo consumers."""
    store = get_store()
    study_id = "demo-study-001"
    for idx in range(5):
        persona = _build_demo_persona(idx, study_id)
        store.save(persona)


if __name__ == "__main__":
    import uvicorn

    print("Starting AI_CBC dev server with mocked LLM on http://127.0.0.1:8000")
    print("Endpoints:")
    print("  GET  /api/v1/health")
    print("  GET  /api/v1/admin/settings")
    print("  PUT  /api/v1/admin/settings")
    print("  GET  /api/v1/studies")
    print("  GET  /api/v1/studies/{id}")
    print("  POST /api/v1/studies")
    print("  GET  /api/v1/studies/{id}/questionnaire")
    print("  POST /api/v1/studies/{id}/generate")
    print("  GET  /api/v1/studies/{id}/design")
    print("  PUT  /api/v1/studies/{id}/design")
    print("  POST /api/v1/studies/{id}/simulate-responses")
    print("  GET  /api/v1/studies/{id}/responses/export")
    print("  POST /api/v1/studies/{id}/analyze")
    print("  GET  /api/v1/studies/{id}/analysis/{aid}")
    print("  GET  /api/v1/studies/{id}/analysis/{aid}/importance")
    print("  GET  /api/v1/studies/{id}/analysis/{aid}/convergence")
    print("  GET  /api/v1/studies/{id}/analysis/{aid}/wtp")
    print("  GET  /api/v1/studies/{id}/analysis/{aid}/status")
    print("  POST /api/v1/studies/{id}/analysis/{aid}/simulate-market")
    print("  GET  /api/v1/studies/{id}/analysis/{aid}/segment-comparison")
    print("  POST /api/v1/personas/generate")
    print("  GET  /api/v1/personas")
    print("  GET  /api/v1/personas/{id}")
    print("  POST /api/v1/personas/{id}/validate")
    print("  GET  /api/v1/personas/{id}/layers/{n}")
    print("  DELETE /api/v1/personas/{id}")
    print("  POST /api/v1/personas/{id}/converse")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
