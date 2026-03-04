const elements = {
  Ac: document.getElementById("Ac"),
  Bc: document.getElementById("Bc"),
  Qc: document.getElementById("Qc"),
  dt: document.getElementById("dt"),
  continuousConfirm: document.getElementById("continuousConfirm"),
  continuousSection: document.getElementById("continuousSection"),
  A: document.getElementById("A"),
  B: document.getElementById("B"),
  C: document.getElementById("C"),
  D: document.getElementById("D"),
  Q: document.getElementById("Q"),
  R: document.getElementById("R"),
  x0: document.getElementById("x0"),
  P0: document.getElementById("P0"),
  N: document.getElementById("N"),
  seed: document.getElementById("seed"),
  xTrue0: document.getElementById("xTrue0"),
  controlsSim: document.getElementById("controlsSim"),
  controlsOffline: document.getElementById("controlsOffline"),
  measurements: document.getElementById("measurements"),
  measurementsFile: document.getElementById("measurementsFile"),
  offlineInfo: document.getElementById("offlineInfo"),
  status: document.getElementById("status"),
  resultsSection: document.getElementById("resultsSection"),
  metrics: document.getElementById("metrics"),
  stepsTableBody: document.querySelector("#stepsTable tbody"),
  simulationPanel: document.getElementById("simulationPanel"),
  offlinePanel: document.getElementById("offlinePanel"),
};

const modeButtons = Array.from(document.querySelectorAll(".mode-btn"));
const discretizeBtn = document.getElementById("discretizeBtn");
const runBtn = document.getElementById("runBtn");

let currentMode = "simulation";
toggleContinuousSection(elements.continuousConfirm.checked);
toggleResultsSection(false);

modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const mode = btn.dataset.mode;
    currentMode = mode;

    modeButtons.forEach((node) => node.classList.toggle("active", node === btn));
    elements.simulationPanel.className =
      mode === "simulation" ? "grid two-cols panel-visible" : "panel-hidden";
    elements.offlinePanel.className = mode === "offline" ? "panel-visible" : "panel-hidden";
  });
});

elements.measurementsFile.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  const text = await file.text();
  const matrix = parseCsv(text);
  if (!matrix.length) {
    setStatus("No se detectaron filas numéricas válidas en el CSV.", true);
    return;
  }

  elements.measurements.value = matrix.map((row) => row.join(" ")).join("\n");
  elements.offlineInfo.textContent = `CSV cargado: ${matrix.length} fila(s), ${matrix[0].length} columna(s).`;
  setStatus("CSV de mediciones cargado correctamente.", false);
});

elements.continuousConfirm.addEventListener("change", () => {
  const isContinuous = elements.continuousConfirm.checked;
  toggleContinuousSection(isContinuous);

  if (!isContinuous) {
    setStatus("Se usará el modelo discreto ingresado en A, B y Q.", false);
    return;
  }
  setStatus("Modelo continuo confirmado. Pulsa \"Discretizar modelo continuo\" para actualizar A, B y Q.", false);
});

discretizeBtn.addEventListener("click", async () => {
  setStatus("Discretizando modelo continuo...", false);
  try {
    await discretizeContinuousModel();
    setStatus("Discretización exacta aplicada y matrices copiadas al modelo discreto.", false);
  } catch (error) {
    setStatus(error.message, true);
  }
});

runBtn.addEventListener("click", async () => {
  setStatus("Ejecutando filtro...", false);

  try {
    const payload = {
      mode: currentMode,
      A: elements.A.value,
      B: elements.B.value,
      C: elements.C.value,
      D: elements.D.value,
      Q: elements.Q.value,
      R: elements.R.value,
      x0: elements.x0.value,
      P0: elements.P0.value,
    };

    if (currentMode === "simulation") {
      payload.N = Number(elements.N.value);
      payload.seed = elements.seed.value.trim();
      payload.x_true0 = elements.xTrue0.value.trim();
      payload.controls = elements.controlsSim.value.trim();
    } else {
      payload.measurements = elements.measurements.value.trim();
      payload.controls = elements.controlsOffline.value.trim();
    }

    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Fallo en la ejecución del filtro.");
    }

    toggleResultsSection(true);
    renderMetrics(result);
    renderPlots(result);
    renderSteps(result);

    setStatus("Filtro ejecutado correctamente.", false);
  } catch (error) {
    setStatus(error.message, true);
  }
});

async function discretizeContinuousModel() {
  const payload = {
    Ac: elements.Ac.value,
    Bc: elements.Bc.value,
    Qc: elements.Qc.value,
    dt: Number(elements.dt.value),
  };

  const response = await fetch("/api/discretize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "No se pudo discretizar el modelo.");
  }

  elements.A.value = matrixToText(result.Ad);
  elements.B.value = matrixToText(result.Bd);
  elements.Q.value = matrixToText(result.Qd);
}

function toggleContinuousSection(visible) {
  elements.continuousSection.hidden = !visible;
}

function toggleResultsSection(visible) {
  elements.resultsSection.hidden = !visible;
}

function parseCsv(text) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const rows = [];
  for (const line of lines) {
    const tokens = line.split(/[;,\t]/).map((part) => part.trim());
    const numeric = tokens.map((token) => Number(token));
    if (numeric.every((value) => Number.isFinite(value))) {
      rows.push(numeric);
    }
  }
  return rows;
}

function setStatus(message, isError) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", Boolean(isError));
  elements.status.classList.toggle("ok", !isError && Boolean(message));
}

function matrixToText(matrix) {
  return matrix.map((row) => row.map((v) => Number(v.toFixed(6))).join(" ")).join("\n");
}

function renderMetrics(result) {
  const n = result.x_est[0]?.length || 0;
  const p = result.measurements[0]?.length || 0;
  const N = result.time.length;

  const finalTrace = result.P_trace[result.P_trace.length - 1];
  const lastInnovation = result.innovation[result.innovation.length - 1] || [];

  const cards = [
    ["\\(N\\)", N],
    ["\\(n\\)", n],
    ["\\(p\\)", p],
    ["\\(\\mathrm{tr}(P_{\\mathrm{final}})\\)", formatNumber(finalTrace)],
    ["\\(\\lVert \\nu_{\\mathrm{final}} \\rVert_2\\)", formatNumber(norm(lastInnovation))],
  ];

  if (Array.isArray(result.x_true)) {
    const rmse = estimateRmse(result.x_true, result.x_est);
    cards.push(["\\(\\mathrm{RMSE}_x\\)", formatNumber(rmse)]);
  }

  elements.metrics.innerHTML = cards
    .map(
      ([label, value]) =>
        `<article class="metric"><div class="label">${label}</div><div class="value">${value}</div></article>`
    )
    .join("");

  typesetMath(elements.metrics);
}

function renderPlots(result) {
  const k = result.time;
  const n = result.x_est[0].length;
  const p = result.measurements[0].length;

  const stateTraces = [];
  for (let i = 0; i < n; i += 1) {
    stateTraces.push({
      x: k,
      y: result.x_est.map((row) => row[i]),
      mode: "lines",
      name: `x̂[${i}]`,
      line: { width: 2 },
    });
  }

  if (Array.isArray(result.x_true)) {
    for (let i = 0; i < n; i += 1) {
      stateTraces.push({
        x: k,
        y: result.x_true.map((row) => row[i]),
        mode: "lines",
        name: `x real[${i}]`,
        line: { width: 1.8, dash: "dot" },
      });
    }
  }

  Plotly.newPlot("statesPlot", stateTraces, baseLayout("Estados reales vs estimados"), plotConfig());

  const outputTraces = [];
  for (let j = 0; j < p; j += 1) {
    outputTraces.push({
      x: k,
      y: result.measurements.map((row) => row[j]),
      mode: "markers",
      marker: { size: 6, opacity: 0.7 },
      name: `y medido[${j}]`,
    });
    outputTraces.push({
      x: k,
      y: result.y_est.map((row) => row[j]),
      mode: "lines",
      line: { width: 2.2 },
      name: `ŷ estimado[${j}]`,
    });
  }

  Plotly.newPlot("outputsPlot", outputTraces, baseLayout("Salida medida vs salida estimada"), plotConfig());

  const covTraces = [
    {
      x: k,
      y: result.P_trace,
      mode: "lines",
      name: "tr(P)",
      line: { width: 2.5 },
    },
  ];

  for (let i = 0; i < n; i += 1) {
    covTraces.push({
      x: k,
      y: result.P_diag.map((row) => row[i]),
      mode: "lines",
      name: `P[${i},${i}]`,
      line: { width: 1.8, dash: "dot" },
    });
  }

  Plotly.newPlot(
    "covPlot",
    covTraces,
    baseLayout("Evolución temporal de la covarianza del error"),
    plotConfig()
  );

  const innovationTraces = [];
  for (let j = 0; j < p; j += 1) {
    innovationTraces.push({
      x: k,
      y: result.innovation.map((row) => row[j]),
      mode: "lines",
      name: `innovación[${j}]`,
      line: { width: 1.9 },
    });
  }

  Plotly.newPlot("innovationPlot", innovationTraces, baseLayout("Innovación"), plotConfig());
}

function renderSteps(result) {
  const rows = [];
  const limit = Math.min(result.time.length, 10);

  for (let k = 0; k < limit; k += 1) {
    const innovation = result.innovation[k].map(formatNumber).join(", ");
    const gainCol = result.K[k].map((row) => formatNumber(row[0])).join(", ");
    rows.push(`
      <tr>
        <td>${k}</td>
        <td>${formatNumber(result.P_trace[k])}</td>
        <td>[${innovation}]</td>
        <td>[${gainCol}]</td>
      </tr>
    `);
  }

  elements.stepsTableBody.innerHTML = rows.join("");
}

function baseLayout(title) {
  return {
    title,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(242, 248, 255, 0.92)",
    font: {
      color: "#173956",
      family: "JetBrains Mono, monospace",
      size: 12,
    },
    margin: { t: 40, r: 15, b: 38, l: 48 },
    xaxis: {
      title: "k",
      gridcolor: "rgba(42, 101, 148, 0.18)",
      zerolinecolor: "rgba(42, 101, 148, 0.28)",
    },
    yaxis: {
      gridcolor: "rgba(42, 101, 148, 0.18)",
      zerolinecolor: "rgba(42, 101, 148, 0.28)",
    },
    legend: {
      orientation: "h",
      y: -0.25,
      x: 0,
    },
  };
}

function plotConfig() {
  return {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
  };
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return Number(value).toFixed(4);
}

function norm(vec) {
  if (!Array.isArray(vec)) {
    return NaN;
  }
  return Math.sqrt(vec.reduce((acc, val) => acc + val * val, 0));
}

function estimateRmse(truth, estimate) {
  let acc = 0;
  let count = 0;

  for (let i = 0; i < truth.length; i += 1) {
    for (let j = 0; j < truth[i].length; j += 1) {
      const err = truth[i][j] - estimate[i][j];
      acc += err * err;
      count += 1;
    }
  }

  return Math.sqrt(acc / Math.max(count, 1));
}

function typesetMath(node) {
  if (!window.MathJax || !node) {
    return;
  }
  if (typeof window.MathJax.typesetClear === "function") {
    window.MathJax.typesetClear([node]);
  }
  if (typeof window.MathJax.typesetPromise === "function") {
    window.MathJax.typesetPromise([node]).catch(() => {});
  }
}
