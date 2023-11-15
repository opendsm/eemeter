import numpy as np
from scipy.spatial.distance import cdist

from gridmeter.utils.misc import chunks


def calculate_distances(ls_t, ls_cp, dist_metric, n_matches_per_treatment, n_meters_per_chunk):
    n_chunk_smallest = n_smallest = n_matches_per_treatment
    if n_smallest is None or n_smallest > ls_cp.shape[0]:
        n_smallest = ls_cp.shape[0]

    if n_chunk_smallest is None or n_chunk_smallest > n_meters_per_chunk:
        n_chunk_smallest = n_meters_per_chunk

    dist = []
    cp_id_idx = []
    for idx_chunk, ls_cp_chunk in chunks(ls_cp, n_meters_per_chunk):
        chunked_dist = cdist(ls_t, ls_cp_chunk, metric=dist_metric)
        chunked_cp_id_idx = np.tile(idx_chunk, (chunked_dist.shape[0], 1))

        if n_chunk_smallest < chunked_dist.shape[1]:
            # slice smallest n values
            idx = np.argpartition(chunked_dist, n_chunk_smallest, axis=1)[:, :n_chunk_smallest]
            cp_id_idx.append(chunked_cp_id_idx[np.arange(chunked_dist.shape[0])[:, None], idx])
            dist.append(chunked_dist[np.arange(chunked_dist.shape[0])[:, None], idx])
        else:
            cp_id_idx.append(chunked_cp_id_idx)
            dist.append(chunked_dist)

    dist = np.hstack(dist)
    cp_id_idx = np.hstack(cp_id_idx)

    if n_smallest < dist.shape[1]:
        idx = np.argpartition(dist, n_smallest, axis=1)[:, :n_smallest] # slice smallest n values
    else:
        idx = np.tile(np.arange(dist.shape[1]), (dist.shape[0], 1))

    cp_id_idx = cp_id_idx[np.arange(cp_id_idx.shape[0])[:, None], idx]
    dist = dist[np.arange(dist.shape[0])[:, None], idx]

    return cp_id_idx, dist