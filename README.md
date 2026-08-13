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
python -m webapp.server --db 我的题库.json --port 9000    # 换题库/换端口
```

两个输入方式：

- **图片**：点选 / 拖进去 / Cmd+V 粘贴截图 → 自动 OCR → MiniMax 转 JSON → 匹配
- **题目 JSON**：已经有结构化 JSON 时直接贴（点「填入示例」拿模板）

**结果只列出匹配到的题目原文**，按分数从高到低排，不显示分数和字段明细。
OCR 文本和模型生成的 JSON 收在结果下方一个默认折叠的「提取过程」里，方便出错时核对。

题目原文取自题库条目的 `text` 字段，`stem` / `question` / `content` / `题目` / `题干` 也认；
一个都没有时会退化成「未提供题目原文 + 考点」。要改就动 `webapp/server.py` 里的 `TEXT_KEYS`。

两个接口，也能直接给别的程序调：

```bash
# 已有 JSON
curl -s -X POST http://127.0.0.1:8000/api/match \
  -H 'Content-Type: application/json' \
  -d '{"topk": 5, "query": {"knowledge_points": ["二次函数", "最值"], "question_type": "求最小值", "method": ["配方法", "顶点"]}}'
# -> {"db_size": 12, "matches": [{"text": "求二次函数 f(x) = 2x^2 + 8x - 3 的最小值是多少？"}, ...]}

# 传图片（OCR + 模型 + 匹配一步走）
curl -s -X POST http://127.0.0.1:8000/api/match-image -F "image=@题目.png" -F "topk=5"
# -> {"matches": [...], "ocr_text": "...", "ocr_backend": "vision", "question_json": {...}, "warnings": []}
```

`query` 传对象或 JSON 字符串都行；`topk` 上限 50；图片上限 16 MB。
错误码：400 参数问题，502 OCR/模型失败，503 没配 API key。想看分数明细就用下面的命令行。

## 命令行用法

```bash
# 匹配（默认用 data/questions.sample.json 作题库）
python -m mqm.cli match --query examples/query.json --topk 5

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
缺字段时权重重新归一、上面那个算例的总分（0.966），以及网页接口只返回题目原文、JSON 写错要有中文报错。

## 目录结构

```text
mqm/            匹配核心（不联网、不依赖 OCR，可单独当库用）
  schema.py     题目 JSON -> Question，别名归一
  structure.py  数学结构归一化
  similarity.py 各字段的相似度算法
  scoring.py    加权总分
  index.py      题库索引：召回 + 精排 + KNN baseline
  cli.py        命令行
pipeline/       图片 -> 题目 JSON
  ocr.py        Vision / tesseract 后端
  prompts.py    提示词
  llm.py        MiniMax 客户端（anthropic / openai 两种请求格式）
  extract.py    串流程 + 模型输出清洗
  cli.py        命令行
webapp/         网页版（Flask，/api/match 和 /api/match-image）
config/         权重、mode、别名表、OCR 与模型配置
data/           样例题库
examples/       样例 query
```

三层是解耦的：`mqm` 不知道 OCR 和模型的存在，`pipeline` 不知道匹配怎么算，
换 OCR 引擎或换模型都只动一个文件。
