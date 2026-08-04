"use strict";

const form = document.querySelector("#scan-form");
const submitButton = document.querySelector("#submit-button");
const progressSection = document.querySelector("#progress-section");
const progressMessage = document.querySelector("#progress-message");
const progressTrack = document.querySelector("[role='progressbar']");
const progressBar = document.querySelector("#progress-bar");
const errorSection = document.querySelector("#error-section");
const errorMessage = document.querySelector("#error-message");
const resultsArticle = document.querySelector("#results");

const text = (tag, value, className) => {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
};

const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };

function statusClass(status) {
  if (status === "risque élevé") return "risk";
  if (status === "à surveiller") return "watch";
  if (status === "donnée insuffisante") return "insufficient";
  if (status === "erreur technique" || status === "non évalué") return "error";
  return "good";
}

function setProgress(job) {
  progressMessage.textContent = job.message;
  progressBar.style.width = `${job.progress}%`;
  progressTrack.setAttribute("aria-valuenow", String(job.progress));
  document.querySelectorAll(".progress-steps li").forEach((item) => {
    item.classList.toggle("active", item.dataset.stage === job.stage || job.progress === 100);
  });
}

function appendList(target, items, emptyMessage) {
  clear(target);
  if (!items.length) {
    target.append(text("li", emptyMessage));
    return;
  }
  items.forEach((item) => target.append(text("li", item)));
}

function renderDetails(target, axes, field, emptyMessage) {
  clear(target);
  Object.values(axes).forEach((axis) => {
    if (!axis[field].length) return;
    const details = document.createElement("details");
    const summary = text("summary", `${axis.key} — ${axis.label}`);
    details.append(summary);
    axis[field].forEach((item) => {
      if (field === "evidence") {
        const code = text("code", JSON.stringify(item, null, 2));
        details.append(code);
      } else {
        details.append(text("p", item));
      }
    });
    target.append(details);
  });
  if (!target.childElementCount) target.append(text("p", emptyMessage));
}

function renderResult(job) {
  const data = job.result;
  const summary = data.summary;
  const profileLabel = job.profile === "loi25" ? "Diagnostic technique Loi 25" : "Diagnostic multidimensionnel";
  const scanState = summary.status === "partial" ? "scan partiel" : "scan terminé";
  document.querySelector("#result-context").textContent = `${data.domain} · ${data.meta.mode} · ${profileLabel} · ${scanState} · ${summary.evaluated_axes}/${summary.total_axes} axes`;

  const reliability = document.querySelector("#reliability");
  clear(reliability);
  [
    [summary.coverage.toLocaleString("fr-CA", {style: "percent", maximumFractionDigits: 0}), "Couverture pondérée"],
    [String(summary.reliability_factor), "Facteur de fiabilité"],
    [`${summary.technical_score}/10`, "Score technique"],
  ].forEach(([value, label]) => {
    const metric = text("div", "", "metric");
    metric.append(text("strong", value), text("span", label));
    reliability.append(metric);
  });

  const score = document.querySelector("#global-score");
  clear(score);
  score.append(document.createTextNode(`${summary.score}/10`), text("small", summary.grade));

  const axesTarget = document.querySelector("#axis-scores");
  clear(axesTarget);
  Object.values(data.axes).forEach((axis) => {
    const row = text("div", "", "axis-row");
    if (job.profile === "loi25" && ["S", "I", "V", "L"].includes(axis.key)) {
      row.classList.add("profile-highlight");
    }
    row.append(
      text("strong", `${axis.key} — ${axis.label}`),
      text("span", axis.score === null ? "—" : `${axis.score}/10`, "axis-score"),
      text("span", axis.coverage.toLocaleString("fr-CA", {style: "percent", maximumFractionDigits: 0})),
      text("span", axis.status, `status ${statusClass(axis.status)}`),
    );
    axesTarget.append(row);
  });

  const issues = data.priority_issues.map((issue) => `${issue.axis} — ${issue.label} : ${issue.risk}`);
  appendList(document.querySelector("#priority-issues"), issues, "Aucun risque prioritaire observé dans les données disponibles.");
  renderDetails(document.querySelector("#observations"), data.axes, "observations", "Aucune observation disponible.");
  renderDetails(document.querySelector("#evidence"), data.axes, "evidence", "Aucune preuve structurée disponible.");

  const recommendations = Object.values(data.axes).flatMap((axis) => axis.recommendations.map((item) => `${axis.key} — ${item}`));
  appendList(document.querySelector("#recommendations"), recommendations, "Aucune recommandation supplémentaire.");
  const limits = data.limitations.concat(Object.values(data.axes).flatMap((axis) => axis.limitations.map((item) => `${axis.key} — ${item}`)));
  appendList(document.querySelector("#limits"), limits, "Aucune limite déclarée.");

  const downloads = document.querySelector("#download-links");
  clear(downloads);
  const labels = {json: "JSON", markdown: "Markdown", pdf: "PDF"};
  Object.entries(job.downloads).forEach(([kind, href]) => {
    const link = text("a", labels[kind]);
    link.href = href;
    link.setAttribute("download", "");
    downloads.append(link);
  });

  progressSection.hidden = true;
  resultsArticle.hidden = false;
  resultsArticle.scrollIntoView({behavior: "smooth", block: "start"});
  resultsArticle.focus({preventScroll: true});
}

function showError(message) {
  progressSection.hidden = true;
  resultsArticle.hidden = true;
  errorMessage.textContent = message;
  errorSection.hidden = false;
  errorSection.focus();
  submitButton.disabled = false;
}

async function poll(jobId) {
  for (;;) {
    const response = await fetch(`/api/scans/${jobId}`, {headers: {"Accept": "application/json"}});
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "Analyse introuvable");
    setProgress(job);
    if (job.status === "complete") { renderResult(job); submitButton.disabled = false; return; }
    if (job.status === "failed") {
      const detail = job.errors ? Object.values(job.errors).join(" · ") : job.message;
      showError(detail); return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 700));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  errorSection.hidden = true;
  resultsArticle.hidden = true;
  progressSection.hidden = false;
  setProgress({message: "Validation de la cible", progress: 3, stage: "validation"});
  const values = new FormData(form);
  try {
    const response = await fetch("/api/scans", {
      method: "POST",
      headers: {"Content-Type": "application/json", "Accept": "application/json"},
      body: JSON.stringify({url: values.get("url"), mode: values.get("mode"), profile: values.get("profile")}),
    });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "Le scan ne peut pas démarrer");
    await poll(job.id);
  } catch (error) {
    showError(error instanceof Error ? error.message : "Erreur technique inconnue");
  }
});

document.querySelector("#restart").addEventListener("click", () => {
  resultsArticle.hidden = true;
  form.scrollIntoView({behavior: "smooth", block: "center"});
  document.querySelector("#scan-url").focus();
});
document.querySelector("#error-retry").addEventListener("click", () => {
  errorSection.hidden = true;
  document.querySelector("#scan-url").focus();
});
