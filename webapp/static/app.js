const el = (id) => document.getElementById(id);

const browseSubjectEl = el("browse-subject");
const browseSchoolEl = el("browse-school");
const browseSchoolBlockEl = el("browse-school-block");
const browseFacultyEl = el("browse-faculty");
const browseFacultyBlockEl = el("browse-faculty-block");
const browseMajorEl = el("browse-major");
const browseMajorBlockEl = el("browse-major-block");
const browseQuestionEl = el("browse-question");
const browseQuestionBlockEl = el("browse-question-block");
const browseScopeEl = el("browse-scope");
const browseCountEl = el("browse-count");
const browseListEl = el("browse-list");
const browseEmptyEl = el("browse-empty");

let scopeTree = JSON.parse(el("scope-tree").textContent || "[]");
let browseSubject = "__all__";// 当前选中的科目（"__all__" 或科目名，如 "线性代数"）
let browseSchool = "";        // 当前选中的学校（"" = 全部）
let browseFaculty = "";
let browseMajor = "";
let browseQuestion = "";
let browseReady = false;      // 是否已经点过专攻（页面打开时默认 false，点了专攻才 fetch）

// ?subject=线性代数/九州大学 可以直接带着范围打开
const wanted = new URLSearchParams(location.search).get("subject");

// ---------- 检索范围：科目按钮 + 学校二级按钮 ----------

function topNode(value) {
  const top = String(value).split("/")[0];
  return scopeTree.find((n) => n.value === top || n.value === value) || null;
}

// 只有一所学校时，「全部」和那所学校是同一批题，第二排就没必要出现
function schoolChips(node) {
  return node && node.children.length > 2 ? node.children : [];
}

function scopeLabel(value) {
  const node = topNode(value);
  if (!node) return "";
  const child = node.children.find((c) => c.value === value);
  const count = child ? child.count : node.count;
  const name = child && child.label !== "全部" ? `${node.label} · ${child.label}` : node.label;
  return `${name} · ${count} 题`;
}

function chipButton(option, extraClass) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `chip ${extraClass}`.trim();
  button.dataset.value = option.value;

  const name = document.createElement("span");
  name.className = "chip-name";
  name.textContent = option.label;
  const count = document.createElement("span");
  count.className = "chip-count";
  count.textContent = option.error ? "读取失败" : option.count;
  button.append(name, count);

  if (option.error) button.title = option.error;
  button.addEventListener("click", () => selectScope(option.value));
  return button;
}

// ---------- 题目库展示：科目 / 学校 / 年份 三个下拉 ----------

// scopeTree 一项：科目级（含 children），或「全部题目」「默认题库」（无 children）
function isSubjectNode(node) {
  return Array.isArray(node.children) && node.children.length > 0;
}

function schoolExists(subjectValue, schoolLabel) {
  const node = scopeTree.find((n) => n.value === subjectValue);
  if (!node || !isSubjectNode(node)) return false;
  return node.children.some((c) => c.label === schoolLabel);
}

function apiSubjectParam() {
  // 拼成 API 接受的 subject 字符串：__all__ / 科目[/学校[/专攻]]
  if (browseSubject === "__all__") return "__all__";
  const parts = [browseSubject, browseSchool, browseFaculty, browseMajor, browseQuestion].filter((p) => p !== "");
  return parts.join("/");
}

// 「科目」节点下找「学习」节点；「学习」节点下找「专业」节点
function findNode(scopeValue) {
  return scopeTree.find((n) => n.value === scopeValue) || null;
}

// 顶部科目下拉：只列有数据的科目
function populateBrowseSubject() {
  browseSubjectEl.replaceChildren();
  scopeTree.forEach((node) => {
    // 题目展示模式不显示「全部题目」（那是匹配模式的事）
    if (isSubjectNode(node)) {
      const opt = document.createElement("option");
      opt.value = node.value;
      opt.textContent = `${node.label}（${node.count}）`;
      browseSubjectEl.appendChild(opt);
    }
  });
  const available = [...browseSubjectEl.options].map((o) => o.value);
  // 初次加载时若 browseSubject 是 __all__，跳过它选第一个实际科目
  const wanted = browseSubject === "__all__" ? available[0] || "" : browseSubject;
  browseSubjectEl.value = available.includes(wanted) ? wanted : (available[0] || "");
  browseSubject = browseSubjectEl.value;
  browseSubjectEl.disabled = browseSubjectEl.options.length === 0;
}

// 四级下拉：学校 → 学院 → 专攻 → 题目
function populateBrowseSchool() {
  const levels = [[browseSchoolEl, browseSchoolBlockEl, "school"], [browseFacultyEl, browseFacultyBlockEl, "faculty"], [browseMajorEl, browseMajorBlockEl, "major"], [browseQuestionEl, browseQuestionBlockEl, "question"]];
  const selected = [browseSchool, browseFaculty, browseMajor, browseQuestion];
  let parent = findNode(browseSubject);
  let prefix = browseSubject;
  levels.forEach(([select, block], index) => {
    const options = (parent?.children || []).filter((c) => c.label !== "全部");
    select.replaceChildren(...options.map((item) => {
      const option = document.createElement("option");
      option.value = item.value.slice(prefix.length + 1);
      option.textContent = `${item.label}（${item.count}）`;
      return option;
    }));
    const values = [...select.options].map((option) => option.value);
    select.value = values.includes(selected[index]) ? selected[index] : (values[0] || "");
    selected[index] = select.value;
    select.disabled = !values.length;
    block.hidden = !values.length;
    parent = options.find((item) => item.value === `${prefix}/${select.value}`);
    prefix = parent?.value || `${prefix}/${select.value}`;
  });
  [browseSchool, browseFaculty, browseMajor, browseQuestion] = selected;
}

// 用户没选完时，右侧显示提示而不调 API
function showBrowsePrompt(text) {
  browseListEl.replaceChildren();
  browseCountEl.textContent = "";
  browseScopeEl.textContent = "";
  browseEmptyEl.textContent = text || "请从左侧选一个专攻查看题目。";
  browseEmptyEl.hidden = false;
}

function selectBrowseSubject(value) {
  browseSubject = value;
  browseSchool = "";
  browseFaculty = browseMajor = browseQuestion = "";
  populateBrowseSchool();
  updateUrl();
  // 选完科目后自动选中第一个专攻 → 立即 fetch
  if (browseQuestion) {
    browseReady = true;
    fetchBrowse();
  } else {
    showBrowsePrompt();
  }
}

function selectBrowseSchool(value) {
  browseSchool = value;
  browseFaculty = browseMajor = browseQuestion = "";
  populateBrowseSchool();
  updateUrl();
  if (browseQuestion) {
    browseReady = true;
    fetchBrowse();
  } else {
    showBrowsePrompt();
  }
}

function selectBrowseFaculty(value) {
  browseFaculty = value;
  browseMajor = browseQuestion = "";
  populateBrowseSchool();
  browseReady = Boolean(browseQuestion);
  updateUrl();
  if (browseQuestion) fetchBrowse(); else showBrowsePrompt();
}

function selectBrowseMajor(value) {
  browseMajor = value;
  browseQuestion = "";
  populateBrowseSchool();
  browseReady = Boolean(browseQuestion);
  updateUrl();
  if (browseQuestion) fetchBrowse(); else showBrowsePrompt();
}

function selectBrowseQuestion(value) {
  browseQuestion = value;
  browseReady = true;
  updateUrl();
  fetchBrowse();
}

async function fetchBrowse() {
  browseEmptyEl.hidden = true;
  browseListEl.replaceChildren();
  browseCountEl.textContent = "加载中…";
  try {
    const url = new URL("/api/browse/questions", location.origin);
    url.searchParams.set("subject", apiSubjectParam());
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) {
      browseCountEl.textContent = "";
      browseEmptyEl.textContent = data.error || "加载失败。";
      browseEmptyEl.hidden = false;
      return;
    }
    renderBrowseCards(data);
  } catch (err) {
    browseCountEl.textContent = "";
    browseEmptyEl.textContent = "请求失败：" + err.message;
    browseEmptyEl.hidden = false;
  }
}

function renderBrowseCards(data) {
  browseListEl.replaceChildren();
  const total = data.total || 0;
  const filterNote = data.year ? ` · ${data.year}` : "";
  browseScopeEl.textContent = `${data.subject_label}${filterNote}`;
  browseCountEl.textContent = total ? `共 ${total} 题` : "";
  if (!total) {
    browseEmptyEl.textContent = `「${data.subject_label}」里没有题目。`;
    browseEmptyEl.hidden = false;
    return;
  }
  data.questions.forEach((q) => {
    const li = document.createElement("li");
    li.className = "browse-card";
    const head = document.createElement("div");
    head.className = "browse-card-head";
    const idEl = document.createElement("span");
    idEl.className = "browse-card-id";
    idEl.textContent = q.id || "（无 id）";
    const meta = document.createElement("span");
    meta.className = "browse-card-meta";
    meta.textContent = [q.school, q.year].filter(Boolean).join(" · ");
    head.append(idEl, meta);
    li.appendChild(head);
    li.id = `question-${q.id}`;
    li.dataset.questionId = q.id || "";
    const similarButton = document.createElement("button");
    similarButton.type = "button";
    similarButton.className = "similar-button";
    similarButton.textContent = "找相似题";
    similarButton.addEventListener("click", () => findSimilar(q));
    li.appendChild(similarButton);
    paragraphs(q.text).forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part;
      li.appendChild(p);
    });
    if (Array.isArray(q.answer) && q.answer.length) {
      li.appendChild(buildAnswerBlock(q.answer));
    }
    if (Array.isArray(q.practice_questions) && q.practice_questions.length) {
      li.appendChild(buildPracticeBlock(q.practice_questions));
    }
    browseListEl.appendChild(li);
  });
  typeset(browseListEl);
}

// 答案块：默认折叠的 <details>，里面按子问分块、每块内是编号步骤列表
// answer 形状：[{label: "(1)", steps: ["step1...", "step2..."]}, ...]
// 每步可能是多行字符串（用 \n 分隔）
function buildAnswerBlock(parts) {
  const details = document.createElement("details");
  details.className = "browse-answer";
  const totalSteps = parts.reduce((s, p) => s + (p.steps ? p.steps.length : 0), 0);
  const summary = document.createElement("summary");
  summary.textContent = `参考答案 · ${parts.length} 个子问 · ${totalSteps} 步`;
  details.appendChild(summary);

  parts.forEach((part) => {
    const block = document.createElement("div");
    block.className = "browse-answer-part";
    const labelEl = document.createElement("div");
    labelEl.className = "browse-answer-label";
    labelEl.textContent = part.label || "";
    block.appendChild(labelEl);
    const ol = document.createElement("ol");
    ol.className = "browse-answer-steps";
    (part.steps || []).forEach((step) => {
      const li = document.createElement("li");
      li.className = "browse-answer-step";
      // 多行字符串用 \n 分隔，按行渲染（保留换行让公式独占一行）
      const div = document.createElement("div");
      div.className = "browse-answer-step-body";
      step.split("\n").forEach((line, idx, arr) => {
        div.appendChild(document.createTextNode(line));
        if (idx < arr.length - 1) div.appendChild(document.createElement("br"));
      });
      li.appendChild(div);
      ol.appendChild(li);
    });
    block.appendChild(ol);
    details.appendChild(block);
  });
  return details;
}

// 专属练习和原题一起存放、一起展示，但不提供“找相似题”入口，
// 也不会由后端加入 QuestionIndex。
function buildPracticeBlock(questions) {
  const details = document.createElement("details");
  details.className = "browse-practice";
  const summary = document.createElement("summary");
  summary.textContent = `针对本题的循序渐进练习 · ${questions.length} 题`;
  details.appendChild(summary);

  questions.forEach((question, index) => {
    const card = document.createElement("article");
    card.className = "browse-practice-card";
    const head = document.createElement("div");
    head.className = "browse-practice-head";
    const title = document.createElement("strong");
    title.textContent = `第 ${index + 1} 题`;
    const meta = document.createElement("span");
    const detailsText = [];
    if (question.difficulty) detailsText.push(`难度 ${question.difficulty}/5`);
    if (question.estimated_minutes) detailsText.push(`约 ${question.estimated_minutes} 分钟`);
    meta.textContent = detailsText.join(" · ");
    head.append(title, meta);
    card.appendChild(head);
    paragraphs(question.text).forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part;
      card.appendChild(p);
    });
    if (Array.isArray(question.answer) && question.answer.length) {
      card.appendChild(buildAnswerBlock(question.answer));
    }
    details.appendChild(card);
  });

  details.addEventListener("toggle", () => {
    if (details.open) typeset(details);
  });
  return details;
}

// 题库是热加载的：切回这个页面时顺手看看科目/学习/专业/学校有没有变
async function refreshScope() {
  try {
    const res = await fetch("/api/subjects");
    const data = await res.json();
    if (JSON.stringify(data.tree) === JSON.stringify(scopeTree)) return;
    scopeTree = data.tree;
    if (!scopeTree.some((n) => n.value === browseSubject)) browseSubject = "";
    populateBrowseSubject();
    populateBrowseSchool();
    populateBrowseSchool();
    if (browseReady) fetchBrowse(); else showBrowsePrompt();
  } catch (err) {
    /* 拿不到就保持现状 */
  }
}

function showMessage(text, kind) {
  messageEl.textContent = text;
  messageEl.className = kind === "info" ? "message info" : "message";
  messageEl.hidden = !text;
}

// 一道题拆成若干行：题设、公式、各小问各占一行，别全挤成一段
// 关键：日校题库里小问经常紧跟在 `。` 后面写（`…M_{mn}(R)。(1) 对 A,C∈…`），
// 所以规则是「在 `(1)/(2)/...`、`1./2./...`、`①/②` 这类标记前换行」；
// 同时要求标记后跟空白+汉字，避免拆掉矩阵下标 `M_{mn}(R)`、公式 `(a_{ij})`
function paragraphs(text) {
  return String(text || "")
    .replace(/([。：；！？…」』])\s*(?=[（(]\d+[)）]\s*[\u4e00-\u9fff])/g, "$1\n")
    .replace(/([。：；！？…」』])\s*(?=\d+[\.\)、]\s*[\u4e00-\u9fff])/g, "$1\n")
    .replace(/([。：；！？…」』])\s*(?=[①②③④⑤⑥⑦⑧⑨⑩]\s*[\u4e00-\u9fff])/g, "$1\n")
    .split(/\n+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

// KaTeX 的脚本使用 defer；网络较慢时，数据可能先回来。短暂重试，避免把
// `$...$` 永久留成原始 LaTeX。CDN 真拿不到时仍保持原文，不影响其它功能。
function typeset(root, retries = 30) {
  if (!root || !root.isConnected) return;
  if (!window.renderMathInElement) {
    if (retries > 0) window.setTimeout(() => typeset(root, retries - 1), 100);
    return;
  }
  window.renderMathInElement(root, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\[", right: "\\]", display: true },
      { left: "\\(", right: "\\)", display: false },
    ],
    throwOnError: false,
    errorColor: "#b4232c",
  });
}

function renderResults(data) {
  const matches = data.matches || [];
  resultsEl.replaceChildren();
  matches.forEach((m) => {
    const li = document.createElement("li");
    li.className = "result";          // 只显示题目，一小问一行
    paragraphs(m.text).forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part;
      li.appendChild(p);
    });
    resultsEl.appendChild(li);
  });

  const scope = [data.subject_label, `共 ${data.db_size} 题`, `阈值 ${data.min_score}`]
    .filter((s) => s !== undefined && s !== null && s !== "")
    .join(" · ");
  el("results-scope").textContent = scope;
  resultsEl.hidden = matches.length === 0;

  const emptyEl = el("results-empty");
  emptyEl.textContent = matches.length ? "" : emptyReason(data);
  emptyEl.hidden = matches.length > 0;

  // 0 条也要把面板留着：图片模式下 OCR 文本和模型 JSON 就在这里面
  resultsPanel.hidden = matches.length === 0 && !data.ocr_text && !data.question_json;
  typeset(resultsEl);
}

function emptyReason(data) {
  const where = `「${data.subject_label || "题库"}」`;
  if (data.best_score === null || data.best_score === undefined) {
    return `${where}里没有可比较的题目。`;
  }
  return (
    `${where}里没有相似度 ≥ ${data.min_score} 的题，最相似的一条也只有 ${data.best_score}。` +
    `要么检索范围选错了，要么把阈值调低再试。`
  );
}

function summarize(data) {
  const parts = [...(data.warnings || [])];
  if (data.matches.length && data.filtered) {
    parts.push(`另有 ${data.filtered} 条低于阈值 ${data.min_score}，没有显示`);
  }
  return parts.join("；");
}

function renderDetail(data) {
  const hasDetail = Boolean(data.ocr_text || data.question_json);
  detailEl.hidden = !hasDetail;
  if (!hasDetail) return;
  detailEl.open = false;
  el("ocr-text").textContent = data.ocr_text || "";
  el("ocr-backend").textContent = data.ocr_backend || "";
  el("question-json").textContent = data.question_json
    ? JSON.stringify(data.question_json, null, 2)
    : "";
}

function setMode(next) {
  mode = next;
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.mode === next);
  });
  el("pane-image").hidden = next !== "image";
  el("pane-json").hidden = next !== "json";
  showMessage("");
}

function setFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showMessage("请选择图片文件。");
    return;
  }
  pickedFile = file;
  previewEl.src = URL.createObjectURL(file);
  previewEl.hidden = false;
  dropHintEl.textContent = file.name;
  showMessage("");
}

async function post(url, options) {
  const res = await fetch(url, options);
  const raw = await res.text();
  let data;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch (_err) {
    data = { error: `服务端返回了无法解析的内容（HTTP ${res.status}）。` };
  }
  return { ok: res.ok, data };
}

async function match() {
  const topk = Number(topkEl.value) || 5;
  const minScore = minScoreEl && minScoreEl.value !== "" ? Number(minScoreEl.value) : null;
  let request;

  if (mode === "image") {
    if (!pickedFile) {
      showMessage("先选一张题目图片。");
      return;
    }
    const form = new FormData();
    form.append("image", pickedFile);
    form.append("topk", String(topk));
    form.append("subject", subject);
    if (minScore !== null) form.append("min_score", String(minScore));
    request = ["/api/match-image", { method: "POST", body: form }];
  } else {
    const raw = queryEl.value.trim();
    if (!raw) {
      showMessage("先贴入一道题的 JSON。");
      return;
    }
    request = [
      "/api/match",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: raw, topk, subject, min_score: minScore }),
      },
    ];
  }

  submitEl.disabled = true;
  showMessage(mode === "image" ? "识别并匹配中，第一次调用模型可能要十几秒…" : "匹配中…", "info");

  try {
    const { ok, data } = await post(...request);
    if (!ok) {
      resultsPanel.hidden = true;
      showMessage(data.error || "匹配失败。");
      return;
    }
    renderResults(data);
    renderDetail(data);
    showMessage(summarize(data), "info");
  } catch (err) {
    resultsPanel.hidden = true;
    showMessage("请求失败：" + err.message);
  } finally {
    submitEl.disabled = false;
  }
}

const similarCache = new Map();
let similarSourceId = "";
let lastSimilar = null;

function similarCacheKey(question) {
  return JSON.stringify([apiSubjectParam(), question.id, Number(el("similar-count").value)]);
}

function openSimilarDrawer() {
  el("similar-drawer").hidden = false;
  el("similar-backdrop").hidden = false;
  document.body.classList.add("drawer-open");
}

function closeSimilarDrawer() {
  el("similar-drawer").hidden = true;
  el("similar-backdrop").hidden = true;
  document.body.classList.remove("drawer-open");
}

function highlightQuestion(questionId) {
  const target = [...browseListEl.children]
    .find((card) => card.dataset.questionId === questionId);
  if (!target) return false;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("question-highlight");
  window.setTimeout(() => target.classList.remove("question-highlight"), 1800);
  return true;
}

async function openOriginalQuestion(match) {
  closeSimilarDrawer();
  if (highlightQuestion(match.id)) return;
  if (!match.scope) return;

  const [subject = "", school = "", faculty = "", major = "", question = ""] = match.scope.split("/");
  browseSubject = subject;
  browseSchool = school;
  browseFaculty = faculty;
  browseMajor = major;
  browseQuestion = question;
  populateBrowseSubject();
  populateBrowseSchool();
  browseReady = Boolean(browseQuestion);
  updateUrl();
  if (!browseReady) return;
  await fetchBrowse();
  window.requestAnimationFrame(() => highlightQuestion(match.id));
}

function renderSimilar(data, source) {
  lastSimilar = { data, source };
  el("reopen-similar").hidden = false;
  const list = el("similar-results");
  const status = el("similar-status");
  const matches = data.matches || [];
  list.replaceChildren();
  el("similar-scope").textContent = `${source.id} · ${data.subject_label || "题库"}`;
  status.textContent = matches.length ? `按相似度从高到低，共 ${matches.length} 题` : "没有找到相似题目。";
  status.hidden = false;
  matches.forEach((match, index) => {
    const item = document.createElement("li");
    item.className = "similar-result";
    const head = document.createElement("div");
    head.className = "similar-result-head";
    const rank = document.createElement("span");
    rank.textContent = `相似度 ${(match.score * 100).toFixed(1)}%`;
    const meta = document.createElement("span");
    meta.textContent = [match.school, match.year].filter(Boolean).join(" · ") || match.id || `第 ${index + 1} 题`;
    head.append(rank, meta);
    item.appendChild(head);
    paragraphs(match.text).forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part;
      item.appendChild(p);
    });
    const jump = document.createElement("button");
    jump.type = "button";
    jump.className = "jump-button";
    jump.textContent = "打开原题";
    jump.addEventListener("click", () => openOriginalQuestion(match));
    item.appendChild(jump);
    list.appendChild(item);
  });
  typeset(list);
}

async function findSimilar(question) {
  openSimilarDrawer();
  similarSourceId = question.id;
  const topk = Math.max(1, Math.min(50, Number(el("similar-count").value) || 5));
  el("similar-count").value = topk;
  const key = similarCacheKey(question);
  const cached = similarCache.get(key);
  if (cached) {
    renderSimilar(cached, question);
    return;
  }
  const status = el("similar-status");
  status.textContent = "正在检索相似题目…";
  status.hidden = false;
  el("similar-results").replaceChildren();
  try {
    const { ok, data } = await post("/api/similar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: question.id, subject: apiSubjectParam(), topk, min_score: 0 }),
    });
    if (!ok) throw new Error(data.error || "匹配失败。");
    similarCache.set(key, data);
    renderSimilar(data, question);
  } catch (err) {
    status.textContent = err.message;
    status.hidden = false;
  }
}

el("close-similar").addEventListener("click", closeSimilarDrawer);
el("similar-backdrop").addEventListener("click", closeSimilarDrawer);
el("rerun-similar").addEventListener("click", () => {
  if (similarSourceId) findSimilar({ id: similarSourceId });
});
el("reopen-similar").addEventListener("click", () => {
  if (lastSimilar) { openSimilarDrawer(); renderSimilar(lastSimilar.data, lastSimilar.source); }
});

window.addEventListener("focus", refreshScope);

// ---------- 题目展示 + URL 同步 ----------

function updateUrl() {
  const params = new URLSearchParams(location.search);
  params.delete("view");
  const subjParam = apiSubjectParam();
  if (subjParam && subjParam !== "__all__") params.set("subject", subjParam);
  else params.delete("subject");
  const qs = params.toString();
  const url = qs ? `?${qs}` : location.pathname;
  history.replaceState(null, "", url);
}

// 启动：URL 里有 ?subject= / ?year= 就按它来
const urlParams = new URLSearchParams(location.search);
if (wanted) {
  {
    // browse 模式：URL 里 `subject=科目/学习/专业/学校` 才视为已经点过学校（直接取数）；
    // 只有 `subject=科目` 没学校就只切科目不取数
    if (wanted.includes("/")) {
      const parts = wanted.split("/");
      const subj = parts[0];
      const school = parts[1] || "";
      const faculty = parts[2] || "";
      const major = parts[3] || "";
      const question = parts[4] || "";
      if (scopeTree.some((n) => n.value === subj)) {
        browseSubject = subj;
        browseSchool = school;
        browseFaculty = faculty;
        browseMajor = major;
        browseQuestion = question;
        if (question) browseReady = true;
      }
    } else if (scopeTree.some((n) => n.value === wanted)) {
      browseSubject = wanted;
    }
  }
}
const wantedYear = urlParams.get("year");
// 年份下拉已移除（按用户要求）；保留 wantedYear 变量占位

browseSubjectEl.addEventListener("change", () => selectBrowseSubject(browseSubjectEl.value));
browseSchoolEl.addEventListener("change", () => selectBrowseSchool(browseSchoolEl.value));
browseFacultyEl.addEventListener("change", () => selectBrowseFaculty(browseFacultyEl.value));
browseMajorEl.addEventListener("change", () => selectBrowseMajor(browseMajorEl.value));
browseQuestionEl.addEventListener("change", () => selectBrowseQuestion(browseQuestionEl.value));

populateBrowseSubject();
populateBrowseSchool();
if (browseQuestion && browseReady) fetchBrowse(); else showBrowsePrompt();
updateUrl();
