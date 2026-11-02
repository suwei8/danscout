# danscout

福彩3D / 排列三 预测帖定时聚合 → 数据入仓 → Cloudflare Pages 可视化面板。

## 数据流
GitHub Actions（UTC 10:30/11:50/12:38 ≈ 北京 18:30/19:50/20:38 三轮）：
sing-box(自建VLESS代理) → 采集两论坛当期帖子 → OpenCode 免费模型探测选优（文本+视觉）→ 提取规范化 → `data/<game>/<period>.json` 提交回仓 → Pages 自动部署。

## 结构
- `collector.py` 采集器（55125系走代理、17500 --resolve 绕 DNS）
- `aggregate.py` 规范化：predictor归组 + 胆码/复式/直组选提取 + 共识统计
- `probe_models.py` `opencode models` 全量探测选最快可用模型
- `bin/start-proxy.sh` 由 VLESS_URL 生成 sing-box 配置并启动
- `site/` 静态面板（Pages 托管，读 data/*.json）
- `data/models/<date>.json` 每日选模记录

## Secrets（仓库 Settings → Secrets → Actions）
- `VLESS_URL` 代理节点链接
- `TG_TOKEN` / `TG_CHAT_ID` 失败告警（粗粒度，仅失败发）

## 手动触发
Actions → danscout → Run workflow。
