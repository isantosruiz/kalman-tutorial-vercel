from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from flask import Flask, jsonify, render_template, request
from scipy.linalg import expm

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
        static_url_path="/static",
    )

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.post("/api/discretize")
    def discretize_api():
        try:
            payload = request.get_json(force=True, silent=False) or {}
            Ac = parse_matrix(payload.get("Ac"), "Ac")
            Bc = parse_matrix(payload.get("Bc"), "Bc")
            Qc = parse_matrix(payload.get("Qc"), "Qc")
            dt = float(payload.get("dt"))

            n = Ac.shape[0]
            if Ac.shape[1] != n:
                raise ValueError("Ac debe ser cuadrada (n x n).")
            if Bc.shape[0] != n:
                raise ValueError("Bc debe tener n filas.")
            if Qc.shape != (n, n):
                raise ValueError("Qc debe ser n x n.")
            if dt <= 0:
                raise ValueError("El periodo de muestreo dt debe ser positivo.")

            Ad, Bd = exact_discretize_dynamics(Ac, Bc, dt)
            Qd = exact_discretize_process_noise(Ac, Qc, dt)

            return jsonify(
                {
                    "Ad": Ad.tolist(),
                    "Bd": Bd.tolist(),
                    "Qd": Qd.tolist(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/run")
    def run_filter_api():
        try:
            payload = request.get_json(force=True, silent=False) or {}
            mode = str(payload.get("mode", "simulation")).strip().lower()

            A = parse_matrix(payload.get("A"), "A")
            B = parse_matrix(payload.get("B"), "B")
            C = parse_matrix(payload.get("C"), "C")
            D = parse_matrix(payload.get("D"), "D")
            Q = parse_matrix(payload.get("Q"), "Q")
            R = parse_matrix(payload.get("R"), "R")
            x0 = parse_vector(payload.get("x0"), "x0")
            P0 = parse_matrix(payload.get("P0"), "P0")

            n = A.shape[0]
            if A.shape[1] != n:
                raise ValueError("A debe ser cuadrada (n x n).")
            if B.shape[0] != n:
                raise ValueError("B debe tener n filas.")

            p = C.shape[0]
            if C.shape[1] != n:
                raise ValueError("C debe tener n columnas.")
            m = B.shape[1]
            if D.shape != (p, m):
                raise ValueError("D debe tener forma (salidas x entradas) = (p x m).")
            if Q.shape != (n, n):
                raise ValueError("Q debe ser n x n.")
            if R.shape != (p, p):
                raise ValueError("R debe ser p x p.")
            if x0.shape[0] != n:
                raise ValueError("x0 debe tener n elementos.")
            if P0.shape != (n, n):
                raise ValueError("P0 debe ser n x n.")

            result: dict[str, Any]

            if mode == "simulation":
                N = int(payload.get("N", 100))
                if N < 2:
                    raise ValueError("N debe ser al menos 2 en modo simulacion.")

                controls = parse_controls(payload.get("controls"), N, m)
                x_true0 = parse_optional_vector(payload.get("x_true0"), n, x0)
                seed = payload.get("seed")
                seed = None if seed in (None, "") else int(seed)

                sim = simulate_system(A, B, C, D, Q, R, x_true0, controls, N, seed)
                measurements = sim["measurements"]
                kf = run_kalman_filter(A, B, C, D, Q, R, x0, P0, measurements, controls)

                result = {
                    "mode": mode,
                    "time": list(range(N)),
                    "controls": controls.tolist(),
                    "measurements": measurements.tolist(),
                    "x_true": sim["x_true"].tolist(),
                    "x_est": kf["x_est"].tolist(),
                    "x_pred": kf["x_pred"].tolist(),
                    "y_est": kf["y_est"].tolist(),
                    "innovation": kf["innovation"].tolist(),
                    "K": kf["K"].tolist(),
                    "P_diag": kf["P_diag"].tolist(),
                    "P_trace": kf["P_trace"].tolist(),
                }
            elif mode == "offline":
                measurements = parse_matrix(payload.get("measurements"), "measurements")
                if measurements.ndim != 2:
                    raise ValueError("measurements debe ser una matriz de N x p.")
                if measurements.shape[1] != p:
                    raise ValueError("measurements debe tener p columnas (dimensión de salida).")
                N = measurements.shape[0]
                controls = parse_controls(payload.get("controls"), N, m)

                kf = run_kalman_filter(A, B, C, D, Q, R, x0, P0, measurements, controls)

                result = {
                    "mode": mode,
                    "time": list(range(N)),
                    "controls": controls.tolist(),
                    "measurements": measurements.tolist(),
                    "x_est": kf["x_est"].tolist(),
                    "x_pred": kf["x_pred"].tolist(),
                    "y_est": kf["y_est"].tolist(),
                    "innovation": kf["innovation"].tolist(),
                    "K": kf["K"].tolist(),
                    "P_diag": kf["P_diag"].tolist(),
                    "P_trace": kf["P_trace"].tolist(),
                }
            else:
                raise ValueError("mode debe ser 'simulation' u 'offline'.")

            return jsonify(result)

        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400

    return app


def parse_optional_vector(raw: Any, expected_len: int, fallback: np.ndarray) -> np.ndarray:
    if raw in (None, ""):
        return fallback
    vec = parse_vector(raw, "x_true0")
    if vec.shape[0] != expected_len:
        raise ValueError("x_true0 debe tener n elementos.")
    return vec


def parse_controls(raw: Any, N: int, m: int) -> np.ndarray:
    if raw in (None, ""):
        return np.zeros((N, m), dtype=float)

    arr = parse_matrix(raw, "controls")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)

    if arr.shape[1] != m:
        raise ValueError(f"controls debe tener {m} columna(s).")

    if arr.shape[0] == 1:
        return np.repeat(arr, N, axis=0)
    if arr.shape[0] == N:
        return arr
    if arr.shape[0] == N - 1:
        return np.vstack([arr, arr[-1]])

    raise ValueError("controls debe tener N filas, 1 fila, o N-1 filas.")


def parse_vector(raw: Any, name: str) -> np.ndarray:
    arr = parse_matrix(raw, name)
    if arr.ndim == 2:
        if 1 in arr.shape:
            return arr.reshape(-1)
        raise ValueError(f"{name} debe ser un vector.")
    return arr


def parse_matrix(raw: Any, name: str) -> np.ndarray:
    if raw is None:
        raise ValueError(f"Falta el valor de {name}.")

    if isinstance(raw, (list, tuple)):
        arr = np.array(raw, dtype=float)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError(f"{name} no puede estar vacio.")

        arr = _parse_text_matrix(text)
    else:
        raise ValueError(f"Formato invalido para {name}.")

    if arr.ndim == 0:
        arr = np.array([[float(arr)]], dtype=float)

    return arr.astype(float)


def _parse_text_matrix(text: str) -> np.ndarray:
    try:
        parsed = json.loads(text)
        return np.array(parsed, dtype=float)
    except Exception:  # noqa: BLE001
        pass

    cleaned = text.replace(";", "\n")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    rows: list[list[float]] = []
    for line in lines:
        tokens = [tok for tok in re.split(r"[\s,]+", line) if tok]
        rows.append([float(tok) for tok in tokens])

    if not rows:
        raise ValueError("Entrada vacia.")

    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("Todas las filas deben tener la misma longitud.")

    return np.array(rows, dtype=float)


def exact_discretize_dynamics(Ac: np.ndarray, Bc: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    n = Ac.shape[0]
    m = Bc.shape[1]
    block = np.zeros((n + m, n + m), dtype=float)
    block[:n, :n] = Ac
    block[:n, n:] = Bc
    phi = expm(block * dt)
    Ad = phi[:n, :n]
    Bd = phi[:n, n:]
    return Ad, Bd


def exact_discretize_process_noise(Ac: np.ndarray, Qc: np.ndarray, dt: float) -> np.ndarray:
    n = Ac.shape[0]
    block = np.zeros((2 * n, 2 * n), dtype=float)
    block[:n, :n] = -Ac
    block[:n, n:] = Qc
    block[n:, n:] = Ac.T
    phi = expm(block * dt)
    phi12 = phi[:n, n:]
    phi22 = phi[n:, n:]
    Qd = phi22.T @ phi12
    return 0.5 * (Qd + Qd.T)


def simulate_system(
    A: np.ndarray,
    B: np.ndarray,
    C: np.ndarray,
    D: np.ndarray,
    Q: np.ndarray,
    R: np.ndarray,
    x0: np.ndarray,
    controls: np.ndarray,
    N: int,
    seed: int | None,
) -> dict[str, np.ndarray]:
    n = A.shape[0]
    p = C.shape[0]

    rng = np.random.default_rng(seed)
    w = rng.multivariate_normal(np.zeros(n), Q, size=max(N - 1, 1))
    v = rng.multivariate_normal(np.zeros(p), R, size=N)

    x_true = np.zeros((N, n), dtype=float)
    y = np.zeros((N, p), dtype=float)

    x_true[0] = x0
    for k in range(N):
        uk = controls[k]
        y[k] = (C @ x_true[k].reshape(-1, 1) + D @ uk.reshape(-1, 1)).reshape(-1) + v[k]

        if k < N - 1:
            x_next = A @ x_true[k].reshape(-1, 1) + B @ uk.reshape(-1, 1) + w[k].reshape(-1, 1)
            x_true[k + 1] = x_next.reshape(-1)

    return {"x_true": x_true, "measurements": y}


def run_kalman_filter(
    A: np.ndarray,
    B: np.ndarray,
    C: np.ndarray,
    D: np.ndarray,
    Q: np.ndarray,
    R: np.ndarray,
    x0: np.ndarray,
    P0: np.ndarray,
    measurements: np.ndarray,
    controls: np.ndarray,
) -> dict[str, np.ndarray]:
    n = A.shape[0]
    p = C.shape[0]
    m = B.shape[1]
    N = measurements.shape[0]

    x_pred_hist = np.zeros((N, n), dtype=float)
    x_est_hist = np.zeros((N, n), dtype=float)
    y_est_hist = np.zeros((N, p), dtype=float)
    K_hist = np.zeros((N, n, p), dtype=float)
    innovation_hist = np.zeros((N, p), dtype=float)
    P_pred_hist = np.zeros((N, n, n), dtype=float)
    P_est_hist = np.zeros((N, n, n), dtype=float)

    x_prev = x0.reshape(n, 1)
    P_prev = P0.copy()
    I = np.eye(n)

    for k in range(N):
        if k == 0:
            x_pred = x_prev
            P_pred = P_prev
        else:
            uk_prev = controls[k - 1].reshape(m, 1)
            x_pred = A @ x_prev + B @ uk_prev
            P_pred = A @ P_prev @ A.T + Q

        uk = controls[k].reshape(m, 1)
        yk = measurements[k].reshape(p, 1)

        S = C @ P_pred @ C.T + R
        K = np.linalg.solve(S, C @ P_pred).T
        innovation = yk - (C @ x_pred + D @ uk)

        x_est = x_pred + K @ innovation

        # Forma de Joseph para mejorar estabilidad numérica de P.
        P_est = (I - K @ C) @ P_pred @ (I - K @ C).T + K @ R @ K.T

        y_est = C @ x_est + D @ uk

        x_pred_hist[k] = x_pred.reshape(-1)
        x_est_hist[k] = x_est.reshape(-1)
        y_est_hist[k] = y_est.reshape(-1)
        K_hist[k] = K
        innovation_hist[k] = innovation.reshape(-1)
        P_pred_hist[k] = P_pred
        P_est_hist[k] = P_est

        x_prev = x_est
        P_prev = P_est

    P_diag = np.diagonal(P_est_hist, axis1=1, axis2=2)
    P_trace = np.trace(P_est_hist, axis1=1, axis2=2)

    return {
        "x_pred": x_pred_hist,
        "x_est": x_est_hist,
        "y_est": y_est_hist,
        "innovation": innovation_hist,
        "K": K_hist,
        "P_diag": P_diag,
        "P_trace": P_trace,
    }


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
