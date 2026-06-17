"""Tests for CBC response data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aicbc.questionnaire.response_models import (
    AlternativeRecord,
    CBCRawDataset,
    ChoiceRecord,
    DatasetMetadata,
    PersonaResponse,
    SingleChoiceDetail,
)


def _make_choice_record(
    respondent_id: str = "p-001",
    choice_set_id: int = 1,
    chosen_alt: int = 0,
) -> ChoiceRecord:
    return ChoiceRecord(
        respondent_id=respondent_id,
        respondent_index=0,
        segment="测试群体",
        choice_set_id=choice_set_id,
        choice_set_index=choice_set_id - 1,
        alternatives=[
            AlternativeRecord(
                alt_index=0,
                chosen=(chosen_alt == 0),
                attributes={"price": 2999, "brand": "美的"},
            ),
            AlternativeRecord(
                alt_index=1,
                chosen=(chosen_alt == 1),
                attributes={"price": 3999, "brand": "西门子"},
            ),
        ],
        none_chosen=False,
    )


class TestAlternativeRecord:
    """Tests for AlternativeRecord model."""

    def test_valid_record(self) -> None:
        alt = AlternativeRecord(alt_index=0, chosen=True, attributes={"price": 2999})
        assert alt.alt_index == 0
        assert alt.chosen is True

    def test_alt_index_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            AlternativeRecord(alt_index=-1, chosen=True, attributes={})


class TestChoiceRecord:
    """Tests for ChoiceRecord model."""

    def test_valid_record(self) -> None:
        record = _make_choice_record(chosen_alt=1)
        assert record.respondent_id == "p-001"
        assert record.choice_set_id == 1
        assert record.alternatives[1].chosen is True
        assert record.alternatives[0].chosen is False

    def test_none_chosen_flag(self) -> None:
        record = _make_choice_record()
        record.none_chosen = True
        assert record.none_chosen is True


class TestDatasetMetadata:
    """Tests for DatasetMetadata constraints."""

    def test_valid_metadata(self) -> None:
        meta = DatasetMetadata(
            study_id="s-1",
            n_respondents=10,
            n_choice_sets=12,
            n_alternatives=3,
        )
        assert meta.n_respondents == 10

    def test_n_respondents_must_be_non_negative(self) -> None:
        # Empty datasets are allowed (e.g. partial-failure fallback), but
        # negative respondent counts are never valid.
        with pytest.raises(ValidationError):
            DatasetMetadata(
                study_id="s-1",
                n_respondents=-1,
                n_choice_sets=12,
                n_alternatives=3,
            )

    def test_n_alternatives_minimum(self) -> None:
        with pytest.raises(ValidationError):
            DatasetMetadata(
                study_id="s-1",
                n_respondents=1,
                n_choice_sets=1,
                n_alternatives=1,
            )


class TestCBCRawDataset:
    """Tests for CBCRawDataset aggregate."""

    def test_empty_dataset(self) -> None:
        dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id="s-1",
                n_respondents=1,
                n_choice_sets=12,
                n_alternatives=3,
            )
        )
        assert dataset.n_records == 0
        assert dataset.metadata.n_respondents == 1

    def test_records_for_respondent(self) -> None:
        dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id="s-1",
                n_respondents=2,
                n_choice_sets=2,
                n_alternatives=3,
            ),
            choice_records=[
                _make_choice_record(respondent_id="p-A", choice_set_id=1),
                _make_choice_record(respondent_id="p-A", choice_set_id=2),
                _make_choice_record(respondent_id="p-B", choice_set_id=1),
            ],
        )
        assert dataset.n_records == 3
        assert len(dataset.records_for_respondent("p-A")) == 2
        assert len(dataset.records_for_respondent("p-B")) == 1
        assert len(dataset.records_for_respondent("p-C")) == 0

    def test_to_dict_serializes(self) -> None:
        dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id="s-1", n_respondents=1, n_choice_sets=1, n_alternatives=2
            ),
            choice_records=[_make_choice_record()],
        )
        d = dataset.to_dict()
        assert d["metadata"]["study_id"] == "s-1"
        assert len(d["choice_records"]) == 1


class TestPersonaResponse:
    """Tests for PersonaResponse model."""

    def test_valid_response(self) -> None:
        response = PersonaResponse(
            response_id="resp-p-001",
            study_id="s-1",
            persona_id="p-001",
            questionnaire_id="q-1",
            responses=[
                SingleChoiceDetail(choice_set_id=1, chosen_alt_index=0),
                SingleChoiceDetail(choice_set_id=2, chosen_alt_index=1),
            ],
            completion_status="COMPLETED",
        )
        assert response.completion_status == "COMPLETED"
        assert len(response.responses) == 2

    def test_invalid_completion_status(self) -> None:
        with pytest.raises(ValidationError):
            PersonaResponse(
                response_id="resp-p-001",
                study_id="s-1",
                persona_id="p-001",
                questionnaire_id="q-1",
                completion_status="DONE",  # invalid
            )

    def test_authenticity_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            PersonaResponse(
                response_id="resp-p-001",
                study_id="s-1",
                persona_id="p-001",
                questionnaire_id="q-1",
                authenticity_score=15,
            )
