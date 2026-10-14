"""The observation cadence and the freshness window repository metadata is held to."""

from __future__ import annotations

from datetime import timedelta

OBSERVATION_INTERVAL = timedelta(seconds=120)
FRESHNESS_WINDOW = timedelta(minutes=15)
# A repository is collected once its last attempt is this old: two intervals before its
# observation expires, so collection on its first due tick lands in time even when ticks
# run up to half an interval.
COLLECTION_DUE = FRESHNESS_WINDOW - 2 * OBSERVATION_INTERVAL
