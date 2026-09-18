"""网页服务：贴一道题的 JSON（或传图片），选好检索范围，返回匹配到的题目。

检索范围（下拉框）三级：全部题目 / 某个科目（data/ 下的子目录）/ 科目里的某个来源（学校）。
低于相似度阈值的结果一律不显示，避免选错范围时拿一堆跨科目的题来凑数。

启动：
    python -m webapp.server                     # http://127.0.0.1:8000
    python -m webapp.server --db 我的题库.json --port 9000
    python -m webapp.server --data-root 我的题库目录 --min-score 0.4
"""

from __future__ import annotations

import argparse
import os
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # 允许 python webapp/server.py 直接跑
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from mqm import (  # noqa: E402
    ALL_SUBJECTS,
    DATA_ROOT,
    QuestionIndex,
    Question,
    aliases_from_config,
    group_by_source,
    list_senkou,
    list_schools,
    list_subjects,
    load_config,
    load_question_files,
    load_scope,
    match_defaults,
    question_files,
    question_from_dict,
    structured_files,
    subject_files,
)

DEFAULT_DB = ROOT / "data" / "questions.sample.json"
DEFAULT_SUBJECT_KEY = ""  # 不选科目时用 --db 那个文件
EXAMPLE_QUERY = ROOT / "examples" / "my_question.json"

# 临时不展示的科目；命令行可用 --hide-subjects 覆盖（逗号分隔）
# 默认隐藏非数学科（按你的当前需要）
HIDDEN_SUBJECTS = {"形式语言与自动机", "情报理论", "计算机组成原理"}

# 题库里"题目原文"可能用的键名，按顺序取第一个非空的
TEXT_KEYS = ("text", "stem", "question", "content", "题目", "题干")

MAX_TOPK = 50
MAX_UPLOAD_BYTES = 16 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif", ".bmp", ".tiff"}


def filename_hierarchy(path: Path) -> tuple[str, str, str]:
    """从 `年份_一级专攻_二级专攻_题目.json` 提取三级文件名分类。"""
    stem = path.stem
    parts = stem.split("_")
    if parts and parts[0].isdigit() and len(parts) >= 3:
        primary = parts[1]
        secondary = parts[2]
        question = "_".join(parts[3:]) or stem
        return primary, secondary, question
    # 不符合新命名法的文件仍可浏览，不把它们丢掉。
    return stem, "", stem


def question_text(q: Question) -> str:
    """结果只显示题目，所以要尽量找到题目原文；实在没有就用考点凑一句。"""
    for key in TEXT_KEYS:
        value = q.raw.get(key)
        if value and str(value).strip():
            return str(value).strip()
    parts = [p for p in ["、".join(q.knowledge_points), q.question_type] if p]
    return "（该题未提供题目原文）" + ("：" + " / ".join(parts) if parts else f" {q.qid}")


@dataclass
class Scope:
    """下拉框里的一个检索范围。`group` 非空时在下拉框里归到同一个分组下。"""

    key: str
    label: str
    group: str = ""
    questions: List[Question] = field(default_factory=list)
    error: Optional[str] = None

    def as_option(self) -> Dict[str, Any]:
        return {
            "value": self.key,
            "label": self.label,
            "group": self.group,
            "count": len(self.questions),
            "error": self.error,
        }


class Library:
    """按范围分开的题库。题目启动时读好，索引第一次用到时才建（换编码器也不拖慢启动）。

    范围 key：`""` = `--db` 那个文件，`"__all__"` = 整个 data 目录，
    `"线性代数"` = 该科目全部，`"线性代数/九州大学"` = 该科目里的某个来源。

    题库文件改了/加了/删了，`refresh_if_changed()` 会重建，不用重启服务。
    """

    def __init__(
        self,
        db_path: Path,
        config: Dict[str, Any],
        aliases: Dict[str, Dict[str, str]],
        data_root: Path = DATA_ROOT,
        hidden: Iterable[str] = HIDDEN_SUBJECTS,
    ):
        self.db_path = Path(db_path)
        self.data_root = Path(data_root)
        self.config = config
        self.aliases = aliases
        self.hidden = set(hidden)
        self.subjects: List[str] = []
        # (scopes, by_key) 一起换，读的人永远拿到一致的快照（不用加锁）
        self._state: tuple = ([], {})
        self._indexes: Dict[str, QuestionIndex] = {}
        self._stamp: tuple = ()
        self.reload()

    # ---------- 读 ----------

    def keys(self) -> List[str]:
        return [s.key for s in self._state[0]]

    def has(self, key: str) -> bool:
        return key in self._state[1]

    def label(self, key: str) -> str:
        scope = self._state[1].get(key)
        return scope.label if scope else key

    def size(self, key: str) -> int:
        scope = self._state[1].get(key)
        return len(scope.questions) if scope else 0

    def questions(self, key: str) -> List[Question]:
        """返回该范围内的题目列表（题目库展示用）。"""
        scope = self._state[1].get(key)
        return list(scope.questions) if scope else []

    def detail_scope(self, qid: str, subject: str = "") -> str:
        """返回一道题所在的最深浏览范围，供“打开原题”跨文件跳转。"""
        top_subject = str(subject or "").split("/")[0]
        prefix = f"{top_subject}/" if top_subject else ""
        candidates = [
            scope.key
            for scope in self._state[0]
            if scope.key.startswith(prefix)
            and scope.key.count("/") >= 4
            and any(question.qid == qid for question in scope.questions)
        ]
        return max(candidates, key=lambda key: key.count("/"), default="")

    def error(self, key: str) -> Optional[str]:
        scope = self._state[1].get(key)
        return scope.error if scope else None

    def index(self, key: str) -> QuestionIndex:
        index = self._indexes.get(key)
        if index is None:
            index = QuestionIndex(list(self._state[1][key].questions), config=self.config)
            self._indexes[key] = index
        return index

    def options(self) -> List[Dict[str, Any]]:
        return [s.as_option() for s in self._state[0]]

    def option_groups(self) -> List[Dict[str, Any]]:
        """连续同组的选项收进一组（给需要分组视图的调用方用）。"""
        groups: List[Dict[str, Any]] = []
        for scope in self._state[0]:
            if not groups or groups[-1]["label"] != scope.group:
                groups.append({"label": scope.group, "options": []})
            groups[-1]["options"].append(scope.as_option())
        return groups

    def chip_tree(self) -> List[Dict[str, Any]]:
        """给页面上的按钮组用：

        顶层 = [全部题目, *科目, 默认题库]
        科目下 = [全部, *学习]
        学习下 = [全部, *专业]
        专业下 = [全部, *学校]

        每个 scope 都按 (科目, 学习, 专业, 学校) 4 段标识，scope.group 是「同一科目」标签。
        """
        tree: List[Dict[str, Any]] = []
        for scope in self._state[0]:
            option = scope.as_option()
            parts = scope.key.split("/")
            if not scope.group:
                tree.append({**option, "children": []})
                continue
            siblings = tree
            for depth, part in enumerate(parts):
                prefix = "/".join(parts[: depth + 1])
                child = next((item for item in siblings if item["value"] == prefix), None)
                if child is None:
                    child = {
                        "value": prefix,
                        "label": part,
                        "group": scope.group,
                        "count": option["count"],
                        "error": None,
                        "children": [],
                    }
                    siblings.append(child)
                if depth == len(parts) - 1:
                    child["count"] = option["count"]
                    child["error"] = option["error"]
                siblings = child["children"]
        return tree

    # ---------- 热加载 ----------

    def watched_files(self) -> List[Path]:
        return [*question_files(self.data_root), self.db_path]

    def stamp(self) -> tuple:
        """题库文件的指纹：路径 + 修改时间 + 大小。任何一项变了就该重新加载。"""
        out = []
        for path in self.watched_files():
            try:
                st = path.stat()
            except OSError:
                continue  # 刚被删掉/正在写，下次请求再看
            out.append((str(path), st.st_mtime_ns, st.st_size))
        return tuple(out)

    def reload(self) -> None:
        self._stamp = self.stamp()
        self.subjects = [s for s in list_subjects(self.data_root) if s not in self.hidden]
        scopes = self._build_scopes()
        self._state = (scopes, {s.key: s for s in scopes})
        self._indexes = {}  # 题目换了，索引跟着作废（新建字典，不动别人正在读的那个）

    def refresh_if_changed(self) -> bool:
        """文件没动就什么都不做（只有几十次 stat）；动了就重建，返回 True。"""
        if self.stamp() == self._stamp:
            return False
        self.reload()
        return True

    # ---------- 构建 ----------

    def _build_scopes(self) -> List[Scope]:
        """顺序 = 全部题目 -> 每科目的层级树（全部 → 学校 → 专攻）-> 默认题库。"""
        # StructuredPath = (subject, school, filename)，取第一项比较 hidden
        all_files = [p for (subj, _, _), p in structured_files(ALL_SUBJECTS, self.data_root)
                     if subj not in self.hidden]
        scopes = [self._load_scope(ALL_SUBJECTS, "全部题目", all_files)]
        for subject in self.subjects:
            scopes.extend(self._subject_scopes(subject))
        scopes.append(
            self._load_scope(
                DEFAULT_SUBJECT_KEY,
                f"默认题库（{self.db_path.name}）",
                [self.db_path] if self.db_path.exists() else [],
            )
        )
        return scopes

    def _subject_scopes(self, subject: str) -> List[Scope]:
        """一个科目 -> 学校 -> 一级专攻 -> 二级专攻 -> 题目。"""
        paths = [p for _, p in structured_files(subject, self.data_root)]
        if not paths:
            return []
        scopes: List[Scope] = []
        # 全部：聚合所有文件
        try:
            all_q = load_question_files(paths, self.aliases, base=self.data_root)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return [Scope(subject, f"{subject} · 全部", subject, [], str(exc))]
        scopes.append(Scope(subject, f"{subject} · 全部", subject, all_q))

        for school in list_schools(subject, self.data_root):
            school_paths = [p for ((_, sc, _), p) in structured_files(subject, self.data_root) if sc == school]
            school_q = load_question_files(school_paths, self.aliases, base=self.data_root)
            scopes.append(Scope(f"{subject}/{school}", f"{school}", subject, school_q))
            grouped: Dict[tuple[str, str], List[Path]] = {}
            for path in school_paths:
                primary, secondary, _ = filename_hierarchy(path)
                grouped.setdefault((primary, secondary), []).append(path)
            for (primary, secondary), category_paths in sorted(grouped.items()):
                primary_key = f"{subject}/{school}/{primary}"
                scopes.append(Scope(primary_key, primary, subject,
                                    load_question_files(category_paths, self.aliases, base=self.data_root)))
                secondary_key = f"{primary_key}/{secondary or primary}"
                scopes.append(Scope(secondary_key, secondary or primary, subject,
                                    load_question_files(category_paths, self.aliases, base=self.data_root)))
                for path in sorted(category_paths):
                    _, _, question = filename_hierarchy(path)
                    question_key = f"{secondary_key}/{question}"
                    scopes.append(Scope(question_key, question, subject,
                                        load_question_files([path], self.aliases, base=self.data_root)))
        return scopes

    def _load_scope(self, key: str, label: str, paths: List[Path]) -> Scope:
        try:
            questions = load_question_files(paths, self.aliases, base=self.data_root)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return Scope(key, label, questions=[], error=str(exc))
        return Scope(key, label, questions=questions)


def create_app(
    db_path: Path = DEFAULT_DB,
    config_path: Optional[Path] = None,
    encoder_spec: Optional[str] = None,
    data_root: Path = DATA_ROOT,
    min_score: Optional[float] = None,
    watch: bool = True,
    hidden: Optional[Iterable[str]] = None,
) -> Flask:
    config = load_config(config_path)
    if encoder_spec:
        config["encoder"] = encoder_spec
    if min_score is not None:
        config.setdefault("match", {})["min_score"] = min_score
    aliases = aliases_from_config(config)
    defaults = match_defaults(config)
    hidden_set = list(hidden) if hidden is not None else HIDDEN_SUBJECTS
    library = Library(Path(db_path), config, aliases, Path(data_root), hidden_set)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.config["TEMPLATES_AUTO_RELOAD"] = True  # 改模板也不用重启
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # 静态资源每次都要再验证（?v= 之外再加一道保险）
    app.config["LIBRARY"] = library
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "").strip().rstrip("/")
    try:
        rate_limit = max(0, int(os.environ.get("QUESTION_RATE_LIMIT", "120")))
    except ValueError:
        rate_limit = 120
    request_buckets: Dict[str, List[float]] = {}

    example = EXAMPLE_QUERY.read_text(encoding="utf-8") if EXAMPLE_QUERY.exists() else "{}"

    @app.before_request
    def reload_data_if_changed():
        """题库热加载：每个请求前 stat 一遍题库文件，变了就重建索引。

        加文件、删文件、改题目都是刷一下页面就生效，不用重启服务。
        """
        if not watch or request.endpoint in (None, "static"):
            return
        if library.refresh_if_changed():
            print(
                f"[热加载] 题库已更新：{len(library.subjects)} 个科目 / "
                f"{library.size(ALL_SUBJECTS)} 题（{'、'.join(library.subjects)}）",
                file=sys.stderr,
            )

    @app.before_request
    def protect_api():
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return ("", 204)
        """给公开 API 加轻量保护；生产环境仍建议叠加 Vercel WAF/鉴权。"""
        if not request.path.startswith("/api/") or rate_limit == 0:
            return
        now = time.monotonic()
        key = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        recent = [stamp for stamp in request_buckets.get(key, []) if now - stamp < 60]
        if len(recent) >= rate_limit:
            return jsonify({"error": "请求过于频繁，请稍后再试。"}), 429
        recent.append(now)
        request_buckets[key] = recent

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            if frontend_origin:
                response.headers.setdefault("Access-Control-Allow-Origin", frontend_origin)
                response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
                response.headers.setdefault("Vary", "Origin")
        return response

    def resolve_subject(raw: Any) -> tuple[str, Optional[tuple[Dict[str, str], int]]]:
        """把请求里的 subject 变成检索范围 key；不认识就连错误响应一起返回。"""
        subject = str(raw or "").strip()
        if not library.has(subject):
            choices = "、".join(library.label(k) for k in library.keys() if k != DEFAULT_SUBJECT_KEY)
            return subject, ({"error": f"没有这个科目：{subject}；可选：{choices}"}, 400)
        error = library.error(subject)
        if error:
            return subject, ({"error": f"科目「{library.label(subject)}」的题库读取失败：{error}"}, 500)
        return subject, None

    def clamp_topk(raw: Any) -> int:
        try:
            return max(1, min(MAX_TOPK, int(raw)))
        except (TypeError, ValueError):
            return defaults["topk"]

    def clamp_min_score(raw: Any) -> float:
        """没传就用 config 里的阈值；传了就夹到 0~1。"""
        if raw is None or raw == "":
            return defaults["min_score"]
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return defaults["min_score"]

    def run_match(query: Question, topk: Any, subject: str, min_score: Any) -> Dict[str, Any]:
        topk, threshold = clamp_topk(topk), clamp_min_score(min_score)
        index = library.index(subject)
        ranked = index.match(query, topk=topk)          # 已按分数降序
        kept = [m for m in ranked if m.score >= threshold]
        return {
            "matches": [{
                "id": m.question.qid,
                "school": str(m.question.raw.get("school") or m.question.raw.get("学校") or "").strip(),
                "year": str(m.question.raw.get("year") or m.question.raw.get("年度") or m.question.raw.get("年份") or "").strip(),
                "text": question_text(m.question),
                "score": round(m.score, 4),
                "scope": library.detail_scope(m.question.qid, subject),
            } for m in kept],
            "db_size": len(index),
            "subject": subject,
            "subject_label": library.label(subject),
            "min_score": round(threshold, 4),
            "best_score": round(ranked[0].score, 4) if ranked else None,
            "filtered": len(ranked) - len(kept),        # 因低于阈值而没显示的条数
        }

    @app.get("/")
    def home():
        from pipeline import available_backends  # 延迟导入：没装 OCR 也要能开页面

        # 静态资源用文件 mtime 做版本号：模板 / 前端代码改了刷新就生效，
        # 不用再清缓存或硬刷新（数据热加载靠 stamp() 单独处理）
        static_dir = Path(__file__).resolve().parent / "static"
        version = int(max(
            (p.stat().st_mtime for p in static_dir.glob("*") if p.is_file()),
        ) * 1000) if static_dir.exists() else 0
        return render_template(
            "index.html",
            scope_tree=library.chip_tree(),
            data_root=str(library.data_root),
            subject_count=len(library.subjects),
            total_count=library.size(ALL_SUBJECTS),
            # 默认显示第一个实际科目（首个 list_subjects，按字母序可能是「复变函数」）；
            # 当 browse 模式打开时，JS 会读取这个值填充第一个 dropdown。
            default_subject=library.subjects[0] if library.subjects else ALL_SUBJECTS,
            default_topk=defaults["topk"],
            default_min_score=defaults["min_score"],
            example=example,
            ocr_ready=bool(available_backends()),
            model_name=config.get("llm", {}).get("model", "MiniMax-M2.7"),
            asset_version=version,
        )

    @app.get("/api/subjects")
    def api_subjects():
        return jsonify({
            "subjects": library.options(),
            "tree": library.chip_tree(),     # 页面上的按钮组直接吃这个
            "default": ALL_SUBJECTS,
            "min_score": defaults["min_score"],
            "topk": defaults["topk"],
        })

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "service": "question-backend"})

    @app.post("/api/match")
    def api_match():
        payload = request.get_json(silent=True) or {}
        raw_query = payload.get("query")

        subject, failure = resolve_subject(payload.get("subject"))
        if failure:
            return jsonify(failure[0]), failure[1]

        if isinstance(raw_query, str):
            try:
                raw_query = json.loads(raw_query)
            except json.JSONDecodeError as exc:
                return jsonify({"error": f"JSON 格式有误：{exc.msg}（第 {exc.lineno} 行）"}), 400
        if not isinstance(raw_query, dict):
            return jsonify({"error": "请贴入一道题的 JSON 对象。"}), 400

        try:
            query = question_from_dict(raw_query, aliases, default_id="__web_query__")
        except (TypeError, ValueError) as exc:
            return jsonify({"error": f"题目字段有问题：{exc}"}), 400

        if not query.present_fields():
            return jsonify({"error": "这道题一个可比较的字段都没有，至少要填 knowledge_points 或 method。"}), 400

        return jsonify(run_match(query, payload.get("topk"), subject, payload.get("min_score")))

    @app.post("/api/similar")
    def api_similar():
        """只接收题目 ID；题目内容留在服务端，避免把完整 q.raw 发到浏览器。"""
        payload = request.get_json(silent=True) or {}
        qid = str(payload.get("id") or "").strip()
        if not qid:
            return jsonify({"error": "缺少题目 ID。"}), 400
        subject, failure = resolve_subject(payload.get("subject"))
        if failure:
            return jsonify(failure[0]), failure[1]
        # 题目 ID 从当前下拉层级定位；相似题则提升到当前科目，避免只在当前文件中排除自身后变成 0 条。
        query = next((q for q in library.questions(subject) if q.qid == qid), None)
        search_subject = subject.split("/")[0] if "/" in subject else subject
        if query is None and search_subject != subject:
            query = next((q for q in library.questions(search_subject) if q.qid == qid), None)
        if query is None:
            return jsonify({"error": "题目不存在或不属于当前检索范围。"}), 404
        return jsonify(run_match(query, payload.get("topk"), search_subject, payload.get("min_score")))

    @app.post("/api/match-image")
    def api_match_image():
        """图片 -> OCR -> MiniMax -> 题目 JSON -> 匹配。"""
        from pipeline import LLMError, MissingAPIKeyError, OcrError, extract_from_image

        subject, failure = resolve_subject(request.form.get("subject"))
        if failure:
            return jsonify(failure[0]), failure[1]

        upload = request.files.get("image")
        if upload is None or not upload.filename:
            return jsonify({"error": "没有收到图片。"}), 400

        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            return jsonify({
                "error": f"不支持的图片格式 {suffix or '(无后缀)'}，"
                         f"支持：{'、'.join(sorted(s.lstrip('.') for s in ALLOWED_IMAGE_SUFFIXES))}"
            }), 400

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            upload.save(tmp.name)
            try:
                extracted = extract_from_image(tmp.name, config, aliases)
            except MissingAPIKeyError as exc:
                return jsonify({"error": str(exc)}), 503
            except (OcrError, LLMError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 502

        body = run_match(
            extracted.question, request.form.get("topk"), subject, request.form.get("min_score")
        )
        body.update({
            "ocr_text": extracted.ocr_text,
            "ocr_backend": extracted.ocr_backend,
            "question_json": extracted.question_json,
            "warnings": extracted.warnings,
        })
        return jsonify(body)

    @app.get("/api/browse/questions")
    def api_browse_questions():
        """题目库展示：按科目/学校列出题目卡片，可按年份过滤。"""
        subject, failure = resolve_subject(request.args.get("subject"))
        if failure:
            return jsonify(failure[0]), failure[1]

        year = str(request.args.get("year", "")).strip()
        questions = library.questions(subject)

        items: List[Dict[str, Any]] = []
        years = set()
        for q in questions:
            raw_year = q.raw.get("year") or q.raw.get("年度") or q.raw.get("年份") or ""
            y = str(raw_year).strip()
            if y:
                years.add(y)
            if year and y != year:
                continue
            raw_school = q.raw.get("school") or q.raw.get("学校") or q.raw.get("source") or ""
            items.append({
                "id": q.qid,
                "school": str(raw_school).strip(),
                "year": y,
                "text": question_text(q),
                "answer": q.raw.get("answer") or [],    # 题目库展示用，匹配接口不返回
                # 针对原题的专属练习只随浏览接口返回，不进入 QuestionIndex。
                "practice_questions": q.raw.get("practice_questions") or [],
            })

        # 按数字年份降序排：平成N=1988+N、令和N=2018+N；同年内 winter 比普通晚半年（次年初考）排前
        def _year_num(y: str) -> int:
            import re
            m = re.match(r'(平成|令和)(\d+)年度', y or '')
            if not m: return 0
            return 1988 + int(m.group(2)) if m.group(1) == '平成' else 2018 + int(m.group(2))
        items.sort(key=lambda it: (_year_num(it["year"]), 1 if 'winter' in it["id"] else 0), reverse=True)
        return jsonify({
            "subject": subject,
            "subject_label": library.label(subject),
            "year": year,
            "years": sorted(years),
            "total": len(items),
            "questions": items,
        })

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": f"图片太大了，上限 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB。"}), 413

    return app


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="math-question-matcher 网页版")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="不选科目时用的题库 JSON / JSONL")
    parser.add_argument("--data-root", dest="data_root", default=str(DATA_ROOT),
                        help="科目根目录，每个子目录是一个科目（默认 data/）")
    parser.add_argument("--config", default=None, help="config JSON 路径")
    parser.add_argument("--encoder", default=None, help="hashing | hashing:<dim> | sbert:<model>")
    parser.add_argument("--min-score", dest="min_score", type=float, default=None,
                        help="检索阈值：分数低于它的结果不显示（默认取 config 的 match.min_score）")
    parser.add_argument("--no-watch", dest="watch", action="store_false",
                        help="关掉题库热加载（默认开：题库文件变了刷新页面就生效）")
    parser.add_argument("--reload", action="store_true",
                        help="连 Python 代码也热加载（改 .py 自动重启进程）")
    parser.add_argument("--hide-subjects", dest="hide_subjects", default=",".join(sorted(HIDDEN_SUBJECTS)),
                        help="不展示的科目，逗号分隔（默认隐藏非数学科：" + ",".join(sorted(HIDDEN_SUBJECTS)) + "）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    hidden_list = [s.strip() for s in args.hide_subjects.split(",") if s.strip()]
    app = create_app(
        Path(args.db), args.config, args.encoder, Path(args.data_root),
        args.min_score, args.watch, hidden_list,
    )
    subjects = list_subjects(Path(args.data_root)) or ["（无）"]
    shown = [s for s in subjects if s not in hidden_list]
    hidden_now = [s for s in subjects if s in hidden_list]
    threshold = match_defaults(load_config(args.config))["min_score"] if args.min_score is None else args.min_score
    print(f"科目目录：{args.data_root}（{'、'.join(subjects)}）\n"
          f"展示科目：{'、'.join(shown) or '（无）'}\n"
          f"隐藏科目：{'、'.join(hidden_now) or '（无）'}\n"
          f"默认题库：{args.db}\n"
          f"检索阈值：{threshold}\n"
          f"题库热加载：{'开（改完刷新页面即生效）' if args.watch else '关'}"
          f"{' ／ 代码热加载：开' if args.reload or args.debug else ''}\n"
          f"打开 http://{args.host}:{args.port}")
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=args.reload or args.debug,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
