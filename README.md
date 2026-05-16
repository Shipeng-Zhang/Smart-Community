# 智慧社区居家安全与能耗协同管理系统

一个面向真实社区治理场景的物联网课程项目，围绕日常生活中高频且高价值的问题进行设计：

- 厨房燃气泄漏
- 烟雾异常与空气质量下降
- 用电过载与晚高峰能耗异常
- 漏水隐患
- 老人户低活动异常

项目采用前后端分离架构，支持标准登录/注册、动态仿真、云边端协同说明与 OA 式工单流转。

## 当前亮点

- 标准登录 / 注册页面
- 动态仿真数据，不是静态预生成
- OA 风格的工单流转与通知中心
- 风险与能耗双趋势图，另附告警类型图
- 创新模块：告警关联闭环、分时能耗画像、老人户主动关怀
- 云边端部署方案说明

## 项目结构

```text
/mnt/e/iot
├─ src/smartcity_iot/                 # 后端核心
│  ├─ auth.py                         # 登录 / 注册 / 会话管理
│  ├─ hub.py                          # 业务中台、工单流转、KPI 聚合
│  ├─ simulator.py                    # 动态仿真引擎
│  ├─ server_oa_v2.py                 # 新版前后端服务入口
│  └─ models.py                       # 数据模型
├─ frontend_oa_v2/                    # 新版多页面前端
│  ├─ login.html
│  ├─ register.html
│  ├─ auth.css
│  ├─ auth.js
│  ├─ index.html
│  ├─ styles.css
│  └─ app.js
├─ start_community_system.py          # 推荐启动脚本
├─ 启动说明-智慧社区系统.md
└─ 云边端部署方案.md
```

## 启动方式

```bash
cd /mnt/e/iot
python3 start_community_system.py --port 8080
```

浏览器访问：

```text
http://127.0.0.1:8080/login.html
```

登录后进入主系统：

```text
http://127.0.0.1:8080/index.html
```

演示账号：

- 账号：`admin@community.local`
- 密码：`Admin@12345`

## API

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET /api/health`
- `GET /api/snapshot`
- `POST /api/sim/control`
- `POST /api/work-orders/action`

## 部署

云边端协同的推荐说明见：[云边端部署方案.md](./云边端部署方案.md)
