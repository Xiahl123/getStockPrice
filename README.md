# 股票实时价格提醒（iTick + 飞书）

Python 后端服务：通过 iTick WebSocket 订阅实时报价，当**相对当日开盘价**涨跌幅度达到阈值时，经飞书机器人提醒；也可在飞书里增删股票、修改百分比。

## 关于 iTick 免费版

| 项目 | 免费版限制 |
| --- | --- |
| WebSocket 连接 | 1 条 |
| 同时订阅标的 | **最多 3 只** |
| REST | 约 5 次/分钟 |

本服务默认按免费版设计（单连接 + 上限 3）。如果经常要盯超过 3 只，建议：

1. **升级 iTick**（订阅数更高，最省事），并把 `.env` 里 `ITICK_MAX_SUBSCRIPTIONS`、`ITICK_WS_URL` 改成付费地址；或
2. **仅美股且可接受延迟**：可考虑 Finnhub 免费 WebSocket（额度更大，但亚洲市场较弱）；或
3. 接受 REST 轮询方案（延迟更高，本项目未采用）。

对个人「少量重仓股」实时提醒，**iTick 免费版足够用**。

## 快速开始

```bash
cd getStockPrice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 ITICK_TOKEN、FEISHU_APP_ID、FEISHU_APP_SECRET
python -m app.main
```

## 环境变量（`.env`）

完整示例见 [.env.example](.env.example)。必填：

- `ITICK_TOKEN`：iTick API Token  
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书企业自建应用凭证  
- 建议填写 `FEISHU_ALERT_CHAT_ID`：告警默认会话（启动后可对机器人发 `/chatid` 获取）

可选：

- `FEISHU_WEBHOOK_URL`：群自定义机器人 Webhook（只推送，不收命令）  
- `DEFAULT_ALERT_PERCENT`：默认阈值（%）  
- `ALERT_COOLDOWN_SECONDS`：同向告警冷却时间  

## 飞书应用配置

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → 创建**企业自建应用**  
2. **添加应用能力 → 机器人**  
3. **权限管理**（应用身份）至少开通：
   - `im:message` / `im:message:send_as_bot`（发消息）
   - `im:message.p2p_msg:readonly`（收单聊）
   - `im:message.group_at_msg:readonly`（收群内 @）
4. **事件与回调**：
   - 先在本机启动本服务（建立长连接）
   - 订阅方式选 **使用长连接接收事件**
   - 添加事件：`im.message.receive_v1`（接收消息）
5. 创建版本并**发布**；把机器人拉进目标群，或私聊机器人  
6. 对机器人发送 `/chatid`，把返回的 ID 写入 `FEISHU_ALERT_CHAT_ID` 后重启

## 飞书命令

```
/add AAPL US 2.5     # 添加美股 Apple，开盘价涨跌 ≥2.5% 提醒
/add 700 HK 3        # 添加腾讯港股
/add 600519 CN 2     # 添加贵州茅台（A股）
/del AAPL US         # 删除
/set 700 HK 4        # 改阈值
/list                # 列表
/chatid              # 查会话 ID
/help                # 帮助
```

提醒逻辑：`|(最新价 - 开盘价) / 开盘价 * 100| ≥ 阈值`。同一方向默认冷却 300 秒，避免刷屏。

## 项目结构

```
app/
  main.py           # 入口
  config.py         # 环境变量
  store.py          # 监控列表持久化 (data/watches.json)
  itick_client.py   # iTick WebSocket
  alert_engine.py   # 涨跌幅判定
  feishu_bot.py     # 飞书收发与命令
.env.example
requirements.txt
```

## 运行注意

- 机器需能访问公网（连接 iTick 与飞书长连接）。  
- 免费版改监控列表会重连并重新订阅，属正常行为。  
- 非交易时段可能收不到 quote 或 `open` 为 0，此时不会误报。
