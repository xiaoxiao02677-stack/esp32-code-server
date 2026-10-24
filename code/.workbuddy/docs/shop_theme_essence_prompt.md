# 电商小店·主题精华提示词（从 console-v2 提取，前后端对应版）

> 用途：把这份提示词整体交给代码生成 AI / 执行 agent，即可按现有网站风格做出电商小店。
> 提取日期：2026-10-21。来源：`yh/console-v2`（前端）+ `yh/manager-api`（后端）实测代码。
> 特点：所有数值均来自现有代码实值，非泛化描述；API 契约与现有 Java 后端一字不差。

---

## 第一部分：主提示词（可直接整段粘贴使用）

```
请为我开发一个电商小店网站，风格完全复刻下述设计体系（这是一个已在生产运行的
Vue3 控制台的设计基因，请严格按数值执行，不要自行发挥配色和圆角）。

【技术栈】
- 前端：Vue 3（<script setup> 组合式 API）+ vue-router（createWebHashHistory 哈希路由）
  + Vite 构建。不使用任何 UI 组件库——所有样式手写在一个 global.css 设计系统里。
  登录密码用 sm-crypto（SM2）加密。无 Pinia，全局状态用 localStorage + ref。
- 后端：Spring Boot + MyBatis-Plus，接口返回统一 Result<T> 包装。
- 部署：Vite 双产物模式——客户端构建 base='/' 输出 dist/，管理端构建
  mode='admin' base='/admincc/' 输出 dist-admin/；nginx 分别 alias 部署，
  共用同一后端反代 /yuhe/ → manager-api:8002。

【设计 tokens（CSS 变量，:root 定义）】
--primary:#1B6CFF; --primary-hover:#0F5AE0; --primary-soft:#EAF2FF;
--bg:#F5F7FA; --surface:#FFFFFF; --text:#1A2233; --text-sub:#8A94A6; --border:#E8ECF2;
--teal-1:#B8F3E2; --teal-2:#6FE0C6; --teal-3:#37C8A8;   /* 青绿有机渐变三元色 */
--orange:#FF7A45; --success:#2FBF71; --danger:#F0534D; --warning:#F5A623;
--radius-lg:24px; --radius-md:16px; --radius-pill:999px;
--shadow-dock:0 8px 32px rgba(27,44,80,.14); --shadow-card:0 2px 12px rgba(27,44,80,.05);
--z-dock:50; --z-dropdown:90; --z-modal:150; --z-toast:200; --z-force:300; --z-boot:400;
--sb-thumb:rgba(27,44,80,.16); --sb-thumb-hover:rgba(27,44,80,.30);
--font:"PingFang SC","HarmonyOS Sans SC","Source Han Sans SC","Microsoft YaHei",system-ui,sans-serif;
语义色用法：价格/促销强调用 --orange，加购成功 --success，删除/下架 --danger，库存预警 --warning。

【整体布局骨架（A10 滚动体系，必须照搬）】
- body { overflow:hidden } —— 文档滚动锁定，页面滚动收进内层容器，浏览器滚动条永不出现。
- .app-shell：height:100dvh + overflow-y:auto + overflow-x:hidden + scrollbar-gutter:stable
  + display:flex + justify-content:center；背景是两层径向光晕叠加底色
  radial-gradient(1200px 500px at 85% -10%, rgba(27,108,255,.06), transparent 60%),
  radial-gradient(900px 400px at 0% 110%, rgba(55,200,168,.07), transparent 60%), #E9EDF3；
  padding:20px 24px 32px calc(var(--dock-w) + 12px)（左侧给 dock 让位）。
- .app-canvas：max-width:min(1280px, calc(100vw - 152px))；border-radius:28px；
  background:var(--bg)；box-shadow:0 20px 60px rgba(27,44,80,.10)；padding:20px 28px 32px；
  overflow:hidden（服务圆角裁切，不许删）。
- 左侧 .dock 固定导航：width:max-content 夹取 72~140px 自适应，收起态 56px；
  高度 100dvh，overflow-y:auto（滚动条平时隐形、hover 显影）；
  背景 rgba(255,255,255,.92) + backdrop-filter:blur(18px)；border-radius:0 22px 22px 0。
  dock 底部 dock-foot：六色主题圆点切换器 + 紧凑模式按钮 + 端切换按钮。
- 顶栏 .topbar：左品牌（36px 圆角 logo + 800 字重品牌名 + 12px 副标），中间胶囊搜索框
  .searchbox（border 1px + radius-pill + 9px 16px padding + kbd 快捷键角标），
  右侧头像（40px 圆形 primary-soft 底）。

【核心组件（全部已有实现范式，按此复刻）】
1. 按钮：.btn 胶囊形 radius-pill + padding:10px 22px + 600 字重 + inline-flex + gap:7px。
   .btn-primary 蓝底白字带 0 4px 14px rgba(27,108,255,.35) 投影，hover 上浮 1px；
   .btn-ghost 白底 1.5px border，hover 变蓝；.btn-danger 红底。disabled opacity:.45。
2. 筛选 chip（分类 tab）：胶囊按钮，active 态 primary 边框 + primary-soft 底 + 600 字重。
3. 统计卡 .stat-card：radius-md 白卡 + shadow-card + 右上角 26px 半透明图标 +
   13px 灰 label + 30px 800 字重大数字 + note 小注；数字用 tabular-nums 防抖动。
   电商用法：今日成交/待发货/商品数/低库存预警 四卡横排 grid(4,1fr)。
4. 表格面板 .panel + .panel-head（标题前 8px 蓝点装饰）+ .data-table：
   th 浅灰底 12px 字重600；td padding:14px 20px；行 hover 高亮；数字列 tabular-nums。
   分页器 .pager：共N条 + 每页条数下拉 + ‹ 1 … 4 5 6 … 20 ›（窗口式页码）。
5. 加载骨架屏：与表格行同构的灰色圆角条 shimmer（1.2s ease-in-out infinite，50% opacity:.4），
   不用转圈。
6. 弹窗 .modal-mask（fixed 全屏 rgba(15,22,40,.45) + grid place-items:center）+
   .modal（radius:20px + padding:26px + max-height:min(88dvh,88vh) + overflow-y:auto
   + overscroll-behavior:contain 防穿透）。ESC 可关、确认按钮自动聚焦。
7. Toast 通知栈：右上角滑入，success/error/info 三态各配图标，2600ms 自动消失，
   hover 暂停计时。
8. Hero 区（页面气质担当）.hero-blob：300px 宽青绿有机渐变卡
   linear-gradient(160deg, teal-1 0%, teal-2 55%, teal-3 100%)，radius:26px，
   内部两个白色半透明"生物形态"圆形 ::before/::after 缓慢浮动（blobFloat 9s/7s），
   右下角 74px 白色 3D 浮雕方块（inset 阴影 + rotate(14deg) + 6s 浮动动画）放 emoji。
   电商用法：左侧放店铺招牌语+CTA按钮，右侧四张统计卡。
9. 页头范式 .page-head：h1 26px/800 字重（如"订单 管理"，后半段 primary 蓝色）+
   13px 灰 sub 副标；右侧 head-actions 放主操作按钮组。

【六套主题系统（电商换肤卖点）】
html[data-theme] 覆盖变量，dock 底部 18px 渐变圆点切换，localStorage 'cc_theme' 持久化：
blue 蓝白(默认 #1B6CFF) / kawaii 奶油粉(#F9A8D4系, body#FFE9F1) / dark 深色(#0B1120底,
dock半透明深蓝) / purple 紫(#7C3AED) / green 绿(#16A34A) / morandi 莫兰迪(#8B9DAF系)。
六套皮肤 = 六种店铺风格，切换即时生效无需刷新。

【交互细节红线】
- 滚动条全站统一：thin + 软色圆角 thumb（scrollbar-width:thin + ::-webkit-scrollbar 8px）。
- 键盘可达：Tab 焦点环 outline:2px solid var(--primary)（:focus-visible）；skip-link 跳主内容。
- 所有过渡 .15s~.25s ease；按钮 hover 上浮 translateY(-1px)；图标 hover scale(1.12)。
- 开机 boot 进度条：顶部 4px 蓝→青绿渐变横条 0.32s 展开，路由就绪即撤。

【前后端契约（与现有 manager-api 严格对应，新接口照此风格加）】
- 响应体：{code:0, msg:'', data:...}；code=0 才成功；code=401 登录过期（跳登录）；
  HTTP 层可能仍 200，业务码在前端判。
- 鉴权：Bearer token（localStorage 'cc_token'），登录 = GET /user/captcha?uuid= →
  GET /user/publicKey 取 SM2 公钥 → 密码 SM2 加密 POST 登录。
- REST 路径范式（照 OrderController 现有六件套）：
  GET /xxx/page（分页）、GET /xxx/info/{id}、POST /xxx/create、PUT /xxx/update、
  DELETE /xxx/delete/{id}、GET /xxx/export。
- 实体范式：MyBatis-Plus @TableName，字段 userName/contact/product/amount/
  paymentTime/shippingAddress/status/remark + createDate/updateDate/creator/updater。
  【订单表 order_table 已存在且管理端已有订单管理页——电商下单直接写这张表，
  管理端零改动即可发货管理】。
- 分页返回 PageData<Map> 结构；前端 DataTable 组件直接消费。
- 导航模块可见性由管理端"展示配置"控制（visible:false 才隐藏），新页面注册进
  customerItems/adminItems 数组即自动纳入权限体系。

【电商化页面映射（两套产物）】
客户端 dist/（顾客逛店）：
- /shop 首页：hero-blob 店招 + stats 四卡 + 商品橱窗 grid（商品卡=stat-card 变体，
  图 1:1 白卡 + 名称 + orange 价格 + 加购胶囊按钮）
- /shop/goods/:id 商品详情：左图右购（数量 stepper + btn-primary 立即购买 + ghost 加购）
- /shop/cart 购物车：data-table 变体 + 底部结算条
- /shop/orders 我的订单：chips 状态筛选(待付款/待发货/已发货/已完成) + data-table
- 复用已有：/customer/profile 个人中心、/customer/points 积分(营销积分直接用)
管理端 dist-admin/（老板管店，大部分白捡）：
- 订单管理 /admin/orders —— 已存在，order_table 直连，改状态即发货
- 数据概览 /admin —— stats-grid 换成成交额/订单数/转化漏斗
- 新增：商品管理（CRUD 六件套 + 上下架 chip）、库存管理（低库存 warning 色预警）
- 已有可复用：用户管理、角色权限、审计日志、字典、展示配置(控制客户端显隐)
```

---

## 第二部分：数值速查表（执行时对照）

### 配色全景

| 用途 | 变量 | 值 |
|---|---|---|
| 主操作/链接/active | --primary | #1B6CFF |
| 主色 hover | --primary-hover | #0F5AE0 |
| 主色浅底（选中态/chip active/头像底） | --primary-soft | #EAF2FF |
| 页面底 | --bg | #F5F7FA |
| 卡片/表面 | --surface | #FFFFFF |
| 主文字 | --text | #1A2233 |
| 次文字/label | --text-sub | #8A94A6 |
| 边框 | --border | #E8ECF2 |
| Hero 渐变（浅→深） | --teal-1/2/3 | #B8F3E2 → #6FE0C6 → #37C8A8 |
| 价格/促销 | --orange | #FF7A45 |
| 成功（上架/加购） | --success | #2FBF71 |
| 危险（删除/下架） | --danger | #F0534D |
| 警告（低库存） | --warning | #F5A623 |
| 外层画布底（径向光晕叠加处） | — | #E9EDF3 |

### 字号体系（全站实测值）

- 页面 h1：26px / 800 / letter-spacing .5px（后半词 primary 蓝）
- 面板 h3：16px / 700（前置 8px 蓝点）
- hero h2：24px / 800 / 白字 + 文字阴影
- stat-value：30px / 800 / tabular-nums
- 正文/表格：13.5px；按钮 14px/600；chip 13px；hint/sub 12~13px 灰
- hero 内英文眉题：11px / 700 / letter-spacing 3px（"ORDERS / SALES" 式）

### 圆角/阴影/层级

- 圆角：卡片 16px（--radius-md）、大容器/弹窗 20px、画布 28px、hero 26px、
  按钮与输入框 999px 胶囊、dock 右侧 22px
- 阴影：卡片 0 2px 12px rgba(27,44,80,.05)；dock 0 8px 32px rgba(27,44,80,.14)；
  主按钮 0 4px 14px rgba(27,108,255,.35)；画布 0 20px 60px rgba(27,44,80,.10)
- z-index 只允许用 token：50/90/150/200/300/400，禁止魔数

### 关键动效

| 动效 | 参数 |
|---|---|
| 按钮 hover | translateY(-1px)，.15s |
| 图标 hover | scale(1.12)，.18s |
| hero 生物形态浮动 | blobFloat 9s / 7s（reverse），rotate 14°↔10° + translateY -9px |
| 3D 浮雕块 | blobFloat 6s |
| 骨架屏 | sk-fade 1.2s infinite（50% opacity .4） |
| 开机进度条 | boot-fill .32s（8%→100% 宽度） |
| toast 进出 | transition-group 滑入淡出 |
| 通用过渡 | all .15s / .25s ease |

---

## 第三部分：前后端对应明细（新增模块时照抄）

### 现成可白捡的模块（电商零开发）

| 电商需求 | 现有实现 | 位置 |
|---|---|---|
| 订单管理（含导出 Excel） | OrderController 六件套 + Orders.vue | manager-api/.../order/ + views/admin/Orders.vue |
| 订单表 | order_table（userName/contact/product/amount/paymentTime/shippingAddress/status/remark） | OrderEntity.java |
| 用户体系 | sys_user + 角色 + SM2 登录 | modules/security |
| 权限/角色 | Roles.vue + hasAdminRole | 前端 lib/api.js |
| 操作审计 | AuditLog.vue | views/admin/ |
| 字典（商品分类等枚举） | Dicts.vue + dict_type/dict_data | views/admin/Dicts.vue |
| 模块显隐（店铺装修开关） | DisplayConfig → isModuleVisible | DockNav.vue:161-164 |
| 积分（营销） | Points.vue | views/customer/ |
| 个人中心 | Profile.vue | views/customer/ |

### 需新增的模块（照现有范式）

| 模块 | 前端 | 后端 | 表 |
|---|---|---|---|
| 商品管理 | views/admin/Goods.vue（复刻 Orders.vue 结构：page-head + hero-row + stats-grid + DataTable + modal 表单） | GoodsController（六件套） | shop_goods（name/cover/price/stock/category/status/sort/remark + 审计四件套 createDate/updateDate/creator/updater） |
| 购物车 | views/customer/Cart.vue | CartController | shop_cart（user_id/goods_id/qty/checked） |
| 商品橱窗 | views/customer/Shop.vue（hero-blob 店招 + 商品 grid） | 复用 /goods/page + 分类参数 | — |
| 下单结算 | views/customer/Checkout.vue | OrderController 扩展 /order/createByCart | 写 order_table |

### API 层三条铁律（从 api.js 逐字提取）

1. `data.code === 401` → 清 token 跳登录（在途请求也拦截）；`code !== 0` 一律 throw `{code, msg}`。
2. token 存 localStorage 'cc_token'，JSON 包装 `{token, loginAt, expire}`，提前 5 分钟预警过期。
3. API_BASE 固定 '/yuhe'（nginx 同源反代，无 CORS）；所有请求头 `Authorization: Bearer <token>`。

### 部署对应（生产 nginx 已验证结构）

```
客户端产物 dist/    → /var/www/<新站>/app/   （location = / 和 /assets/）
管理端产物 dist-admin/ → /var/www/<新站>/admin/（location /admin/ 和 /admincc/ alias）
后端                → 同一 manager-api:8002，新 Controller 加包即用
vite.config.js 双模式：mode==='admin' ? base '/admincc/' : base '/'，outDir 同步切换
```

---

## 第四部分：验收清单

1. 打开新店页面与现有控制台并排看：圆角、投影、按钮、滚动条、弹窗、toast 六项视觉一致
2. 六套主题切换在新站同样生效（localStorage cc_theme 同 key 双站联动）
3. 管理端登录后左侧 dock 出现"订单管理"，能直接看到客户端下的单（order_table 走通）
4. 顾客下单 → order_table 落一行 → 管理端 Orders.vue 刷新可见 → 改 status 为已发货 →
   顾客"我的订单"chips 筛选正确
5. 移动端 375px 宽：dock 收起 56px、商品橱窗单列、结算条吸底
6. 键盘 Tab 可走完下单流程（焦点环可见）
