"""Unit tests for the health-flag computation rule (Phase 10).

Tests every branch of the _compute_health_flag function in isolation —
no database required.

Health-flag rules (from dashboard_service.py module docstring):
  off_track : actual > planned  (including zero-budget with any spend)
  at_risk   : (not off_track) AND (high_impact_open_risk OR utilization_pct >= 80)
  on_track  : everything else
"""

from decimal import Decimal

import pytest

from app.services.dashboard_service import _compute_health_flag

_Z = Decimal("0")
_ONE = Decimal("1")


class TestHealthFlagOffTrack:
    """actual_spend > planned_amount triggers off_track regardless of other signals."""

    def test_spend_exceeds_planned(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("1001"),
            utilization_pct=Decimal("100.10"),
            high_impact_open_risk=False,
        ) == "off_track"

    def test_spend_slightly_exceeds_planned(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("1000.01"),
            utilization_pct=Decimal("100.00"),
            high_impact_open_risk=False,
        ) == "off_track"

    def test_zero_budget_with_any_spend_is_off_track(self):
        """When planned == 0 any positive actual is > planned → off_track."""
        assert _compute_health_flag(
            planned=_Z,
            actual=Decimal("0.01"),
            utilization_pct=_Z,  # zero-budget policy: utilization stays 0
            high_impact_open_risk=False,
        ) == "off_track"

    def test_off_track_overrides_high_risk_flag(self):
        """off_track wins even when a high-impact risk also exists."""
        assert _compute_health_flag(
            planned=Decimal("500"),
            actual=Decimal("600"),
            utilization_pct=Decimal("120"),
            high_impact_open_risk=True,
        ) == "off_track"

    def test_off_track_large_overspend(self):
        assert _compute_health_flag(
            planned=Decimal("100"),
            actual=Decimal("9999"),
            utilization_pct=Decimal("9999"),
            high_impact_open_risk=True,
        ) == "off_track"


class TestHealthFlagAtRisk:
    """at_risk when not off_track but a high-impact risk exists or utilization >= 80."""

    def test_high_impact_risk_alone_triggers_at_risk(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("500"),
            utilization_pct=Decimal("50"),
            high_impact_open_risk=True,
        ) == "at_risk"

    def test_utilization_exactly_80_triggers_at_risk(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("800"),
            utilization_pct=Decimal("80"),
            high_impact_open_risk=False,
        ) == "at_risk"

    def test_utilization_above_80_triggers_at_risk(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("999"),
            utilization_pct=Decimal("99.9"),
            high_impact_open_risk=False,
        ) == "at_risk"

    def test_both_high_risk_and_high_utilization(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("850"),
            utilization_pct=Decimal("85"),
            high_impact_open_risk=True,
        ) == "at_risk"

    def test_zero_budget_no_spend_high_risk(self):
        """Zero-budget with no spend is not off_track; high-impact risk → at_risk."""
        assert _compute_health_flag(
            planned=_Z,
            actual=_Z,
            utilization_pct=_Z,
            high_impact_open_risk=True,
        ) == "at_risk"

    def test_utilization_just_below_100_no_overspend(self):
        """utilization 99.9 and actual < planned → at_risk (not off_track)."""
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("999"),
            utilization_pct=Decimal("99.9"),
            high_impact_open_risk=False,
        ) == "at_risk"


class TestHealthFlagOnTrack:
    """on_track when no overspend, no high-impact risk, and utilization < 80."""

    def test_perfectly_healthy_project(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("400"),
            utilization_pct=Decimal("40"),
            high_impact_open_risk=False,
        ) == "on_track"

    def test_zero_spend_zero_risk(self):
        assert _compute_health_flag(
            planned=Decimal("5000"),
            actual=_Z,
            utilization_pct=_Z,
            high_impact_open_risk=False,
        ) == "on_track"

    def test_utilization_just_below_80(self):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("799"),
            utilization_pct=Decimal("79.9"),
            high_impact_open_risk=False,
        ) == "on_track"

    def test_zero_budget_no_spend_no_risk(self):
        """No budget, no spend, no risk → on_track (cleanest empty project)."""
        assert _compute_health_flag(
            planned=_Z,
            actual=_Z,
            utilization_pct=_Z,
            high_impact_open_risk=False,
        ) == "on_track"

    def test_exact_spend_equals_planned_is_not_off_track(self):
        """actual == planned is NOT > planned, so should be at_risk (80% threshold
        would be 80 of 100; utilization == 100 >= 80 → at_risk)."""
        result = _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("1000"),
            utilization_pct=Decimal("100"),
            high_impact_open_risk=False,
        )
        assert result == "at_risk"  # utilization 100 >= 80 triggers at_risk


class TestHealthFlagBoundaryValues:
    """Edge cases around the 80% boundary and zero values."""

    @pytest.mark.parametrize("utilization,expected", [
        (Decimal("79.99"), "on_track"),
        (Decimal("80.00"), "at_risk"),
        (Decimal("80.01"), "at_risk"),
    ])
    def test_utilization_boundary(self, utilization, expected):
        assert _compute_health_flag(
            planned=Decimal("1000"),
            actual=Decimal("500"),  # always < planned, so not off_track
            utilization_pct=utilization,
            high_impact_open_risk=False,
        ) == expected

    @pytest.mark.parametrize("actual,expected", [
        (Decimal("999.99"), "at_risk"),    # 99.999% utilization >= 80% and actual < planned -> at_risk
        (Decimal("1000.00"), "at_risk"),   # 100% utilization >= 80% and actual == planned -> at_risk
        (Decimal("1000.01"), "off_track"), # actual > planned -> off_track
    ])
    def test_actual_vs_planned_boundary(self, actual, expected):
        planned = Decimal("1000")
        utilization = Decimal(str(round(float(actual) / float(planned) * 100, 2))) if planned else Decimal("0")
        result = _compute_health_flag(
            planned=planned,
            actual=actual,
            utilization_pct=utilization,
            high_impact_open_risk=False,
        )
        assert result == expected
