"""HMM regime detection: train, predict, and label states."""
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM


N_STATES = 3
N_RESTARTS = 20   # independent EM runs; keep the best log-likelihood
BASE_SEED = 42    # seed 42, 43, 44 … for each restart → reproducible


def train(features: pd.DataFrame, n_states: int = N_STATES,
          n_restarts: int = N_RESTARTS) -> GaussianHMM:
    """
    Run EM n_restarts times with different seeds and return the model
    with the highest log-likelihood, avoiding local optima.
    """
    X = features.values
    best_model: GaussianHMM | None = None
    best_score = -np.inf
    best_seed = BASE_SEED

    for i in range(n_restarts):
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=200,
            random_state=BASE_SEED + i,
            tol=1e-5,
        )
        try:
            model.fit(X)
            score = model.score(X)
            if score > best_score:
                best_score = score
                best_model = model
                best_seed = BASE_SEED + i
        except Exception:
            continue

    if best_model is None:
        raise RuntimeError("All HMM restarts failed to converge.")

    print(f"  Best log-likelihood: {best_score:.2f}  |  "
          f"converged: {best_model.monitor_.converged}  |  "
          f"winning seed: {best_seed}  ({n_restarts} restarts)")
    return best_model


def predict(model: GaussianHMM, features: pd.DataFrame) -> pd.Series:
    states = model.predict(features.values)
    return pd.Series(states, index=features.index, name="raw_state")


def label_states(model: GaussianHMM, features: pd.DataFrame) -> dict[int, str]:
    """
    Assign human-readable labels by looking at the mean log return
    for each hidden state. Highest return → Bull, lowest → Bear, middle → Sideways.
    """
    states = model.predict(features.values)
    ret_col = features.columns.get_loc("log_ret")
    means = {}
    for s in range(model.n_components):
        mask = states == s
        means[s] = features.values[mask, ret_col].mean() if mask.sum() > 0 else 0.0

    sorted_states = sorted(means, key=means.get)
    labels = {}
    labels[sorted_states[0]] = "Bear"
    labels[sorted_states[1]] = "Sideways"
    labels[sorted_states[2]] = "Bull"
    return labels


def regime_series(model: GaussianHMM, features: pd.DataFrame) -> pd.DataFrame:
    raw = predict(model, features)
    labels = label_states(model, features)

    # Posterior probabilities for each state
    log_probs = model.predict_proba(features.values)

    out = pd.DataFrame(index=features.index)
    out["state"] = raw.map(labels)
    out["confidence"] = log_probs.max(axis=1)

    for s in range(model.n_components):
        label = labels[s]
        out[f"p_{label.lower()}"] = log_probs[:, s]

    return out
