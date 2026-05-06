# 持仓导入规则

## 不直接拿账号权限

不要把 Steam 密码、2FA、网页登录 Cookie、浏览器会话或平台登录权限交给脚本或 Codex。

原因：

- 这些权限可以控制账号资产，泄漏风险太高。
- Steam 交易锁定期内的私有库存不适合通过非官方会话抓取。
- 项目目标是分析和复盘，不是托管账号权限。

## 安全导入方式

推荐你自己从已登录的 Steam、悠悠有品、BUFF、C5 或交易记录页面整理 CSV，然后让项目读取 CSV。

最小字段：

```csv
market_hash_name,quantity,entry_price,platform,buy_date
AK-47 | Slate (Field-Tested),1,30.00,YOUPIN,2026-05-06
```

可选字段：

```text
category,stop_price,target_price,notes,plan
```

导入命令：

```powershell
python scripts\import_holdings.py your_holdings.csv
```

追加导入：

```powershell
python scripts\import_holdings.py your_holdings.csv --append
```

导入后复查：

```powershell
python scripts\portfolio_review.py
```

## 自动化边界

可以自动化：

- 读取你提供的 CSV。
- 用 SteamDT 查询当前价格、盘口和 K 线。
- 计算 T+7 解锁日、止损线、目标价和仓位建议。
- 生成持仓复查报告。

不自动化：

- 登录 Steam。
- 读取私有库存会话。
- 代替你执行交易。
- 保存账号密码、2FA 或 Cookie。
