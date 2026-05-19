# 会话记忆

## 人格设定
- 我的名字：夏云
- 用户称呼：lulu
- 风格：干练高效，直接了当

## MCP 工具箱
- context7（文档查询）
- gh_grep（GitHub 代码搜索）
- flowus（FlowUs API）
- obsidian（Obsidian 笔记）
- pdf-mcp（PDF 读取 + OCR 识别）

## 可用 Skills
- huashu-nuwa（女娲造人）
- customize-opencode（配置 opencode）
- x-mastery-mentor（X/Twitter 运营）
- andrej-karpathy-perspective
- ilya-sutskever-perspective
- paul-graham-perspective
- steve-jobs-perspective
- elon-musk-perspective
- feynman-perspective
- munger-perspective
- naval-perspective
- taleb-perspective
- trump-perspective
- sun-yuchen-perspective
- zhang-yiming-perspective
- zhangxuefeng-perspective
- mrbeast-perspective
- wenrumin-perspective

## 模型
- 模型：opencode/big-pickle（免费，OpenCode 内置 API）
- 仅此一个，不接其他供应商（之前 OpenRouter 导致内置 API 失效）
- OpenRouter 已配置为备用 provider，不影响内置 API

## Gitee 备份
- 私人仓库：gitee.com/xiayun880512/opencode-config
- 已双远程：GitHub + Gitee

## ⚠️ 一键恢复（出问题时找我）
- 项目根目录双击 `.opencode\restore.bat`
- 或手动：`git pull` + 复制 `global-config.backup.json` 到 `~\.config\opencode\opencode.json`
- 重启 OpenCode 即可

## 省 token 技巧
- 关掉不用的 MCP
- 复杂任务分流（用 Task tool 派子代理）
- 不一次性读大文件，按需分段读
- 会话太长开新会话，避免上下文膨胀
- 优先用 grep/glob 定位，不盲目读文件

## 会话记录
- 2026-05-19：完成全部配置（opencode.json + memory + backup + pdf-mcp），已提交 Git
- 2026-05-19（晚）：移除 FlowUs MCP、省 token 技巧入库、加 OpenRouter 备用、同步备份到 Git
- 2026-05-19（晚）：打通 Gitee 双远程备份
