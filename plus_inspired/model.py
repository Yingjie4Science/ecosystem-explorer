"""One-vs-rest expansion forests with non-executable JSON persistence."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from .core import expansion


def fit(start, end, drivers, valid, classes, *, seed=42, trees=64, max_samples=60000):
    if type(seed) is not int or seed < 0 or type(trees) is not int or not 1 <= trees <= 512 or type(max_samples) is not int or max_samples < 2:
        raise ValueError("invalid forest seed, trees or sample limit")
    if drivers.ndim != 3 or drivers.shape[1:] != start.shape or not np.isfinite(drivers[:, valid]).all():
        raise ValueError("drivers must be finite on complete training support")
    changed = expansion(start, end, valid, classes)
    locations = np.flatnonzero(valid.ravel())
    rng = np.random.default_rng(seed)
    # Uniform sampling retains the natural expansion base rate; balancing
    # would change probability interpretation and is not silently enabled.
    selected = rng.choice(locations, min(len(locations), max_samples), replace=False)
    x = drivers.reshape(len(drivers), -1)[:, selected].T
    models = []
    for index, code in enumerate(classes):
        y = (changed.ravel()[selected] == code).astype(np.uint8)
        if not y.any() and (changed[valid] == code).any():
            raise ValueError(f"sampling missed expansion class {code}; increase max_samples")
        if y.min() == y.max():
            models.append({"constant": float(y[0]), "sample_positives": int(y.sum()),
                           "full_positives": int((changed[valid] == code).sum())})
            continue
        forest = RandomForestClassifier(n_estimators=trees, max_depth=12, min_samples_leaf=2,
                                        max_features="sqrt", random_state=seed + index, n_jobs=1)
        forest.fit(x, y)
        serialized = []
        for estimator in forest.estimators_:
            tree = estimator.tree_
            values = tree.value[:, 0, :]
            probabilities = values[:, 1] / values.sum(axis=1)
            serialized.append({"left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
                               "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
                               "probability": probabilities.tolist()})
        models.append({"trees": serialized, "sample_positives": int(y.sum()),
                       "full_positives": int((changed[valid] == code).sum())})
    return {"format": "plus-inspired-forest-v1", "classes": list(classes), "feature_count": len(drivers),
            "models": models, "seed": seed, "sample_size": len(selected),
            "feature_ranges": [[float(d[valid].min()), float(d[valid].max())] for d in drivers],
            "rf_parameters": {"trees": trees, "max_depth": 12, "min_samples_leaf": 2,
                              "max_features": "sqrt", "n_jobs": 1, "sampling": "uniform_without_replacement"}}


def check_model(model):
    if model.get("format") != "plus-inspired-forest-v1" or type(model.get("feature_count")) is not int or model["feature_count"] < 1:
        raise ValueError("unknown or malformed model format")
    from .core import schema
    schema(model["classes"])
    if len(model["models"]) != len(model["classes"]):
        raise ValueError("model/class count mismatch")
    for component in model["models"]:
        if "constant" in component:
            if not np.isfinite(component["constant"]) or not 0 <= component["constant"] <= 1:
                raise ValueError("invalid constant suitability")
            continue
        if not component.get("trees") or len(component["trees"]) > 512:
            raise ValueError("invalid forest tree count")
        for tree in component["trees"]:
            n = len(tree["feature"])
            if not n or n > 100000 or any(len(tree[key]) != n for key in ["left", "right", "threshold", "probability"]):
                raise ValueError("malformed tree lengths")
            if not np.isfinite(tree["threshold"]).all() or not np.isfinite(tree["probability"]).all() or ((np.array(tree["probability"]) < 0) | (np.array(tree["probability"]) > 1)).any():
                raise ValueError("nonfinite or invalid tree values")
            for node, feature in enumerate(tree["feature"]):
                left, right = tree["left"][node], tree["right"][node]
                if type(feature) is not int or type(left) is not int or type(right) is not int:
                    raise ValueError("tree indexes must be integers")
                if feature == -2:
                    if left != -1 or right != -1:
                        raise ValueError("invalid leaf")
                elif not 0 <= feature < model["feature_count"] or not node < left < n or not node < right < n:
                    raise ValueError("invalid or cyclic tree child")


def predict(model, drivers, valid, *, chunk_size=100000):
    check_model(model)
    if drivers.ndim != 3 or drivers.shape != (model["feature_count"], *valid.shape) or not np.isfinite(drivers[:, valid]).all():
        raise ValueError("inference feature shape or finite-support mismatch")
    output = np.full((len(model["classes"]), *valid.shape), np.nan, dtype=np.float32)
    locations = np.flatnonzero(valid.ravel())
    for component_index, component in enumerate(model["models"]):
        if "constant" in component:
            output[component_index][valid] = component["constant"]
            continue
        for offset in range(0, len(locations), chunk_size):
            selected = locations[offset:offset + chunk_size]
            x = drivers.reshape(len(drivers), -1)[:, selected].T
            aggregate = np.zeros(len(selected))
            for tree in component["trees"]:
                nodes = np.zeros(len(selected), dtype=np.int64)
                feature = np.array(tree["feature"])
                left, right = np.array(tree["left"]), np.array(tree["right"])
                threshold = np.array(tree["threshold"])
                while True:
                    active = np.flatnonzero(feature[nodes] >= 0)
                    if not len(active):
                        break
                    current_nodes = nodes[active]
                    go_left = x[active, feature[current_nodes]] <= threshold[current_nodes]
                    nodes[active] = np.where(go_left, left[current_nodes], right[current_nodes])
                aggregate += np.array(tree["probability"])[nodes]
            output[component_index].ravel()[selected] = aggregate / len(component["trees"])
    return output
