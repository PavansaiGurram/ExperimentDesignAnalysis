"use strict";

const numberFormat = new Intl.NumberFormat();
const percent = (value) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const signedPercent = (value) => value == null ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`;
const pValue = (value) => value == null ? "—" : value < 0.001 ? "<0.001" : value.toFixed(3);

function badge(status) {
  const classes = {
    evaluated: "badge-good",
    guardrail_fail: "badge-bad",
    blocked_srm: "badge-bad",
    pass: "badge-good",
    fail: "badge-bad",
    inconclusive: "badge-neutral",
    not_applicable: "badge-neutral",
  };
  const labels = {
    evaluated: "Evaluated",
    guardrail_fail: "Guardrail fail",
    blocked_srm: "Blocked · SRM",
    not_applicable: "N/A",
  };
  const safeStatus = String(status || "unknown");
  return `<span class="badge ${classes[safeStatus] || "badge-neutral"}">${labels[safeStatus] || safeStatus.replaceAll("_", " ")}</span>`;
}

function renderRow(experiment) {
  const result = experiment.result;
  const effectClass = result.effect > 0 ? "effect-positive" : result.effect < 0 ? "effect-negative" : "";
  const interval = `[${signedPercent(result.ci_lower)}, ${signedPercent(result.ci_upper)}]`;
  return `<tr tabindex="0" data-id="${experiment.experiment_id}" aria-selected="false">
    <td>${experiment.name}<span class="experiment-id">${experiment.experiment_id}</span></td>
    <td>${experiment.primary_metric}</td>
    <td class="${effectClass}">${signedPercent(result.effect)}</td>
    <td>${interval}</td>
    <td>${badge(result.result_status)}</td>
    <td>${experiment.guardrail ? badge(experiment.guardrail.status) : "—"}</td>
  </tr>`;
}

function renderDetail(experiment) {
  const result = experiment.result;
  const detail = document.querySelector("#detail");
  detail.innerHTML = `<div class="detail-content">
    <p class="eyebrow">${experiment.experiment_id} · ${experiment.scenario.replaceAll("_", " ")}</p>
    <h2>${experiment.name}</h2>
    <p class="hypothesis">${experiment.hypothesis}</p>
    <div class="detail-grid">
      <div class="detail-metric"><span>Control conversion</span><strong>${percent(result.control_rate)}</strong><span>${numberFormat.format(result.control_events)} / ${numberFormat.format(result.control_n)} members</span></div>
      <div class="detail-metric"><span>Treatment conversion</span><strong>${percent(result.treatment_rate)}</strong><span>${numberFormat.format(result.treatment_events)} / ${numberFormat.format(result.treatment_n)} members</span></div>
      <div class="detail-metric"><span>Estimated effect</span><strong>${signedPercent(result.effect)}</strong><span>95% CI ${signedPercent(result.ci_lower)} to ${signedPercent(result.ci_upper)}</span></div>
      <div class="detail-metric"><span>Statistical check</span><strong>p = ${pValue(result.p_value)}</strong><span>SRM p = ${pValue(result.srm_p_value)}</span></div>
    </div>
    <p class="detail-foot">Intention-to-treat population · ${numberFormat.format(result.eligible_n)} eligible · ${result.excluded_assignment_n} excluded assignment(s) · Guardrail: ${experiment.guardrail ? experiment.guardrail.name + " — " + experiment.guardrail.status.replaceAll("_", " ") : "not available"}</p>
  </div>`;
}

function render(data) {
  const { summary, experiments } = data;
  document.querySelector("#scale-label").textContent = data.scale;
  document.querySelector("#stat-experiments").textContent = numberFormat.format(summary.experiment_count);
  document.querySelector("#stat-audience").textContent = numberFormat.format(summary.eligible_audience_members);
  document.querySelector("#stat-blocked").textContent = numberFormat.format(summary.result_status_counts.blocked_srm || 0);
  document.querySelector("#stat-checks").textContent = numberFormat.format(summary.checks.filter((check) => check.passed).length);

  const tbody = document.querySelector("#experiments-body");
  const search = document.querySelector("#search");
  const drawRows = () => {
    const previousSelectionId = tbody.querySelector('tr[aria-selected="true"]')?.dataset.id;
    const query = search.value.trim().toLowerCase();
    const matches = experiments.filter((item) => `${item.name} ${item.experiment_id} ${item.primary_metric}`.toLowerCase().includes(query));
    tbody.innerHTML = matches.length ? matches.map(renderRow).join("") : '<tr><td colspan="6" class="loading">No matching experiments.</td></tr>';
    tbody.querySelectorAll("tr[data-id]").forEach((row) => {
      const select = () => {
        tbody.querySelectorAll("tr[data-id]").forEach((item) => item.setAttribute("aria-selected", "false"));
        row.setAttribute("aria-selected", "true");
        renderDetail(experiments.find((item) => item.experiment_id === row.dataset.id));
      };
      row.addEventListener("click", select);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
    });
    const nextSelection = previousSelectionId
      ? tbody.querySelector(`tr[data-id="${previousSelectionId}"]`)
      : null;
    const rowToSelect = nextSelection || tbody.querySelector("tr[data-id]");
    if (rowToSelect) {
      rowToSelect.click();
    } else {
      document.querySelector("#detail").innerHTML = '<div class="detail-empty"><span class="detail-icon">↗</span><div><h2>No experiment selected</h2><p>Change your search to see experiment results.</p></div></div>';
    }
  };
  search.addEventListener("input", drawRows);
  drawRows();
}

fetch("/api/dashboard")
  .then((response) => {
    if (!response.ok) throw new Error(`Dashboard API returned HTTP ${response.status}`);
    return response.json();
  })
  .then(render)
  .catch((error) => {
    document.querySelector("#experiments-body").innerHTML = '<tr><td colspan="6" class="loading">Experiment data could not be loaded.</td></tr>';
    const message = document.querySelector("#error-message");
    message.textContent = `${error.message}. Try restarting the app with: python app.py`;
    message.hidden = false;
  });
