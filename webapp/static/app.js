const el = (id) => document.getElementById(id);

const queryEl = el("query");
const topkEl = el("topk");
const submitEl = el("submit");
const messageEl = el("message");
const resultsEl = el("results");
const resultsPanel = el("results-panel");
const exampleEl = el("example-json");
const fileEl = el("file");
const dropEl = el("drop");
const previewEl = el("preview");
const dropHintEl = el("drop-hint");
const detailEl = el("detail");

let mode = "image";
let pickedFile = null;

function showMessage(text, kind) {
  messageEl.textContent = text;
  messageEl.className = kind === "info" ? "message info" : "message";
  messageEl.hidden = !text;
}

function renderResults(matches) {
  resultsEl.replaceChildren();
  matches.forEach((m) => {
    const li = document.createElement("li");
    li.textContent = m.text;   // 只显示题目
    resultsEl.appendChild(li);
  });
  resultsPanel.hidden = matches.length === 0;
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
  const data = await res.json().catch(() => ({ error: "服务端返回了无法解析的内容。" }));
  return { ok: res.ok, data };
}

async function match() {
  const topk = Number(topkEl.value) || 5;
  let request;

  if (mode === "image") {
    if (!pickedFile) {
      showMessage("先选一张题目图片。");
      return;
    }
    const form = new FormData();
    form.append("image", pickedFile);
    form.append("topk", String(topk));
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
        body: JSON.stringify({ query: raw, topk }),
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
    renderResults(data.matches);
    renderDetail(data);
    const warnings = data.warnings || [];
    showMessage(
      data.matches.length ? warnings.join("；") : "题库里没有可比较的题目。",
      "info"
    );
  } catch (err) {
    resultsPanel.hidden = true;
    showMessage("请求失败：" + err.message);
  } finally {
    submitEl.disabled = false;
  }
}

submitEl.addEventListener("click", match);
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => setMode(tab.dataset.mode));
});

fileEl.addEventListener("change", (e) => setFile(e.target.files[0]));

["dragenter", "dragover"].forEach((type) =>
  dropEl.addEventListener(type, (e) => {
    e.preventDefault();
    dropEl.classList.add("hover");
  })
);
["dragleave", "drop"].forEach((type) =>
  dropEl.addEventListener(type, (e) => {
    e.preventDefault();
    dropEl.classList.remove("hover");
  })
);
dropEl.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

document.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (!item) return;
  setMode("image");
  setFile(item.getAsFile());
});

queryEl.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") match();
});

el("fill-example").addEventListener("click", () => {
  queryEl.value = exampleEl.textContent.trim();
  showMessage("");
});
