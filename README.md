# Paper Library Kit

一个由 **Claude Code** 驱动的论文库生成工具。告诉 AI 一个 arXiv 链接，它会自动下载 PDF、生成缩略图、写结构化笔记、更新数据库。

![screenshot](https://raw.githubusercontent.com/placeholder/paper-library-kit/main/docs/screenshot.png)

## 快速开始

**前置条件：**
- Python 3（自带，无需安装其他依赖）
- [Claude Code](https://claude.ai/code)
- poppler（生成封面缩略图）：`brew install poppler`（macOS）或 `apt-get install poppler-utils`（Linux）

**启动：**

```bash
git clone https://github.com/your-username/paper-library-kit
cd paper-library-kit
python3 server.py
# 浏览器打开 http://localhost:8765
```

## 用法

打开 Claude Code，直接说：

> 帮我加这篇论文：https://arxiv.org/abs/2402.10329

AI 会自动完成：下载 PDF → 生成封面图 → 更新数据库 → 写笔记（可选）。

**从现有 PDF 文件夹批量导入：**

> 帮我初始化，PDF 在 ~/Downloads/papers/

AI 会扫描文件夹，自动识别 arXiv ID、抓取元数据、批量导入。

**其他常用指令：**
- `帮我给 UMI 写深度笔记` — 读 PDF 全文，输出结构化研究笔记
- `新增一个分类：强化学习` — 在 UI 里添加新分类
- `把 DexUMI 移到 RL 分类` — 修改论文归类

## UI 功能

- 按**分类**或**机构**两种视角浏览
- 点击缩略图 → PDF **右侧分屏预览**（ESC 关闭）
- 点击缩略图（无 PDF）→ 内嵌打开官网/arXiv
- 搜索框全文搜索（标题/简称/机构/备注）
- 在线编辑分类、新增/删除论文，**自动保存**（带乐观锁防冲突）
- ★ 标记里程碑论文

## 项目结构

```
paper-library-kit/
├── CLAUDE.md          ← AI 操作手册（所有自动化行为由此驱动）
├── server.py          ← 本地 HTTP 服务器
├── index.html         ← 前端 UI
├── papers.json        ← 论文数据库（唯一数据源）
├── references/        ← PDF 文件
│   └── thumbs/        ← 封面缩略图
├── notes/             ← 结构化研究笔记（Markdown）
└── scripts/
    └── gen_thumb.sh   ← 批量生成缩略图
```

## 自定义库标题

编辑 `papers.json` 顶层的 `meta` 字段：

```json
{
  "meta": {
    "title": "我的机器人论文库",
    "subtitle": "按方向分类 · 由 Claude Code 维护"
  }
}
```

## 支持作者

这个项目完全免费开源。如果它帮你节省了整理论文的时间，欢迎请作者喝杯咖啡 ☕

<img src="docs/wechat_pay.png" width="200" alt="微信收款码" />

## License

MIT
