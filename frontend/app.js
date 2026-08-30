// 支持填写域名或带 /api 的地址，统一避免拼出 /api/api/*。
const backend = String(window.BACKEND_URL || "").replace(/\/$/, "").replace(/\/api$/, "");
const $ = (id) => document.getElementById(id);
const subjectEl = $("subject");
const schoolEl = $("school");
const facultyEl = $("faculty");
const majorEl = $("major");
const questionEl = $("question");
const schoolWrap = $("school-wrap");
const facultyWrap = $("faculty-wrap");
const majorWrap = $("major-wrap");
const questionWrap = $("question-wrap");
const questionList = $("questions");
const cache = new Map();
let tree = [];
let current = { subject: "", school: "", faculty: "", major: "", question: "" };
let selectedQuestionId = "";
let lastSimilar = null;

function api(path) { return `${backend}${path}`; }
function node(value) {
  return tree.find((item) => item.value === value) || null;
}
function subjectParam() {
  return [current.subject, current.school, current.faculty, current.major, current.question].filter(Boolean).join("/");
}
function setOptions(select, values, selected) {
  select.replaceChildren(...values.map((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = `${item.label}（${item.count}）`;
    return option;
  }));
  select.value = values.some((item) => item.value === selected) ? selected : (values[0]?.value || "");
}
function populateFilters() {
  const subjects = tree.filter((item) => Array.isArray(item.children) && item.children.length);
  setOptions(subjectEl, subjects, current.subject);
  current.subject = subjectEl.value;
  const levels = [[schoolEl, schoolWrap, "school"], [facultyEl, facultyWrap, "faculty"], [majorEl, majorWrap, "major"], [questionEl, questionWrap, "question"]];
  let parent = node(current.subject);
  let prefix = current.subject;
  levels.forEach(([select, wrap, key]) => {
    const options = (parent?.children || []).filter((item) => item.label !== "全部");
    const mapped = options.map((item) => ({ ...item, value: item.value.slice(prefix.length + 1) }));
    setOptions(select, mapped, current[key]);
    current[key] = select.value;
    wrap.hidden = !options.length;
    parent = options.find((item) => item.value === `${prefix}/${current[key]}`);
    prefix = parent?.value || `${prefix}/${current[key]}`;
  });
}
function paragraphs(text) { return String(text || "").split(/\n+/).map((part) => part.trim()).filter(Boolean); }
function openDrawer() { $("drawer").hidden = false; $("backdrop").hidden = false; }
function closeDrawer() { $("drawer").hidden = true; $("backdrop").hidden = true; }
function renderQuestions(data) {
  $("scope").textContent = data.subject_label || "";
  $("count").textContent = data.total ? `共 ${data.total} 题` : "";
  $("empty").hidden = Boolean(data.total);
  questionList.replaceChildren(...data.questions.map((question) => {
    const li = document.createElement("li");
    li.className = "question";
    li.dataset.id = question.id;
    const head = document.createElement("header");
    head.textContent = [question.id, question.school, question.year].filter(Boolean).join(" · ");
    li.appendChild(head);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "找相似题";
    button.onclick = () => findSimilar(question.id);
    li.appendChild(button);
    paragraphs(question.text).forEach((part) => { const p = document.createElement("p"); p.textContent = part; li.appendChild(p); });
    return li;
  }));
}
async function loadQuestions() {
  const response = await fetch(api(`/api/browse/questions?subject=${encodeURIComponent(subjectParam())}`));
  if (!response.ok) throw new Error(`题目加载失败（HTTP ${response.status}）`);
  renderQuestions(await response.json());
}
async function findSimilar(id) {
  openDrawer();
  selectedQuestionId = id;
  const topk = Math.max(1, Math.min(50, Number($("result-count").value) || 5));
  $("result-count").value = topk;
  const key = `${subjectParam()}::${id}::${topk}`;
  if (cache.has(key)) return renderSimilar(cache.get(key), id);
  $("similar-status").textContent = "正在检索相似题目…";
  try {
    const response = await fetch(api("/api/similar"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, subject: subjectParam(), topk, min_score: 0 }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `匹配失败（HTTP ${response.status}）`);
    cache.set(key, data);
    renderSimilar(data, id);
  } catch (error) { $("similar-status").textContent = error.message; }
}
function renderSimilar(data, sourceId) {
  lastSimilar = { data, sourceId };
  $("reopen").hidden = false;
  $("similar-status").textContent = `${sourceId} · 按相似度从高到低，共 ${(data.matches || []).length} 题`;
  $("similar").replaceChildren(...(data.matches || []).map((match) => {
    const li = document.createElement("li"); li.className = "similar-item";
    const score = document.createElement("strong"); score.textContent = `${(match.score * 100).toFixed(1)}%`;
    li.append(score, document.createTextNode(` · ${[match.school, match.year].filter(Boolean).join(" · ")}`));
    paragraphs(match.text).forEach((part) => { const p = document.createElement("p"); p.textContent = part; li.appendChild(p); });
    const jump = document.createElement("button"); jump.type = "button"; jump.textContent = "打开原题";
    jump.onclick = () => { closeDrawer(); document.querySelector(`[data-id="${CSS.escape(match.id)}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }); };
    li.appendChild(jump); return li;
  }));
}
async function init() {
  if (!backend || backend.includes("你的后端域名")) throw new Error("请先在 frontend/config.js 设置后端地址。");
  const response = await fetch(api("/api/subjects"));
  if (!response.ok) throw new Error(`后端连接失败（HTTP ${response.status}）`);
  const data = await response.json();
  $("result-count").value = data.topk ?? 5;
  tree = data.tree || [];
  populateFilters(); await loadQuestions();
}
subjectEl.onchange = () => { current = { subject: subjectEl.value, school: "", faculty: "", major: "", question: "" }; populateFilters(); loadQuestions().catch(showError); };
schoolEl.onchange = () => { current.school = schoolEl.value; current.faculty = ""; current.major = ""; current.question = ""; populateFilters(); loadQuestions().catch(showError); };
facultyEl.onchange = () => { current.faculty = facultyEl.value; current.major = ""; current.question = ""; populateFilters(); loadQuestions().catch(showError); };
majorEl.onchange = () => { current.major = majorEl.value; current.question = ""; populateFilters(); loadQuestions().catch(showError); };
questionEl.onchange = () => { current.question = questionEl.value; loadQuestions().catch(showError); };
$("close").onclick = closeDrawer; $("backdrop").onclick = closeDrawer;
$("rerun").onclick = () => { if (selectedQuestionId) findSimilar(selectedQuestionId); };
$("reopen").onclick = () => { if (lastSimilar) { openDrawer(); renderSimilar(lastSimilar.data, lastSimilar.sourceId); } };
function showError(error) { $("empty").textContent = error.message; $("empty").hidden = false; }
init().catch(showError);
