# Paper Library Kit — AI 操作手册

这是一个由 AI Agent 驱动的论文库生成工具。你（AI）基于这个工具帮用户搭建并维护他们自己的论文知识库。

---

## 🚀 首次安装（用户说"帮我建一个论文库"时）

用户不需要懂编程。你来负责所有操作，只在必要时问用户几个问题。

### 第 1 步：确认安装位置

使用交互式提问（如 `AskUserQuestion`）询问：
- 问题："你想把论文库安装在哪里？"
- 选项 1（推荐）："~/paper-library（默认）"
- 选项 2："当前目录"
- Other：用户可输入任意路径

根据回答确定安装目录（默认 `~/paper-library`），然后克隆仓库：

```bash
# 克隆仓库到目标目录（如果目录已存在且非空则跳过克隆，直接使用）
git clone https://github.com/doubleLLL3/paper-library-kit ~/paper-library
cd ~/paper-library
```

### 第 2 步：检查并安装依赖

```bash
# 检查 Python 3
python3 --version || { echo "需要安装 Python 3"; exit 1; }

# 检查 poppler（生成封面缩略图）
if ! command -v /opt/homebrew/bin/pdftoppm &>/dev/null && ! command -v pdftoppm &>/dev/null; then
  echo "正在安装 poppler..."
  # macOS
  command -v brew &>/dev/null && brew install poppler
  # Linux
  command -v apt-get &>/dev/null && sudo apt-get install -y poppler-utils
fi
```

### 第 3 步：问用户 2 个问题

使用交互式提问（如 `AskUserQuestion`）一次提出两个问题：

**问题 1 — 库的名字**
- header: "库的名字"
- 选项 1（推荐）："Paper Library（默认）"
- 选项 2："AI 论文库（示例）"
- Other：用户自定义名称

**问题 2 — 现有 PDF 文件夹**
- header: "现有 PDF"
- 选项 1："没有，跳过"
- 选项 2："~/Downloads/papers（示例，点 Other 输入实际路径）"
- Other：实际文件夹路径

**端口**：只有当用户主动提到端口冲突时才问，否则默认用 `8765`。

### 第 4 步：写入配置

根据用户的回答，更新 `papers.json` 里的 `meta` 字段：
```json
{
  "meta": {
    "title": "用户给的名字",
    "subtitle": "按分类浏览 · 由 AI Agent 维护"
  }
}
```

### 第 5 步：导入现有 PDF（如果用户有）

按照本文档「初始化：从现有 PDF 文件夹导入」章节执行。

### 第 6 步：启动服务器

```bash
cd ~/paper-library   # 换成实际安装路径
bash start.sh        # 后台启动，启动失败会自动报错
```

### 第 7 步：告诉用户完成了

用一段简洁的话告知用户：

> 论文库已经准备好了！
>
> 🌐 打开浏览器访问：**http://localhost:8765**
>
> 之后你可以直接告诉我：
> - "帮我加这篇论文：[arxiv 链接 或 论文名]"
> - "帮我批量导入 [文件夹路径] 里的 PDF"
> - "帮我给 [论文名] 写深度笔记"

---

## 项目结构

```
paper-library/
├── CLAUDE.md              ← 你正在读的这个文件
├── server.py              ← 本地 HTTP 服务器（Python 3，无需安装依赖）
├── index.html             ← 前端 UI
├── papers.json            ← 所有论文/产品数据（唯一数据源）
├── references/            ← PDF 文件存放目录
│   └── thumbs/            ← 论文封面缩略图（PNG）
├── notes/                 ← 结构化笔记（Markdown）
│   └── template.md        ← 笔记模板
└── scripts/
    └── gen_thumb.sh       ← 批量生成缩略图脚本
```

---

## 初始化：从现有 PDF 文件夹导入

用户说"帮我初始化"或"我有一个装满 PDF 的文件夹"时，执行以下流程：

### 第 1 步：确认源文件夹

询问用户 PDF 所在目录路径，例如 `~/Downloads/papers/` 或 `~/Zotero/storage/`。

```bash
ls /path/to/pdf-folder/*.pdf
```

列出所有 PDF，告诉用户共找到多少个，让他确认继续。

### 第 2 步：逐一刮削每个 PDF

对每个 PDF 文件，按以下顺序尝试获取元数据：

**① 从文件名猜测 arXiv ID**（最快）

常见命名模式：
- `2402.10329.pdf` → arXiv ID = `2402.10329`
- `UMI_2402.10329.pdf` → arXiv ID = `2402.10329`
- `2402.10329v2.pdf` → arXiv ID = `2402.10329`

正则：`\b(\d{4}\.\d{4,5})\b`

**② 从 arXiv API 获取完整元数据**（有 arXiv ID 时）

```bash
curl -s "https://export.arxiv.org/api/query?id_list={arXiv_ID}"
```

从返回的 Atom XML 中提取：
- `<title>` → 论文标题
- `<author><name>` → 第一作者
- `<arxiv:affiliation>` 或 `<summary>` → 机构信息
- `<published>` → 发表年份

**③ 从 PDF 文本提取**（无法识别 arXiv ID 时）

```bash
/opt/homebrew/bin/pdftotext -f 1 -l 2 "/path/to/file.pdf" -
```

读第 1-2 页，从文本开头提取标题（通常是最大字号的第一行）和机构信息。

### 第 3 步：生成简称（Short name）

规则（按优先级）：
1. 如果标题里有冒号，取冒号前的部分（如 `UMI: Universal...` → `UMI`）
2. 如果标题是缩写词开头，取该缩写（如 `DexUMI:...` → `DexUMI`）
3. 否则取标题前两个实词的首字母缩写
4. 实在无法判断，用文件名（去掉 arXiv ID 部分）

### 第 4 步：复制 PDF + 生成缩略图

```bash
# 复制并重命名到 references/
cp "/source/path/xxx.pdf" "references/{短名}_{arXiv_ID}.pdf"

# 生成缩略图（脚本自动跳过已有的，只处理新增的）
bash scripts/gen_thumb.sh
```

### 第 5 步：归类

- 如果用户在初始化前已经设置了分类，询问用户把这篇放到哪个分类
- 如果是批量导入（>5 篇），先全部放入 `general` 分类，后续让用户在 UI 里手动拖拽归类
- 如果 `papers.json` 里还没有 `general` 分类，自动创建：
  ```json
  { "id": "general", "color": "#64748b", "title": "未分类", "tag": "待整理" }
  ```

### 第 6 步：汇总报告

所有 PDF 处理完后，输出一张表：

```
已导入 12 篇论文：
✅ UMI (2402.10329)          — 识别来源: arXiv API
✅ DexUMI (2505.21864)       — 识别来源: arXiv API
✅ FastUMI (2409.19499)      — 识别来源: arXiv API
⚠️  unknown_paper.pdf        — 未找到 arXiv ID，已用 PDF 文本提取标题，请手动确认
❌  corrupted.pdf            — PDF 无法读取，已跳过

建议：对标记 ⚠️ 的条目手动补充 arXiv ID 或检查标题是否正确。
```

---

## 启动服务器

```bash
cd /path/to/paper-library
python3 server.py
# 浏览器打开 http://localhost:8765
```

---

## 核心任务：添加一篇论文

用户说"帮我加这篇论文：https://arxiv.org/abs/XXXX.XXXXX"时，按以下步骤执行：

### 第 1 步：确定基本信息

从 URL 提取 arXiv ID（如 `2402.10329`），然后读 PDF 或 arXiv 页面获取：
- 完整标题
- 简称（Short name，如 `UMI`、`DexUMI`）
- 机构（如 `Stanford University`、`NVIDIA`）
- 机构类型：`school`（学校/研究院）/ `company`（公司）/ `lab`（实验室）
- 发表年份

### 第 2 步：下载 PDF

命名规则：`{短名}_{arXiv_ID}.pdf`

```bash
curl -L "https://arxiv.org/pdf/{arXiv_ID}" -o "references/{短名}_{arXiv_ID}.pdf"
```

示例：
```bash
curl -L "https://arxiv.org/pdf/2402.10329" -o "references/UMI_2402.10329.pdf"
```

### 第 3 步：生成封面缩略图

命名规则：`{短名}_{arXiv_ID}-01.png`，存放在 `references/thumbs/`

```bash
bash scripts/gen_thumb.sh
```

脚本会自动检测 poppler 路径（macOS/Linux 均支持），跳过已有缩略图，只处理新增的 PDF。如果 poppler 未安装，脚本会给出安装提示。

### 第 4 步：更新 papers.json

读取 `papers.json`，在 `papers` 数组末尾追加一条记录。

**papers.json 字段说明：**

```jsonc
{
  "id": "唯一标识符（英文小写+连字符，如 umi 或 dex-umi）",
  "cat": "分类 ID（必须是 categories 里存在的 id）",
  "short": "简称（如 UMI、DexUMI）",
  "star": false,         // true = 标记为里程碑
  "type": "paper",       // "paper" 或 "product"
  "title": "完整英文标题",
  "note": "一句话描述：机构 · 核心创新 · 关键指标",
  "arxiv": "2402.10329", // arXiv ID，论文必填
  "pdf": "UMI_2402.10329.pdf",     // references/ 下的文件名
  "thumb": "UMI_2402.10329-01.png",// thumbs/ 下的文件名
  "url": null,           // 产品/官网链接（product 类型时填）
  "org": "Stanford University",
  "orgType": "school"    // "school" | "company" | "lab"
}
```

**关于分类（cat 字段）：**
- 如果现有分类里没有合适的，先向用户确认是否新增分类
- 新分类需要在 `categories` 数组里添加对应条目（id、color、title、tag）
- 默认分类 ID 是 `general`，任何论文都可以先放这里

**如果是非 arXiv 的产品/公司：**
```jsonc
{
  "id": "figure-ai",
  "cat": "robotics",
  "short": "Figure AI",
  "type": "product",
  "title": "Figure 02 — General Purpose Humanoid Robot",
  "note": "Figure AI · 双足人形机器人，OpenAI 合作",
  "url": "https://figure.ai",
  "thumb": "figure02-01.png",   // 可选，手动截图放入 thumbs/
  "org": "Figure AI",
  "orgType": "company"
}
```

### 第 5 步：写结构化笔记（可选，用户要求时）

笔记文件名：`notes/{arXiv_ID}_{短名}.md`

参考模板：`notes/template.md`

---

## 管理分类

`papers.json` 里的 `categories` 数组定义所有分类：

```jsonc
{
  "id": "umi",           // 唯一标识，英文小写
  "color": "#0AB5A8",    // 16进制颜色，用于 UI 高亮
  "title": "UMI 类",     // 显示名称
  "tag": "手持外设，末端轨迹采集"  // 副标题描述
}
```

用户说"新增分类"或现有分类不合适时，向 `categories` 追加条目，同时更新 `papers.json`。

---

## 修改库的标题和描述

编辑 `papers.json` 顶层的 `meta` 字段：

```jsonc
{
  "meta": {
    "title": "My Paper Library",
    "subtitle": "按主题分类的论文知识库"
  },
  "categories": [...],
  "papers": [...]
}
```

---

## 写深度笔记（深度研究一篇论文）

用户说"帮我深度研究 XXX"或"给 XXX 写笔记"时：

1. 读取 PDF：`/opt/homebrew/bin/pdftotext -f 1 -l N "references/XXX.pdf" -`
   - 先读前 4 页（摘要+方法），再读实验页
   - Linux 用 `pdftotext`（同路径逻辑）
2. 按 `notes/template.md` 的结构写笔记
3. 保存到 `notes/{arXiv_ID}_{短名}.md`

**笔记重点关注：**
- 数据怎么用的（预训练/微调/BC/RL）
- 有真机验证的任务和成功率
- 对用户自己研究路线的启示

---

## 批量生成缩略图

如果 `references/` 下有 PDF 但 `references/thumbs/` 里缺少对应缩略图：

```bash
bash scripts/gen_thumb.sh
```

---

## 常见问题

**Q: 服务器端口被占用？**
```bash
python3 server.py 8766   # 指定其他端口
```

**Q: 保存时提示"文件已被修改"？**
刷新浏览器页面后再保存，服务器有乐观锁防止冲突覆盖。

**Q: 添加的论文在 UI 里看不到？**
检查 `cat` 字段的值是否在 `categories` 里有对应 `id`。

**Q: 缩略图不显示？**
确认文件在 `references/thumbs/` 下，文件名与 `papers.json` 里的 `thumb` 字段完全一致（大小写敏感）。
