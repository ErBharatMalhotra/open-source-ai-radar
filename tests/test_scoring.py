"""Tests for the three-axis scoring engine (health axis deepening)."""

import pytest

from radar.scoring.engine import ScoringEngine


@pytest.fixture
def engine():
    return ScoringEngine(db=None)


class TestBusFactorScore:
    def test_healthy_team(self, engine):
        assert engine._bus_factor_score(50) == 95.0
        assert engine._bus_factor_score(25) == 95.0

    def test_solid_team(self, engine):
        assert engine._bus_factor_score(10) == 85.0
        assert engine._bus_factor_score(24) == 85.0

    def test_small_team(self, engine):
        assert engine._bus_factor_score(5) == 70.0
        assert engine._bus_factor_score(9) == 70.0

    def test_risky(self, engine):
        assert engine._bus_factor_score(2) == 50.0
        assert engine._bus_factor_score(4) == 50.0

    def test_single_maintainer_or_unknown(self, engine):
        assert engine._bus_factor_score(1) == 20.0
        assert engine._bus_factor_score(0) == 20.0


class TestLicenseScore:
    def test_missing_license_scores_low(self, engine):
        assert engine._license_score({"license": None}) == 30.0
        assert engine._license_score({"license": ""}) == 30.0

    def test_known_safe_license(self, engine):
        assert engine._license_score({"license": "MIT"}) == 90.0
        assert engine._license_score({"license": "Apache-2.0"}) == 90.0
        assert engine._license_score({"license": "GPL-3.0-only"}) == 90.0

    def test_unknown_license_scores_mid(self, engine):
        assert engine._license_score({"license": "Weird-Custom-1.0"}) == 60.0


class TestHealthIntegration:
    def _base_repo(self):
        return {
            "stars": 1000,
            "forks": 150,
            "open_issues": 20,
            "pushed_at": None,
            "latest_release_tag": "v1.0.0",
            "latest_release_date": None,
            "license": "MIT",
        }

    def test_bus_factor_lifts_health(self, engine):
        weak = self._base_repo()
        strong = self._base_repo()
        h_weak = engine._health(weak, freshness=1.0, bus_factor=1)
        h_strong = engine._health(strong, freshness=1.0, bus_factor=40)
        assert h_strong > h_weak
        # Bus factor weight is 15% of the axis
        assert abs(h_strong - h_weak) == pytest.approx((95.0 - 20.0) * 0.15)

    def test_license_penalty_applies(self, engine):
        licensed = self._base_repo()
        unlicensed = self._base_repo()
        unlicensed["license"] = None
        h_licensed = engine._health(licensed, freshness=1.0, bus_factor=10)
        h_unlicensed = engine._health(unlicensed, freshness=1.0, bus_factor=10)
        assert h_licensed > h_unlicensed
        assert abs(h_licensed - h_unlicensed) == pytest.approx((90.0 - 30.0) * 0.10)

    def test_health_bounded_0_100(self, engine):
        repo = self._base_repo()
        for contributors in (0, 5, 100):
            h = engine._health(repo, freshness=1.0, bus_factor=contributors)
            assert 0.0 <= h <= 100.0
