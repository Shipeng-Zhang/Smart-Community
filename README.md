# 智慧社区居家安全与能耗协同管理系统

一个面向日常生活的物联网课程项目，围绕老旧社区常见问题设计：

- 燃气泄漏
- 烟雾异常
- 用电过载
- 漏水隐患
- 老人户低活动异常

系统采用前后端分离架构，后端持续动态仿真，前端提供类似 OA 的工单流转与实时驾驶舱展示。

## 项目结构

```text
//iot
├─ src/smartcity_iot/     # 后端核心
├─ frontend/              # 独立前端页面
├─ start_community_system.py
├─ tests/
└─ 启动说明-智慧社区系统.md
```

## 启动方式

```bash
cd /mnt/e/iot
python3 start_community_system.py --port 8080
```

浏览器访问：

```text
http://127.0.0.1:8080
```

## 功能

- 实时刷新住户状态
- 动态生成告警与通知
- 工单派单、处理、闭环、重新打开
- 暂停 / 继续 / 手动步进模拟
- 风险趋势、楼栋画像、设备态势可视化

## 接口

- `GET /api/health`
- `GET /api/snapshot`
- `POST /api/sim/control`
- `POST /api/work-orders/action`

## 测试

```bash
python3 -m unittest discover -s tests -v
```

