"""Multi-view label voting: a point keeps a label only when several views agree on it."""

from dataclasses import dataclass
from typing import Optional

import numpy as np

MIN_VIEWS = 2
MIN_LABEL_SHARE = 0.3
NO_LABEL = -1


@dataclass
class LabelVotes:
    """score[p, l] sums detector scores, views[p, l] counts distinct views that labelled point p with l."""

    score: np.ndarray
    views: np.ndarray

    @classmethod
    def empty(cls, point_count: int, label_count: int) -> "LabelVotes":
        return cls(np.zeros((point_count, label_count)), np.zeros((point_count, label_count), dtype=np.int32))

    def assign(self, min_views: int = MIN_VIEWS, min_share: float = MIN_LABEL_SHARE) -> np.ndarray:
        """Label index per point, or NO_LABEL. The winner is the highest summed score among labels with enough views."""
        eligible = np.where(self.views >= min_views, self.score, 0.0)
        winner = eligible.argmax(axis=1)
        total = self.score.sum(axis=1)
        share = np.divide(eligible.max(axis=1), total, out=np.zeros_like(total), where=total > 0)
        is_kept = (eligible.max(axis=1) > 0) & (share >= min_share)
        return np.where(is_kept, winner, NO_LABEL)


def add_view_masks(votes: LabelVotes, masks: list) -> None:
    """Add all (point_indices, label_index, score) masks of ONE view, counting each point once per label."""
    best: dict = {}
    for point_indices, label_index, detector_score in masks:
        best.setdefault(label_index, []).append((point_indices, detector_score))
    for label_index, entries in best.items():
        top = np.zeros(votes.score.shape[0])
        for point_indices, detector_score in entries:
            top[point_indices] = np.maximum(top[point_indices], detector_score)
        hit = np.flatnonzero(top)
        votes.score[hit, label_index] += top[hit]
        votes.views[hit, label_index] += 1
