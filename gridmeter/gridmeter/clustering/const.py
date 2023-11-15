"""
contains constants used for clustering
"""
from __future__ import annotations

from enum import Enum

# used in clustering settings
from gridmeter.utils.const import DistanceMetric
from gridmeter.utils.const import AggType


class ScoreChoice(str, Enum):
    SILHOUETTE = "silhouette"
    SILHOUETTE_MEDIAN = "silhouette_median"
    VARIANCE_RATIO = "variance_ratio"
    CALINSKI_HARABASZ = "calinski-harabasz"
    DAVIES_BOULDIN = "davies-bouldin"
