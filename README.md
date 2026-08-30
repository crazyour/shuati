# math-question-matcher

按「字段分别比较 + 加权综合打分」检索相似数学题。

输入是你自己产出的结构化 JSON（每道题一条），本项目只负责**匹配**这一层：

```text
query.json ──┐
             ├─> 召回(倒排 + 向量粗筛) ─> 字段级相似度 ─> 加权总分 ─> 排序 ─> Top-K
题库 db.json ─┘
```

## 为什么不是整份 JSON 直接 KNN

整份 JSON 拼成一个 embedding 再做 cosine KNN，会被「表面相似」带偏：

- 题 A：考点/考法完全一致，只有数字不同 → 应该高分
- 题 B：文字和公式都很像，但**问法不同** → 应该低分

本项目默认走字段级打分；同时保留 `--baseline` 跑整份 JSON 的 KNN，两个排序并排看差异。
`python -m mqm.cli compare` 就是这个对照实验（样例题库里专门放了 A/B 两类干扰项）。

一点实话：如果 JSON 写得足够干净，整份 embedding 的 KNN 在**头部**也能命中题 A——
差别出在排序的中段，以及 baseline 无法回答"为什么像"。字段级打分给的是可解释、可调权重的分数，
出了问题你能定位到是 K 低还是 Q 低，而不是只有一个 cosine 值。

## 打分公式

```text
Score = 0.35·K + 0.35·M + 0.15·S + 0.10·Q + 0.05·D
```

| 符号 | 字段 | 相似度算法 | 默认 mode |
|---|---|---|---|
| K | `knowledge_points` | 集合软匹配：每个元素找对面最佳匹配，再合成一个分 | `query_biased` |
| M | `method` | 同上 | `query_biased` |
| S | `math_structure` | 模板归一化后比结构：type + 单项式集合 + 变量个数 | — |
| Q | `question_type` | 别名归一 + 文本相似 | — |
| D | `difficulty` | `1 - abs(Δ) / scale`（默认 scale=5，差 1 档 → 0.8） | — |
| P | `solution_steps` | 顺序敏感（软 LCS），默认权重 0，需要时在 config 里打开 | `lcs` |

集合字段可选的 mode（`mqm/similarity.py`）：

| mode | 含义 | 例：query=[二次函数,最值] vs cand=[二次函数,最值,顶点] |
|---|---|---|
| `query_coverage` | query 的每个元素是否都被覆盖到 | 1.00 |
| `query_biased` | `0.7·query_coverage + 0.3·f1`，**默认** | 0.94 |
| `mean` / `f1` | 双向覆盖度的算术 / 调和平均，`f1` 最严 | 0.90 / 0.80 |
| `jaccard` | 纯字面交并比，不用向量 | 0.67 |

选 `query_biased` 是因为：candidate 比 query 多列几个考点，通常只是标注粒度不同，不该重罚；
而 query 的考点没被覆盖到，才是真的不像。要更严就把 mode 改成 `f1`。

权重、mode、难度 scale 全在 [config/default.json](config/default.json) 里改。
`weights` 是**按字段覆盖**：只写一个字段时，其余字段沿用默认权重，想让某字段完全不参与就显式写 0。

**某个字段在 query 或 candidate 缺失时会被跳过，剩下的权重自动重新归一化**，不会因为缺字段就凭空扣分；
`ScoreResult.weight_covered` 会告诉你这次打分覆盖了原始权重的百分之多少。

`solution_steps` 即使权重为 0 也会照常计算并出现在 `--json` 的 breakdown 里，
所以出现同分（样例里 q-0001 和 q-0004 都是 0.958）时，给它一个 0.03~0.05 的小权重就能打破平局。

## 安装

```bash
cd ~/Desktop/math-question-matcher
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

默认编码器是 `hashing`（字符 n-gram 哈希，纯 numpy、离线、确定性），零模型下载即可跑通。
想换成真正的中文语义向量：

```bash
pip install sentence-transformers
python -m mqm.cli match --query examples/query.json --encoder sbert:BAAI/bge-small-zh-v1.5
```

编码器是可插拔的（`mqm/encoders.py` 里的 `Encoder` 协议），换成你自己的 API 向量服务只需加一个类。

## 图片 -> 题目 JSON（OCR + MiniMax）

```text
图片 ──OCR(Apple Vision)──> 题目文本 ──MiniMax-M2.7──> 题目 JSON ──> 匹配
```

### 1. 配 API key

```bash
cp .env.example .env      # 然后把 MINIMAX_API_KEY 填进去（.env 已 gitignore）
# 或者： export MINIMAX_API_KEY=你的key
```

端点和模型默认取自你本机 `~/.minimax/config.yaml` 里那套网关：

| 项 | 默认值 | 覆盖方式 |
|---|---|---|
| base_url | `https://agent.minimaxi.com/mavis/api/v1/llm/v1` | `MINIMAX_BASE_URL` 或 config 的 `llm.base_url` |
| model | `MiniMax-M2.7` | `MINIMAX_MODEL`（如 `MiniMax-M2.7-highspeed`） |
| 请求格式 | `anthropic`（Messages API，`POST {base_url}/messages`） | `MINIMAX_API_STYLE=openai` 切成 `/chat/completions` |

请求格式默认选 Anthropic，是因为那份 config 里 provider 用的是 `@ai-sdk/anthropic`。
如果你用的是 MiniMax 开放平台的 key（不是 MiniMax Code 那套网关），把 `base_url` 换成平台文档给的地址、
`MINIMAX_API_STYLE` 设成 `openai` 即可。认证头两种都会带（`x-api-key` 和 `Authorization: Bearer`），
所以网关认哪个都行。报错会告诉你是哪一层不对：401/403 提示 key，404 提示 base_url 或 model。

M2.7 是强制思考模型，响应里会有 `thinking` 块，客户端只取 `text` 块；
也因此默认**不发** `temperature`（避免和强制思考冲突），要发就在 config 里把 `llm.temperature` 填上数字。

### 2. OCR

默认用 macOS 自带的 Vision 框架（`pip install ocrmac`）：离线、不用下模型、中文识别好。
备选 tesseract（`brew install tesseract tesseract-lang`），config 里 `ocr.backend` 可选 `auto` / `vision` / `tesseract`。

OCR 会丢上下标（`x²` 常被读成 `x2`），这件事写进提示词了，由模型按数学常识还原成 `x^2`。

### 3. 用

```bash
# 图片 -> JSON，直接打印
python -m pipeline.cli --image 题目.png

# 存成文件，再走匹配
python -m pipeline.cli --image 题目.png --out /tmp/q.json
python -m mqm.cli match --query /tmp/q.json --explain

# 一步到位：图片直接匹配（OCR 文本和生成的 JSON 打到 stderr）
python -m mqm.cli match --image 题目.png --explain

# 只看 OCR 结果，不调模型（省钱调试）
python -m pipeline.cli --image 题目.png --ocr-only

# 跳过 OCR，只调模型（调提示词用）
python -m pipeline.cli --text "已知二次函数 y=3x2+6x-2，求它的最小值。" --verbose
```

提示词在 [pipeline/prompts.py](pipeline/prompts.py)，模型输出的清洗/纠错在 `pipeline/extract.py`
的 `normalize_question_json`（难度夹到 1~5、单字符串补成列表、多余字段丢掉、`text` 兜底填 OCR 原文）。

## 网页版

```bash
python -m webapp.server                                  # 打开 http://127.0.0.1:8000
python -m webapp.server --db 我的题库.json --port 9000    # 换默认题库/换端口
python -m webapp.server --data-root ~/题库目录            # 换科目根目录
python -m webapp.server --reload                         # 连 .py 也热加载（改代码自动重启）
```

**题库是热加载的**：往 `data/` 里加文件、加科目目录、改题目、删文件，刷新页面就生效，不用重启服务
（每个请求前 `stat` 一遍题库文件，指纹变了才重建索引；下拉框的题数、页脚也跟着变）。
想固定成启动时那一份就加 `--no-watch`。模板改动同样即时生效；只有改 Python 代码需要 `--reload`。

两个输入方式：

- **图片**：点选 / 拖进去 / Cmd+V 粘贴截图 → 自动 OCR → MiniMax 转 JSON → 匹配
- **题目 JSON**：已经有结构化 JSON 时直接贴（点「填入示例」拿模板）

搜索前先选「检索范围」（科目 / 学校）和「相似度阈值」，见下面两节。

结果排版：一道题一张卡片，题设、公式、每个小问各占一行；题目里的 `$...$` 和 `$$...$$`
由 KaTeX 渲染成公式（CDN 引入，拿不到就原样显示 LaTeX，不影响匹配）。
所以题库的 `text` 建议直接写 LaTeX，例如：

```text
设 $x$ 为实数，考虑矩阵
$$A=\begin{pmatrix}x&0&1\\0&x&1\\1&1&x\end{pmatrix}$$
(1) 求 $A$ 的特征值 $\lambda_1\le\lambda_2\le\lambda_3$ 及各自对应的特征向量。
(2) 取 $x=0$，求对任意正整数 $n$ 的 $A^n$ 的表达式。
```

**结果只列出匹配到的题目原文**，按分数从高到低排，不显示分数和字段明细。
OCR 文本和模型生成的 JSON 收在结果下方一个默认折叠的「提取过程」里，方便出错时核对。

题目原文取自题库条目的 `text` 字段，`stem` / `question` / `content` / `题目` / `题干` 也认；
一个都没有时会退化成「未提供题目原文 + 考点」。要改就动 `webapp/server.py` 里的 `TEXT_KEYS`。

三个接口，也能直接给别的程序调：

```bash
# 有哪些范围可选（含默认阈值）。subjects 是拍平的列表，tree 是页面按钮组用的两级结构
curl -s http://127.0.0.1:8000/api/subjects
# -> {"default": "__all__", "min_score": 0.35, "topk": 5,
#     "subjects": [{"value": "__all__", "label": "全部题目", "group": "", "count": 181, "error": null}, ...],
#     "tree": [{"value": "线性代数", "label": "线性代数", "count": 66,
#               "children": [{"value": "线性代数/九州大学", "label": "九州大学", "count": 18}, ...]}, ...]}

# 已有 JSON（subject 指定检索范围，min_score 覆盖阈值）
curl -s -X POST http://127.0.0.1:8000/api/match \
  -H 'Content-Type: application/json' \
  -d '{"topk": 5, "subject": "线性代数/九州大学", "min_score": 0.4,
       "query": {"knowledge_points": ["特征值与特征向量"], "question_type": "求特征值"}}'
# -> {"subject": "线性代数/九州大学", "subject_label": "九州大学", "db_size": 18,
#     "min_score": 0.4, "best_score": 0.958, "filtered": 2, "matches": [{"text": "..."}, ...]}

# 传图片（OCR + 模型 + 匹配一步走）
curl -s -X POST http://127.0.0.1:8000/api/match-image \
  -F "image=@题目.png" -F "topk=5" -F "subject=线性代数" -F "min_score=0.35"
# -> {"matches": [...], "ocr_text": "...", "ocr_backend": "vision", "question_json": {...}, "warnings": []}
```

`query` 传对象或 JSON 字符串都行；`topk` 上限 50；`min_score` 夹到 0~1，不传就用 config 里的；图片上限 16 MB。
错误码：400 参数问题（含范围名写错，会把可选项列出来），500 该科目的题库读不动，
502 OCR/模型失败，503 没配 API key。想看分数明细就用下面的命令行。

## 检索范围：科目 / 学校

`data/` 下**每个装着题库文件的子目录就是一个科目**；科目里再按「来源」细分，
来源取每道题的 `school` / `学校` / `source` / `来源` 字段，没写就退回文件名——
所以「按学校选」和「按文件选」是同一套机制：

```text
data/
  questions.sample.json     <- 根目录下的文件算进「全部题目」，但不单独成科目
  线性代数/
    九州大学.json            <- 里面每题带 "school": "九州大学"
    东京大学.json            <- 同一科目的多个文件合并成一个索引
  微积分/
    ...
```

网页版的「检索范围」是两级按钮组，科目全部平铺出来、各自带题数，不用翻下拉框：

```text
检索范围  线性代数 · 66 题
[全部题目 181] [复变函数 12] [形式语言与自动机 18] [微分方程 12] [情报理论 18]
[概率统计 18] [线性代数 66 ▾] [解析微积分 7] [计算机组成原理 18]
[默认题库（questions.sample.json） 12]

学校  [全部 66] [九州大学 18] [東北大学 48]      <- 点了带 ▾ 的科目才出现
```

科目后面有 `▾` 表示它下面有两所以上学校可以再选（只有一所时第二排不出现，因为和「全部」是同一批题）。
题库热加载后，切回页面时按钮组会自动跟着更新。
带范围直接打开：`http://127.0.0.1:8000/?subject=线性代数/九州大学`。

| 选项 | 值（API 的 `subject`） | 范围 |
|---|---|---|
| 全部题目 | `__all__` | 整个 `data/` 目录，含根目录下的文件 |
| 科目全部 | `线性代数` | `data/线性代数/` 下的全部文件 |
| 某个来源 | `线性代数/九州大学` | 该科目里 school（或文件名）= 九州大学 的题 |
| 默认题库 | `""`（不传也一样） | `--db` 指定的那个文件，默认 `data/questions.sample.json` |

命令行同样可以选：

```bash
python -m mqm.cli subjects                                             # 列出所有可选范围和题数
python -m mqm.cli match --subject 线性代数 --query /tmp/q.json          # 整个科目
python -m mqm.cli match --subject 线性代数/九州大学 --query /tmp/q.json  # 只看这所学校
python -m mqm.cli match --subject 线性代数 --image 题目.png --explain
```

给了 `--subject` 就忽略 `--db`；范围写错会把可选项列出来。`--data-root` 可以换科目根目录。

多个文件合并时，**不同文件撞 id** 会给后来的那条加上文件名前缀（比如两个文件都没写 id、
各自退化成 `q-0000`），一道题都不会被悄悄丢掉；同一个文件里重复 id 仍然直接报错。
网页版启动时某个科目读挂了不影响其它科目，请求到它时才报错。

## 检索阈值

**分数低于阈值的结果一律不显示**，默认 `0.35`，在 [config/default.json](config/default.json) 的
`match.min_score` 里改，也可以按次覆盖（网页上的「相似度阈值」输入框 / API 的 `min_score` /
命令行的 `--min-score`）。

这条是防「选错范围还硬凑结果」的：同一科目的相似题一般在 0.4 以上，跨科目的凑数题只有 0.1~0.17，
中间有很宽的间隔。样例库里实测：

```text
线代 query  → 线代题库    0.72 / 0.69 / 0.69 ...   ← 阈值 0.35 全部保留
线代 query  → 二次函数题库 0.16 / 0.14 / 0.14 ...   ← 一条都不给，而不是拿不相关的题凑
```

没有结果时不会只显示空列表，而是告诉你最相似的一条差多少：
「里没有相似度 ≥ 0.35 的题，最相似的一条也只有 0.16」——你就知道是范围选错了还是阈值太严。
接口响应里对应 `min_score`（本次阈值）、`best_score`（过滤前的最高分）、`filtered`（被挡掉几条）。

## 命令行用法

```bash
# 匹配（默认用 data/questions.sample.json 作题库）
python -m mqm.cli match --query examples/query.json --topk 5

# 只在某个科目里找（data/线性代数/ 下的全部 JSON）
python -m mqm.cli match --subject 线性代数 --query examples/query.json

# 看每个字段的分数明细
python -m mqm.cli match --query examples/query.json --explain

# 字段级打分 vs 整份 JSON KNN，并排对比
python -m mqm.cli compare --query examples/query.json

# 机器可读输出
python -m mqm.cli match --query examples/query.json --json
```

Python 里调用：

```python
from mqm import QuestionIndex, load_config, load_questions, load_question

cfg = load_config("config/default.json")
index = QuestionIndex(load_questions("data/questions.sample.json"), config=cfg)
for m in index.match(load_question("examples/query.json"), topk=5):
    print(m.qid, round(m.score, 3), m.breakdown)   # breakdown = 各字段分数
```

按范围建索引，并带上阈值：

```python
from mqm import QuestionIndex, list_sources, list_subjects, load_config, load_scope, match_defaults

cfg = load_config()
print(list_subjects())                        # ['线性代数', ...]
print(list_sources("线性代数"))                # ['九州大学', ...]
index = QuestionIndex(load_scope("线性代数/九州大学"), config=cfg)
index.match(query, topk=5, min_score=match_defaults(cfg)["min_score"])
```

## 题目 JSON 格式

字段全部可选，缺了就跳过：

```json
{
  "id": "q-0001",
  "knowledge_points": ["二次函数", "函数最值", "顶点"],
  "question_type": "求最值",
  "method": ["配方法", "顶点式", "判断最值"],
  "solution_steps": ["识别二次函数", "完成平方", "得到顶点", "读取最小值"],
  "math_structure": {
    "type": "quadratic_function",
    "template": "y = a*x^2 + b*x + c",
    "variable_count": 1
  },
  "difficulty": 2,
  "text": "可选，原题文本，只用于 KNN baseline 和人工核对"
}
```

`math_structure` 也接受直接写字符串（`"y=ax^2+bx+c"`），会自动解析成 type/单项式/变量数。

## 结构归一化在做什么

`mqm/structure.py` 把模板变成「和具体数字无关」的签名（`python -m mqm.cli inspect` 可直接看）：

```text
y = 2x^2 - 3x + 1    ─┐
y = a*x^2 + b*x + c  ─┼─> normalized="y=c+c*x^1+c*x^2"  单项式={const,x^1,x^2}  deg=2  quadratic_function
y = x^2 - 4x + 7     ─┘   系数和常数一律记作 c，于是"只有数字不同"的两题结构分 = 1.00

y = a*(x-h)^2 + k     ──> deg=2  quadratic_function     顶点式不会被括号骗成一次函数
a*x^2 + b*x + c = 0   ──> quadratic_equation            左边不是单纯因变量 -> 判为方程
y = a*sin(2x) + b     ──> trigonometric_function         sin/cos/log/exp/sqrt 单独识别，不计入多项式次数
```

两条启发式，不合你的题库习惯就改 `structure.py`：

- 变量：`x y z t u v θ` 视为变量，其余单字母视为系数占位符（`VAR_HINTS`）
- `variable_count`：只数表达式那一侧的自变量，因变量（`y=` / `S=` / `f(x)=`）不计入

这一层只做多项式级别的启发式解析，不接符号计算库。要更严格（比如真正展开、判断同解方程），
把 `parse_structure` 换成 sympy 实现即可，签名不用变。

## 别名归一

[config/aliases.json](config/aliases.json) 按字段分开配置同义词，在加载阶段就归一：

```text
求最小值 / 求最大值 / 最值问题  ->  求最值
配方 / 完全平方 / 配成完全平方  ->  配方法
抛物线                          ->  二次函数
```

这一层比 embedding 便宜也更可控，建议把你题库里高频的说法都塞进去。

注意默认表把 `求最大值` 和 `求最小值` 都归到 `求最值`——即"求最大值"的题会被当成同一考法。
要区分就删掉这两条。

## 实际效果

样例题库里放了两个典型干扰项：q-0001（考点考法一致、只有数字不同）和 q-0002（文字公式几乎一样、
但问的是对称轴）。`compare` 的输出：

```text
 #  字段级加权打分                          整份 JSON KNN(baseline)
 1  q-0001 0.958  求二次函数 f(x) = 2x^2…    q-0001 0.786  求二次函数 f(x) = 2x^2…
 …
 5  q-0011 0.854  已知二次函数 y = x^2 +…    q-0002 0.651  已知函数 y = x^2 - 4x…   <- 问法不同却排到第 5
 7  q-0002 0.631  已知函数 y = x^2 - 4x…     …                                       <- 字段级打分把它压到第 7
```

q-0002 被压下去，靠的是 Q(question_type)=低分 + M(method) 只有部分重合；
而 q-0001 拿到 S=1.00 是因为结构归一化把数字抹掉了。

## 测试

```bash
pytest -q
```

锁死的行为：数字不同不影响结构分、顶点式次数判断、函数名不被误当变量、问法不同必须排在数字不同之后、
缺字段时权重重新归一、上面那个算例的总分（0.966），以及网页接口只返回题目原文、JSON 写错要有中文报错、
选了范围就只在那个范围里找（按 school 分来源、跨文件撞 id 不丢题、范围写错要列出可选项）、
阈值挡掉跨科目结果并报出最高分（阈值可按次覆盖、夹到 0~1）、
题库热加载（加文件/加科目/改题目/删文件都不用重启，`--no-watch` 能关掉）。

## 目录结构

```text
mqm/            匹配核心（不联网、不依赖 OCR，可单独当库用）
  schema.py     题目 JSON -> Question，别名归一
  structure.py  数学结构归一化
  similarity.py 各字段的相似度算法
  scoring.py    加权总分
  index.py      题库索引：召回 + 精排 + KNN baseline
  library.py    检索范围：科目目录的发现、按来源分组、合并加载
  cli.py        命令行
pipeline/       图片 -> 题目 JSON
  ocr.py        Vision / tesseract 后端
  prompts.py    提示词
  llm.py        MiniMax 客户端（anthropic / openai 两种请求格式）
  extract.py    串流程 + 模型输出清洗
  cli.py        命令行
webapp/         网页版（Flask，/api/subjects、/api/match、/api/match-image）
config/         权重、mode、别名表、OCR 与模型配置
data/           题库：根目录放样例，每个子目录是一个科目
examples/       样例 query
```

三层是解耦的：`mqm` 不知道 OCR 和模型的存在，`pipeline` 不知道匹配怎么算，
换 OCR 引擎或换模型都只动一个文件。
