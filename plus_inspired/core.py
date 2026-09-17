"""Pure-array contracts and an explicit net-change patch allocator.

This is not a CARS clone. A spatially aware flow certificate reserves feasible
source-group/target quotas; seeded patch scores place those quotas. Balanced
exchanges and intermediate transitions are deliberately outside v1 scope.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter, label
from scipy.optimize import linprog
from scipy.sparse import lil_matrix


def schema(classes):
    if not classes or len(classes) > 32 or any(type(c) is not int or c < 0 or c > 32767 for c in classes):
        raise ValueError("classes must be nonnegative int16-compatible integer codes")
    if len(classes) != len(set(classes)):
        raise ValueError("duplicate class codes")
    return tuple(classes)


def categorical(array, valid, classes):
    schema(classes)
    if array.ndim != 2 or valid.shape != array.shape or valid.dtype != bool:
        raise ValueError("expected 2D raster and matching boolean validity mask")
    if not np.issubdtype(array.dtype, np.integer) or not valid.any():
        raise ValueError("categorical raster must be integer with nonempty support")
    if not np.isin(array[valid], classes).all():
        raise ValueError("unknown land class")


def expansion(start, end, valid, classes):
    categorical(start, valid, classes)
    categorical(end, valid, classes)
    if start.shape != end.shape:
        raise ValueError("epoch shape mismatch")
    result = np.full(start.shape, -1, dtype=np.int16)
    # -2 is unchanged, -1 invalid; actual class 0 is therefore unambiguous.
    result[valid] = -2
    changed = valid & (start != end)
    result[changed] = end[changed]
    return result


def counts(array, valid, classes):
    return np.array([np.count_nonzero(valid & (array == c)) for c in classes], dtype=np.int64)


def allocate(initial, probabilities, valid, editable, classes, demand, transitions,
             *, seed=42, neighborhood=3, patch_weight=1.0, stochasticity=0.05,
             batch_size=128, max_rounds=10000):
    """Exact net-change quotas, respecting original-source transitions.

    No held-out observations enter this API. Probability zero cannot expand.
    Existing cover may persist at zero probability. Infeasible or incomplete
    runs raise rather than returning a successful projection.
    """
    categorical(initial, valid, classes)
    k = len(classes)
    if editable.shape != initial.shape or editable.dtype != bool or (editable & ~valid).any():
        raise ValueError("editable must be boolean and contained in valid support")
    if probabilities.shape != (k, *initial.shape):
        raise ValueError("probability/class/grid mismatch")
    if not np.isfinite(probabilities[:, valid]).all() or ((probabilities[:, valid] < 0) | (probabilities[:, valid] > 1)).any():
        raise ValueError("suitability must be finite in [0,1] on all valid cells")
    demand = np.asarray(demand)
    transitions = np.asarray(transitions)
    if demand.shape != (k,) or not np.issubdtype(demand.dtype, np.integer) or (demand < 0).any():
        raise ValueError("demand must contain one nonnegative integer per class")
    if demand.sum() != valid.sum():
        raise ValueError("demand total differs from valid support")
    if transitions.shape != (k, k) or not np.isin(transitions, [0, 1]).all() or not np.diag(transitions).all():
        raise ValueError("transition matrix must be binary with persistence allowed")
    if type(seed) is not int or seed < 0 or type(neighborhood) is not int or neighborhood < 3 or neighborhood % 2 != 1:
        raise ValueError("seed nonnegative; neighborhood odd and >=3")
    if not np.isfinite([patch_weight, stochasticity]).all() or patch_weight < 0 or stochasticity < 0:
        raise ValueError("patch/stochasticity weights must be finite and nonnegative")
    if type(batch_size) is not int or batch_size < 1 or type(max_rounds) is not int or max_rounds < 1:
        raise ValueError("batch_size and max_rounds must be positive integers")
    before = counts(initial, valid, classes)
    surplus = np.maximum(before - demand, 0)
    deficit = np.maximum(demand - before, 0)
    current = initial.copy()
    if not surplus.any():
        return current, {"rounds": 0, "changed_cells": 0, "final_counts": before.tolist()}

    # Cells with identical source class and target availability form an
    # interchangeable group for feasibility, not for spatial ranking.
    groups = []
    edges = []
    for source in np.flatnonzero(surplus):
        locations = np.flatnonzero((editable & (initial == classes[source])).ravel())
        targets = np.flatnonzero((deficit > 0) & (transitions[source] == 1))
        if not len(locations) or not len(targets):
            continue
        support = (probabilities[targets].reshape(len(targets), -1)[:, locations] > 0).T
        patterns, inverse = np.unique(support, axis=0, return_inverse=True)
        for pattern_index, pattern in enumerate(patterns):
            if not pattern.any():
                continue
            cells = locations[inverse == pattern_index]
            group_index = len(groups)
            groups.append((source, cells))
            for target in targets[pattern]:
                edges.append((group_index, int(target)))
                if len(edges) > 50000:
                    raise ValueError("feasibility graph exceeds v1 50,000-edge bound")
    if not edges:
        raise ValueError("infeasible net-change demand: no eligible positive-suitability transitions")
    # Source→group→target network constraints are totally unimodular.
    source_rows = np.flatnonzero(surplus)
    target_rows = np.flatnonzero(deficit)
    eq = lil_matrix((len(source_rows) + len(target_rows), len(edges)))
    capacity = lil_matrix((len(groups), len(edges)))
    cost = []
    for column, (group_index, target) in enumerate(edges):
        source, cells = groups[group_index]
        eq[int(np.flatnonzero(source_rows == source)[0]), column] = 1
        eq[len(source_rows) + int(np.flatnonzero(target_rows == target)[0]), column] = 1
        capacity[group_index, column] = 1
        cost.append(-float(probabilities[target].ravel()[cells].mean()))
    solution = linprog(cost, A_ub=capacity.tocsr(), b_ub=[len(g[1]) for g in groups],
                       A_eq=eq.tocsr(), b_eq=np.r_[surplus[source_rows], deficit[target_rows]],
                       bounds=(0, None), method="highs")
    if not solution.success:
        raise ValueError("infeasible net-change demand under locks, transitions and suitability")
    quota = np.rint(solution.x).astype(np.int64)
    if not np.allclose(solution.x, quota, atol=1e-6, rtol=0) or not np.array_equal(eq @ quota, np.r_[surplus[source_rows], deficit[target_rows]]) or (capacity @ quota > [len(g[1]) for g in groups]).any():
        raise ValueError("invalid integer feasibility certificate")
    rng = np.random.default_rng(seed)
    history = []
    available = np.ones(initial.size, dtype=bool)
    for round_index in range(max_rounds):
        if not quota.any():
            break
        target_order = rng.permutation(np.flatnonzero(deficit))
        for target in target_order:
            # Uniform positive baseline allows spontaneous patch seeding even
            # where no target neighbor exists. Not published CARS thresholding.
            fraction = uniform_filter((current == classes[target]).astype(float), size=neighborhood, mode="constant")
            for edge_index, (group_index, edge_target) in enumerate(edges):
                if edge_target != target or quota[edge_index] == 0:
                    continue
                cells = groups[group_index][1]
                cells = cells[available[cells]]
                take = min(batch_size, int(quota[edge_index]))
                if len(cells) < take:
                    raise ValueError("allocation exhausted its feasible group")
                score = probabilities[target].ravel()[cells] * (1 + patch_weight * fraction.ravel()[cells])
                score += stochasticity * rng.random(len(cells))
                # Lexicographic cell-index tie break is explicit and stable.
                chosen = cells[np.lexsort((cells, -score))[:take]]
                current.ravel()[chosen] = classes[target]
                available[chosen] = False
                quota[edge_index] -= take
        history.append(counts(current, valid, classes).tolist())
    if quota.any() or not np.array_equal(counts(current, valid, classes), demand):
        raise ValueError("iteration limit: demand incomplete; no successful projection")
    changed = valid & (current != initial)
    if (changed & ~editable).any() or not np.array_equal(current[~valid], initial[~valid]):
        raise ValueError("constraint invariant violated")
    return current, {"rounds": len(history), "changed_cells": int(changed.sum()),
                     "final_counts": demand.tolist(), "history": history}


def validate(initial, observed, simulated, valid, classes):
    for array in [initial, observed, simulated]:
        categorical(array, valid, classes)
    matrix = np.zeros((len(classes), len(classes)), dtype=np.int64)
    for i, code in enumerate(classes):
        for j, prediction in enumerate(classes):
            matrix[i, j] = np.count_nonzero(valid & (observed == code) & (simulated == prediction))
    total = int(valid.sum())
    accuracy = float(np.trace(matrix) / total)
    quantity = float(np.abs(matrix.sum(axis=0) - matrix.sum(axis=1)).sum() / (2 * total))
    obs_change = valid & (observed != initial)
    sim_change = valid & (simulated != initial)
    hit = int((obs_change & sim_change & (observed == simulated)).sum())
    denominator = int((obs_change | sim_change).sum())
    per_class = {}
    for index, code in enumerate(classes):
        precision_n = int(matrix[:, index].sum())
        recall_n = int(matrix[index].sum())
        per_class[str(code)] = {"precision": float(matrix[index, index] / precision_n) if precision_n else None,
                               "recall": float(matrix[index, index] / recall_n) if recall_n else None}
    patch_counts = {str(c): {name: int(label(valid & (array == c))[1]) for name, array in [("observed", observed), ("simulated", simulated)]} for c in classes}
    transitions = {}
    for source in classes:
        for target in classes:
            if source == target:
                continue
            actual = valid & (initial == source) & (observed == target)
            predicted = valid & (initial == source) & (simulated == target)
            union = int((actual | predicted).sum())
            if union:
                transitions[f"{source}->{target}"] = {"observed": int(actual.sum()), "predicted": int(predicted.sum()),
                                                       "intersection_over_union": float((actual & predicted).sum() / union)}
    return {"overall_accuracy": accuracy, "quantity_disagreement": quantity,
            "allocation_disagreement": max(0.0, 1 - accuracy - quantity),
            "figure_of_merit": hit / denominator if denominator else None,
            "observed_change_cells": int(obs_change.sum()), "predicted_change_cells": int(sim_change.sum()),
            "confusion_matrix": matrix.tolist(), "classes": list(classes),
            "per_class": per_class, "patch_counts_4_connected": patch_counts,
            "transition_iou": transitions}
