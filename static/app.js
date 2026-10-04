const VIEWS = ["practice", "learn", "weaknesses", "progress"];
const VIEW_LABELS = { practice: "Practice", learn: "Learn", weaknesses: "Weak spots", progress: "Progress" };
const LEVELS = ["Foundations", "Intermediate", "Advanced"];
const TIPS = {
  Theory: [
    "Lead with a one-sentence definition, then explain the <em>trade-off</em>.",
    "Name an edge case or a common pitfall. Interviewers listen for it.",
    "A tiny concrete example beats an abstract paragraph.",
  ],
  Coding: [
    "State time and space complexity <em>before</em> you are asked.",
    "Say how you would test it: empty input, one item, duplicates.",
    "Name the data structure first, then write the loop.",
  ],
};

const state = {
  question: null,
  searchUrl: "",
  searchQuery: "",
  searchOpened: false,
  reviewOnly: false,
  targetQuestionId: null,
  questionSaved: false,
  editor: null,
  editorFailed: false,
  timerStart: 0,
  timerId: 0,
  session: { count: 0, scores: [] },
  dashboard: null,
  lessons: [],
  lessonFilter: "all",
  selectedLessonId: null,
};
// Unsaved note text, keyed by lesson id, so re-rendering never discards typing.
const noteDrafts = new Map();

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const icon = (name, extra = "") => `<svg class="icon ${extra}"><use href="#i-${name}"/></svg>`;
const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
const formatScore = (value) => (value === null || value === undefined ? "–" : Number(value).toFixed(Number.isInteger(Number(value)) ? 0 : 1));
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch (_error) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (_error) { /* storage unavailable */ } },
};

const NETWORK_ERROR_MESSAGE = "Could not reach the app. Check that it is still running, then try again.";
const SERVER_ERROR_MESSAGE = "Something went wrong. Try again.";

class RequestError extends Error {
  constructor(message, kind, status) {
    super(message);
    this.name = "RequestError";
    this.kind = kind; // "network" | "server"
    this.status = status; // HTTP status, 0 for network
  }
}

async function request(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error && error.name === "AbortError") throw error;
    if (error instanceof TypeError) throw new RequestError(NETWORK_ERROR_MESSAGE, "network", 0);
    throw error;
  }
  if (response.ok) return response;
  const data = await response.json().catch(() => null);
  const message = data && typeof data.error === "string" && data.error ? data.error : SERVER_ERROR_MESSAGE;
  throw new RequestError(message, "server", response.status);
}

async function requestJson(url, options = {}) {
  const response = await request(url, options);
  return response.json().catch(() => ({}));
}

async function requestBlob(url, options = {}) {
  const response = await request(url, options);
  try {
    return await response.blob();
  } catch (_error) {
    throw new RequestError(NETWORK_ERROR_MESSAGE, "network", 0);
  }
}
const postJson = (url, body) => requestJson(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}),
});

let toastTimer = 0;
function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

function showError(id, message) {
  const element = byId(id);
  element.textContent = message || "";
  element.classList.toggle("hidden", !message);
}

/* ---------- Theme ---------- */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const button = byId("theme-toggle");
  const dark = theme === "dark";
  button.innerHTML = `${icon(dark ? "sun" : "moon")}<span>${dark ? "Light theme" : "Dark theme"}</span>`;
  button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
}
byId("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  storage.set("preparator-theme", next);
  applyTheme(next);
  if (state.dashboard) renderProgress(state.dashboard);
});
applyTheme(document.documentElement.dataset.theme || "light");

/* ---------- Navigation ---------- */
function setView(name) {
  VIEWS.forEach((view) => byId(`${view}-view`).classList.toggle("active", view === name));
  document.querySelectorAll("[data-view]").forEach((item) => {
    const active = item.dataset.view === name;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  byId("crumb-view").textContent = VIEW_LABELS[name];
  if (location.hash.slice(1) !== name) history.pushState(null, "", `#${name}`);
  if (name === "weaknesses" || name === "progress") refreshDashboard();
  if (name === "learn") refreshTheory();
  hideTooltip();
}
document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => setView(item.dataset.view)));
// Brand link: route to Practice without a page load (keeps the answer draft and session stats).
document.querySelector(".brand").addEventListener("click", (event) => {
  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  setView("practice");
});

/* ---------- Practice: filters ---------- */
function readFilters() {
  return {
    topic: byId("topic-select").value,
    difficulty: byId("difficulty-select").value,
    mode: byId("mode-select").value,
  };
}

function restoreFilters() {
  try {
    const saved = JSON.parse(storage.get("preparator-filters") || "{}");
    if (saved.difficulty) byId("difficulty-select").value = saved.difficulty;
    if (saved.mode) byId("mode-select").value = saved.mode;
    return saved;
  } catch (_error) {
    return {};
  }
}
const savedFilters = restoreFilters();

function populateTopics(topics) {
  const select = byId("topic-select");
  const current = select.value !== "All topics" ? select.value : savedFilters.topic;
  select.innerHTML = ["All topics", ...topics].map((topic) => `<option>${escapeHtml(topic)}</option>`).join("");
  if (current && topics.includes(current)) select.value = current;
}

["topic-select", "difficulty-select", "mode-select"].forEach((id) => byId(id).addEventListener("change", () => {
  storage.set("preparator-filters", JSON.stringify(readFilters()));
  // A search opened for the old filters no longer matches; ask for a fresh one.
  if (!state.question && state.searchOpened) resetSearchGate();
  clearReviewTarget();
  if (state.question) showToast("New filters apply to your next question.");
}));

/* ---------- Practice: state machine ---------- */
function showState(name) {
  ["intro", "loading", "question"].forEach((stateName) => byId(`state-${stateName}`).classList.toggle("hidden", stateName !== name));
}

function setStep(step) {
  ["search", "answer", "review"].forEach((name, index) => {
    const item = byId(`step-${name}`);
    item.classList.toggle("current", index + 1 === step);
    item.classList.toggle("done", index + 1 < step);
  });
}

function clearReviewTarget() {
  state.targetQuestionId = null;
  state.reviewOnly = false;
}

function resetSearchGate() {
  clearReviewTarget();
  state.searchOpened = false;
  byId("reveal-button").classList.add("hidden");
  byId("search-button").querySelector("span").textContent = "Open interview search";
}

function showIntro() {
  state.question = null;
  stopTimer();
  resetSearchGate();
  setStep(1);
  showState("intro");
  showError("intro-error", "");
  byId("session-label").textContent = state.session.count ? `${plural(state.session.count, "question")} this session` : "No question yet";
}

function openSearch() {
  const filters = readFilters();
  const topic = filters.topic === "All topics" ? "Google Meta Amazon" : filters.topic;
  const level = filters.difficulty === "Any level" ? "" : filters.difficulty;
  const mode = filters.mode === "Any mode" ? "theory coding" : filters.mode;
  state.searchQuery = `Python interview questions ${topic} ${level} ${mode} ${new Date().getFullYear()}`.replace(/\s+/g, " ").trim();
  state.searchUrl = `https://www.google.com/search?q=${encodeURIComponent(state.searchQuery)}`;
  window.open(state.searchUrl, "_blank", "noopener,noreferrer");
  state.searchOpened = true;
  byId("search-button").querySelector("span").textContent = "Open search again";
  byId("reveal-button").classList.remove("hidden");
  byId("reveal-button").focus();
}

async function revealQuestion() {
  if (!state.searchOpened) return;
  showState("loading");
  try {
    // Review mode (weak spots or a targeted question) ignores the Practice filters (ADR-007).
    const reviewing = state.reviewOnly || state.targetQuestionId !== null;
    const data = await postJson("/api/question", {
      ...(reviewing ? {} : readFilters()),
      weak_only: state.reviewOnly,
      question_id: state.targetQuestionId ?? undefined,
      source_confirmed: true,
      source_url: state.searchUrl,
      search_query: state.searchQuery,
    });
    clearReviewTarget();
    await renderQuestion(data.question);
  } catch (error) {
    showState("intro");
    showError("intro-error", error.message);
  }
}

byId("search-button").addEventListener("click", () => {
  // A fresh (non-review) search must not inherit an abandoned review target.
  if (!state.searchOpened) clearReviewTarget();
  openSearch();
});
byId("reveal-button").addEventListener("click", revealQuestion);

/* ---------- Practice: answering ---------- */
const isCoding = () => state.question?.mode === "Coding";

async function ensureEditor() {
  if (state.editor || state.editorFailed) return state.editor;
  try {
    const { createCodeEditor } = await import("./editor.js");
    state.editor = createCodeEditor(byId("code-editor"), { onSubmit: submitAnswer, onChange: updateAnswerLength });
  } catch (error) {
    console.warn("Code editor unavailable; using plain text box.", error);
    state.editorFailed = true;
  }
  return state.editor;
}

function getAnswer() {
  return isCoding() && state.editor ? state.editor.getValue() : byId("answer-input").value;
}

async function renderQuestion(question) {
  state.question = question;
  state.questionSaved = false;
  state.session.count += 1;
  const coding = question.mode === "Coding";
  const editor = coding ? await ensureEditor() : null;
  const useEditor = Boolean(editor);

  byId("question-tags").innerHTML = [question.topic, question.difficulty, question.mode].map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
  byId("question-text").textContent = question.prompt;
  byId("source-link").href = state.searchUrl;
  byId("answer-type-label").textContent = coding ? "Python code" : "Your answer";
  byId("submit-button").querySelector("span").textContent = coding ? "Submit code" : "Submit answer";

  const textarea = byId("answer-input");
  textarea.classList.toggle("hidden", useEditor);
  textarea.classList.toggle("code-mode", coding && !useEditor);
  textarea.spellcheck = !coding;
  textarea.placeholder = coding ? "Write your Python solution here…" : "Talk through your reasoning. Be specific about trade-offs and edge cases…";
  textarea.value = coding && !useEditor ? question.starter_code || "" : "";
  byId("code-editor").classList.toggle("hidden", !useEditor);
  if (useEditor) editor.setValue(question.starter_code || "");
  byId("editor-hint").textContent = coding
    ? "Tab indents. Press Esc then Tab to leave the editor. Lines left unchanged from the starter earn no credit."
    : "Aim for a definition, a trade-off, and an example.";

  const tips = TIPS[question.mode] || TIPS.Theory;
  byId("tip-text").innerHTML = tips[Math.floor(Math.random() * tips.length)];
  byId("session-label").textContent = `Question ${state.session.count}`;
  setSavedButtons(false);
  showError("answer-error", "");
  byId("answer-area").classList.remove("hidden");
  byId("feedback").classList.add("hidden");
  setStep(2);
  showState("question");
  updateAnswerLength();
  startTimer();
  announce(`New question: ${question.topic}, ${question.difficulty}, ${question.mode}`);
  (useEditor ? editor : textarea).focus();
}

// Polite status message for screen readers (separate from the word count).
let announceTimer;
function announce(message) {
  const region = byId("practice-status");
  region.textContent = "";
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => { region.textContent = message; }, 50);
}

function updateAnswerLength() {
  const text = getAnswer();
  if (isCoding()) {
    const lines = text ? text.split("\n").length : 0;
    byId("word-count").textContent = plural(lines, "line");
  } else {
    byId("word-count").textContent = plural(text.trim().split(/\s+/).filter(Boolean).length, "word");
  }
}

const answerInput = byId("answer-input");
answerInput.addEventListener("input", updateAnswerLength);
// Esc in the fallback code textarea releases Tab until blur or another keystroke (WCAG 2.1.2).
let tabReleased = false;
answerInput.addEventListener("blur", () => { tabReleased = false; });
answerInput.addEventListener("keydown", (event) => {
  if (event.isComposing) return;
  const codeMode = answerInput.classList.contains("code-mode");
  if (codeMode && event.key === "Escape") {
    tabReleased = true;
    return;
  }
  if (event.key === "Tab" && tabReleased) {
    tabReleased = false;
    return; // let focus move on
  }
  if (!["Tab", "Shift", "Control", "Alt", "Meta"].includes(event.key)) tabReleased = false;
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    submitAnswer();
  } else if (event.key === "Tab" && codeMode) {
    // Fallback editor only: insert spaces instead of moving focus.
    event.preventDefault();
    answerInput.setRangeText("    ", answerInput.selectionStart, answerInput.selectionEnd, "end");
    updateAnswerLength();
  }
});

async function submitAnswer() {
  const button = byId("submit-button");
  if (!state.question || button.getAttribute("aria-busy") === "true") return;
  const answer = getAnswer();
  if (!answer.trim()) return showError("answer-error", "Add your answer first.");
  button.setAttribute("aria-busy", "true");
  showError("answer-error", "");
  try {
    const result = await postJson("/api/answer", { question_id: state.question.id, answer });
    stopTimer();
    renderFeedback(result, answer);
    state.session.scores.push(result.score);
    renderSessionStats();
    refreshDashboard();
  } catch (error) {
    showError("answer-error", error.message);
  } finally {
    button.removeAttribute("aria-busy");
  }
}
byId("submit-button").addEventListener("click", submitAnswer);

function renderFeedback(result, answer) {
  const items = [
    ...result.matched.map((label) => ({ label, covered: true })),
    ...result.missing.map((label) => ({ label, covered: false })),
  ];
  byId("concept-list").innerHTML = items.map(({ label, covered }) => `
    <li class="${covered ? "covered" : "missed"}">${icon(covered ? "check" : "x")}
      <span>${escapeHtml(label)}<small>${covered ? "Covered" : "Not mentioned. Revisit this"}</small></span></li>`).join("");
  byId("score-pill").textContent = `Rubric match ${result.score}/10`;
  byId("feedback-note").textContent = result.feedback_note;
  byId("explanation-text").textContent = result.explanation;
  byId("your-answer").textContent = answer;
  byId("solution-text").textContent = result.solution;
  byId("compare-summary").textContent = isCoding() ? "Compare your code with the model solution" : "Compare with the model answer";
  byId("compare-block").open = isCoding();
  byId("answer-area").classList.add("hidden");
  byId("feedback").classList.remove("hidden");
  setStep(3);
  byId("feedback-heading").focus({ preventScroll: true });
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  byId("feedback").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
  announce(`Rubric match ${result.score} out of 10`);
}

function renderSessionStats() {
  const { scores } = state.session;
  byId("session-answered").textContent = scores.length;
  byId("session-average").textContent = scores.length ? formatScore(scores.reduce((a, b) => a + b, 0) / scores.length) : "–";
}

function setSavedButtons(saved) {
  state.questionSaved = saved;
  ["save-question-button", "feedback-save-button"].forEach((id) => {
    const button = byId(id);
    button.setAttribute("aria-pressed", String(saved));
    button.querySelector("span").textContent = saved ? "Saved for review" : "Save for review";
  });
}

async function saveForReview() {
  if (!state.question || state.questionSaved) return;
  try {
    await postJson(`/api/weakness/${state.question.id}`, {});
    setSavedButtons(true);
    showToast("Saved to your weak spots.");
    refreshDashboard();
  } catch (error) {
    showToast(error.message || "Could not save this question.");
  }
}
byId("save-question-button").addEventListener("click", saveForReview);
byId("feedback-save-button").addEventListener("click", saveForReview);

function nextQuestion() {
  showIntro();
  openSearch();
}
byId("next-button").addEventListener("click", nextQuestion);

/* ---------- Timer ---------- */
function startTimer() {
  stopTimer();
  state.timerStart = Date.now();
  const timer = byId("question-timer");
  timer.classList.remove("hidden");
  const tick = () => {
    const seconds = Math.floor((Date.now() - state.timerStart) / 1000);
    timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  };
  tick();
  state.timerId = setInterval(tick, 1000);
}
function stopTimer() { clearInterval(state.timerId); }

/* ---------- Weak spots ---------- */
function weakStatus(question) {
  const misses = question.miss_count ? `Missed ${plural(question.miss_count, "time")} · latest match ${question.last_score}/10` : "";
  if (!question.pinned) return misses;
  return misses ? `Saved by you · ${misses}` : "Saved by you · not attempted yet";
}

function startReview({ questionId = null, weakOnly = false } = {}) {
  setView("practice");
  showIntro();
  state.targetQuestionId = questionId;
  state.reviewOnly = weakOnly;
  openSearch();
}

byId("review-weak-button").addEventListener("click", () => startReview({ weakOnly: true }));
byId("weakness-list").addEventListener("click", async (event) => {
  const practice = event.target.closest("[data-practice-id]");
  if (practice) return startReview({ questionId: Number(practice.dataset.practiceId) });
  const remove = event.target.closest("[data-remove-id]");
  if (!remove) return;
  try {
    await requestJson(`/api/weakness/${remove.dataset.removeId}`, { method: "DELETE" });
    showToast("Removed from your review queue.");
    refreshDashboard();
  } catch (error) {
    showToast(error.message || "Could not update your review queue.");
  }
});

function renderWeakSpots(data) {
  byId("weakness-summary").textContent = data.weak_count
    ? `${plural(data.weak_count, "question")} to revisit`
    : "Your review queue is clear. Save a question or miss a rubric concept to add one.";
  byId("review-weak-button").disabled = data.weak_count === 0;
  byId("weakness-list").innerHTML = data.weak_questions.length ? data.weak_questions.map((question) => `
    <article class="card weak-card">
      <div>
        <div class="tags"><span>${escapeHtml(question.topic)}</span><span>${escapeHtml(question.difficulty)}</span><span>${escapeHtml(question.mode)}</span></div>
        <h2>${escapeHtml(question.prompt)}</h2>
        <p>${escapeHtml(weakStatus(question))}</p>
      </div>
      <div class="weak-actions">
        <button class="btn btn-secondary" data-practice-id="${question.id}" type="button">Practice this one ${icon("arrow")}</button>
        <button class="icon-button" data-remove-id="${question.id}" type="button" aria-label="Remove from review queue" title="Remove from review queue">${icon("x")}</button>
      </div>
    </article>`).join("") : "<div class='empty-state'>No weak spots yet. Your honest answers will build a useful review list.</div>";
}

/* ---------- Dashboard ---------- */
async function refreshDashboard() {
  try {
    const data = await requestJson("/api/dashboard");
    state.dashboard = data;
    populateTopics(data.topics.map((topic) => topic.topic));
    byId("attempt-count").textContent = data.attempts;
    byId("weak-count").textContent = data.weak_count;
    byId("bank-count").textContent = `${data.question_count} prompts in the bank.`;
    byId("rail-average").textContent = data.attempts ? formatScore(data.average) : "–";
    byId("rail-weak").textContent = data.weak_count;
    byId("rail-progress-fill").style.width = `${(data.average || 0) * 10}%`;
    byId("streak-value").textContent = data.streak ? `${data.streak}-day streak` : "No streak yet";
    byId("streak-chip").classList.toggle("active", data.streak > 0);
    renderWeakSpots(data);
    renderProgress(data);
  } catch (_error) {
    showToast("Could not refresh your progress.");
  }
}

/* ---------- Progress ---------- */
const tooltip = byId("chart-tooltip");
function showTooltip(html, x, y) {
  tooltip.innerHTML = html;
  tooltip.classList.remove("hidden");
  const { width, height } = tooltip.getBoundingClientRect();
  const left = Math.min(Math.max(8, x + 14), window.innerWidth - width - 8);
  const top = y - height - 12 < 8 ? y + 16 : y - height - 12;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}
function hideTooltip() { tooltip.classList.add("hidden"); }

const shortDate = (day) => new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function renderProgress(data) {
  byId("progress-attempts").textContent = data.attempts;
  byId("progress-average").innerHTML = `${data.attempts ? formatScore(data.average) : "–"}<small>/10</small>`;
  byId("progress-streak").textContent = data.streak;
  byId("progress-weak").textContent = data.weak_count;
  renderTrend(data.trend);
  renderMatrix(data.matrix);
  byId("recent-list").innerHTML = data.recent.length ? data.recent.map((attempt) => `
    <div class="recent-row"><div><b>${escapeHtml(attempt.topic)}</b><span>${escapeHtml(attempt.prompt.split("\n")[0])}</span></div>
    <strong>${attempt.score}<small>/10</small></strong></div>`).join("") : "<div class='chart-empty'>Your submitted answers will appear here.</div>";
}

function renderTrend(trend) {
  const chart = byId("trend-chart");
  byId("trend-table").innerHTML = trend.length ? `<table class="data-table"><thead><tr><th>Day</th><th>Avg match</th><th>Answers</th></tr></thead><tbody>${
    trend.map((row) => `<tr><td>${escapeHtml(shortDate(row.day))}</td><td>${formatScore(row.average)}/10</td><td>${row.attempts}</td></tr>`).join("")
  }</tbody></table>` : "";
  if (!trend.length) {
    chart.innerHTML = "<div class='chart-empty'>Answer a few questions to see your trend.</div>";
    return;
  }
  // Draw at the container's real width so axis text stays 11px on phones.
  const width = Math.max(280, Math.round(chart.clientWidth || 640)), height = 220, left = 34, right = 14, top = 12, bottom = 28;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const x = (index) => left + (trend.length === 1 ? plotWidth / 2 : (index / (trend.length - 1)) * plotWidth);
  const y = (score) => top + plotHeight - (score / 10) * plotHeight;
  const points = trend.map((row, index) => [x(index), y(row.average)]);
  const path = points.map(([px, py], index) => `${index ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
  const area = `${path}L${points.at(-1)[0].toFixed(1)},${y(0)}L${points[0][0].toFixed(1)},${y(0)}Z`;
  const labelIndexes = [...new Set([0, Math.floor((trend.length - 1) / 2), trend.length - 1])];
  const step = trend.length === 1 ? plotWidth : plotWidth / (trend.length - 1);
  const anchor = (index) => (trend.length === 1 ? "middle" : index === 0 ? "start" : index === trend.length - 1 ? "end" : "middle");
  chart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Average rubric match per practice day, ${trend.length} days">
      ${[0, 5, 10].map((tick) => `<line class="grid-line" x1="${left}" x2="${width - right}" y1="${y(tick)}" y2="${y(tick)}"/><text class="axis-label" x="${left - 8}" y="${y(tick) + 4}" text-anchor="end">${tick}</text>`).join("")}
      ${labelIndexes.map((index) => `<text class="axis-label" x="${x(index)}" y="${height - 6}" text-anchor="${anchor(index)}">${escapeHtml(shortDate(trend[index].day))}</text>`).join("")}
      ${trend.length > 1 ? `<path class="area" d="${area}"/><path class="line" d="${path}"/>` : ""}
      <line class="crosshair hidden" id="trend-crosshair" y1="${top}" y2="${y(0)}"/>
      ${points.map(([px, py]) => `<circle class="dot" cx="${px}" cy="${py}" r="4"/>`).join("")}
      ${points.map(([px], index) => `<rect class="hit" data-index="${index}" x="${px - step / 2}" y="${top}" width="${step}" height="${plotHeight}"/>`).join("")}
    </svg>`;
  const crosshair = chart.querySelector("#trend-crosshair");
  chart.querySelectorAll(".hit").forEach((hit) => {
    hit.addEventListener("pointermove", (event) => {
      const index = Number(hit.dataset.index);
      const row = trend[index];
      crosshair.setAttribute("x1", points[index][0]);
      crosshair.setAttribute("x2", points[index][0]);
      crosshair.classList.remove("hidden");
      showTooltip(`<b>${escapeHtml(shortDate(row.day))}</b>Avg match ${formatScore(row.average)}/10 · ${plural(row.attempts, "answer")}`, event.clientX, event.clientY);
    });
    hit.addEventListener("pointerleave", () => { crosshair.classList.add("hidden"); hideTooltip(); });
  });
}

function renderMatrix(matrix) {
  const topics = [...new Set(matrix.map((row) => row.topic))].sort();
  const lookup = new Map(matrix.map((row) => [`${row.topic}|${row.difficulty}`, row]));
  const tipAttrs = (topic, level, body) => `data-tip-title="${escapeHtml(`${topic} · ${level}`)}" data-tip-body="${escapeHtml(body)}"`;
  const rows = topics.map((topic) => `
    <tr><th scope="row" class="row-head">${escapeHtml(topic)}</th>
    ${LEVELS.map((level) => {
      const row = lookup.get(`${topic}|${level}`);
      if (!row) return `<td class="cell empty"><span aria-hidden="true">–</span><span class="visually-hidden">No questions</span></td>`;
      if (!row.attempts) return `<td class="cell empty" ${tipAttrs(topic, level, "Not practiced yet")}><span aria-hidden="true">not yet</span><span class="visually-hidden">Not attempted</span></td>`;
      const strength = Math.round(12 + row.average * 8.8);
      // Strong cells are dark in light mode and bright in dark mode, so the text flips at different points.
      const invert = document.documentElement.dataset.theme === "dark" ? strength > 55 : strength > 75;
      const body = `Avg match ${formatScore(row.average)}/10 · ${plural(row.attempts, "answer")}`;
      return `<td class="cell ${invert ? "invert-text" : ""}" style="background: color-mix(in oklab, var(--chart) ${strength}%, var(--surface))" ${tipAttrs(topic, level, body)}><span><b>${formatScore(row.average)}</b><span class="visually-hidden"> average match out of 10, </span><small>${plural(row.attempts, "try")}</small></span></td>`;
    }).join("")}</tr>`).join("");
  byId("matrix-chart").innerHTML = `
    <table class="matrix">
      <caption class="visually-hidden">Average keyword-match score and number of tries, by topic and level</caption>
      <colgroup><col class="matrix-topic-col"><col span="${LEVELS.length}"></colgroup>
      <thead><tr><td></td>${LEVELS.map((level) => `<th scope="col" class="head"><span aria-hidden="true">${escapeHtml(level.slice(0, 5))}.</span><span class="visually-hidden">${escapeHtml(level)}</span></th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="matrix-legend"><span>0</span><i></i><span>10 avg match</span></div>`;
}

byId("matrix-chart").addEventListener("pointermove", (event) => {
  const cell = event.target.closest("[data-tip-title]");
  if (!cell) return hideTooltip();
  showTooltip(`<b>${escapeHtml(cell.dataset.tipTitle)}</b>${escapeHtml(cell.dataset.tipBody)}`, event.clientX, event.clientY);
});
byId("matrix-chart").addEventListener("pointerleave", hideTooltip);
let resizeTimer = 0;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state.dashboard) renderTrend(state.dashboard.trend); }, 150);
});

/* ---------- Learn ---------- */
async function refreshTheory() {
  try {
    const data = await requestJson("/api/theory");
    state.lessons = data.lessons;
    byId("saved-theory-count").textContent = data.saved_count;
    const topicFilter = byId("theory-topic-filter");
    const selectedTopic = topicFilter.value;
    const topics = [...new Set(state.lessons.map((lesson) => lesson.topic))];
    topicFilter.innerHTML = '<option value="">All topics</option>' + topics.map((topic) => `<option value="${escapeHtml(topic)}">${escapeHtml(topic)}</option>`).join("");
    topicFilter.value = selectedTopic;
    renderLessons();
  } catch (_error) {
    showToast("Could not load theory lessons.");
  }
}

function filteredLessons() {
  const search = byId("theory-search").value.trim().toLowerCase();
  const topic = byId("theory-topic-filter").value;
  return state.lessons.filter((lesson) =>
    (state.lessonFilter !== "saved" || lesson.saved)
    && (!topic || lesson.topic === topic)
    && `${lesson.title} ${lesson.topic} ${lesson.explanation}`.toLowerCase().includes(search));
}

function renderLessons() {
  const lessons = filteredLessons();
  if (!lessons.some((lesson) => lesson.id === state.selectedLessonId)) state.selectedLessonId = lessons[0]?.id ?? null;
  byId("learn-summary").textContent = `${plural(lessons.length, "lesson")}${state.lessonFilter === "saved" ? " saved" : ""}`;
  byId("lesson-list").innerHTML = lessons.map((lesson) => `
    <li><button type="button" data-lesson="${lesson.id}" aria-current="${lesson.id === state.selectedLessonId}">
      <b>${escapeHtml(lesson.title)}</b>
      <small><span>${escapeHtml(lesson.topic)}</span><span>${escapeHtml(lesson.difficulty)}</span>${lesson.saved ? `<span class="saved-mark">● Saved</span>` : ""}</small>
    </button></li>`).join("");
  renderLessonDetail();
}

function renderLessonDetail() {
  const detail = byId("lesson-detail");
  const lesson = state.lessons.find((item) => item.id === state.selectedLessonId);
  if (!lesson) {
    detail.innerHTML = "<div class='empty-state'>No lessons match this view yet.</div>";
    return;
  }
  const id = String(lesson.id);
  detail.innerHTML = `
    <div class="tags"><span>${escapeHtml(lesson.topic)}</span><span>${escapeHtml(lesson.difficulty)}</span></div>
    <h2>${escapeHtml(lesson.title)}</h2>
    <span class="kicker">Key ideas</span>
    <ul class="key-ideas">${lesson.key_points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>
    <p class="lesson-body">${escapeHtml(lesson.explanation)}</p>
    <details class="disclosure"><summary><span>See example</span>${icon("chevron", "chevron")}</summary><pre>${escapeHtml(lesson.example)}</pre></details>
    <label class="note-field"><span class="kicker">My notes</span>
      <textarea data-lesson-note="${id}" maxlength="4000" placeholder="Capture a useful distinction or reminder…">${escapeHtml(noteDrafts.get(id) ?? lesson.note)}</textarea></label>
    <div class="button-row">
      <button class="btn ${lesson.saved ? "btn-secondary" : "btn-primary"}" type="button" data-lesson-save="${id}" data-saved="${lesson.saved}">${icon("bookmark")}<span>${lesson.saved ? "Remove from saved" : "Save lesson"}</span></button>
      ${lesson.saved ? `<button class="btn btn-ghost" type="button" data-note-save="${id}">Save note</button>` : ""}
    </div>`;
}

const noteRequest = (lessonId) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ note: document.querySelector(`[data-lesson-note="${lessonId}"]`).value }),
});

byId("lesson-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-lesson]");
  if (!button) return;
  state.selectedLessonId = Number(button.dataset.lesson);
  renderLessons();
  if (window.matchMedia("(max-width: 800px)").matches) byId("lesson-detail").scrollIntoView({ behavior: "smooth" });
  byId("lesson-detail").focus({ preventScroll: true });
});

byId("lesson-detail").addEventListener("input", (event) => {
  const lessonId = event.target.dataset?.lessonNote;
  if (lessonId) noteDrafts.set(lessonId, event.target.value);
});

byId("lesson-detail").addEventListener("click", async (event) => {
  const saveButton = event.target.closest("[data-lesson-save]");
  const noteButton = event.target.closest("[data-note-save]");
  if (!saveButton && !noteButton) return;
  const lessonId = saveButton ? saveButton.dataset.lessonSave : noteButton.dataset.noteSave;
  const removing = saveButton?.dataset.saved === "true";
  try {
    await requestJson(`/api/theory/${lessonId}`, removing ? { method: "DELETE" } : noteRequest(lessonId));
    if (!removing) noteDrafts.delete(lessonId);
    showToast(removing ? "Removed from saved. Your note is kept." : noteButton ? "Note updated." : "Lesson and note saved.");
    await refreshTheory();
  } catch (error) {
    showToast(error.message || "Could not save this lesson.");
  }
});

document.querySelectorAll("[data-theory-filter]").forEach((button) => button.addEventListener("click", () => {
  state.lessonFilter = button.dataset.theoryFilter;
  document.querySelectorAll("[data-theory-filter]").forEach((tab) => {
    tab.classList.toggle("selected", tab === button);
    tab.setAttribute("aria-pressed", String(tab === button));
  });
  renderLessons();
}));
byId("theory-search").addEventListener("input", renderLessons);
byId("theory-topic-filter").addEventListener("change", renderLessons);

/* ---------- Keyboard shortcuts ---------- */
const dialog = byId("shortcuts-dialog");
byId("shortcuts-button").addEventListener("click", () => dialog.showModal());
byId("close-shortcuts").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || dialog.open) return;
  if (event.target.closest?.("input, textarea, select, [contenteditable], .cm-editor")) return;
  const practiceActive = byId("practice-view").classList.contains("active");
  const feedbackShown = !byId("feedback").classList.contains("hidden");
  const key = event.key.toLowerCase();
  if (event.key === "?") { event.preventDefault(); dialog.showModal(); }
  else if (/^[1-4]$/.test(key)) setView(VIEWS[Number(key) - 1]);
  else if (key === "n" && practiceActive && state.question && feedbackShown) nextQuestion();
  else if (key === "s" && practiceActive && state.question) saveForReview();
});

/* ---------- Start ---------- */
byId("today-label").textContent = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(new Date());
showIntro();
renderSessionStats();
refreshDashboard();
const viewFromHash = () => (VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "practice");
window.addEventListener("popstate", () => setView(viewFromHash()));
if (location.hash) setView(viewFromHash());
