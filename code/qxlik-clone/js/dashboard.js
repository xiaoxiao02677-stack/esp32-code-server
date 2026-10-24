/* Dashboard 渲染：菜单 + 问候语 + 统计 + 消息列表 + 设备表格（照搬源站结构） */
(function () {
  'use strict';

  /* ---------- 演示数据（取自源站 dashboard 实际渲染值） ---------- */
  var STATS = {
    messages: 186,
    devices: 0,
    roles: 0,
    users: 1
  };

  var MESSAGES = [
    { type: 'ai',    text: '觉渊 于 2026-08-20 09:51:47 回复: 好的，那我给您讲一个小故事吧。\n\n从前，有一只小狐狸，它住在一个美丽的森林里。小狐狸非常好奇，总是喜欢探索森林里的每一个角落。有一天，它在森林里发现了一棵巨大的老树，树上有一个小小的洞……', time: '2026-08-20 09:51:47' },
    { type: 'user',  text: 'esp-vocat 于 2026-08-20 09:51:47 发送: 讲个故事。', time: '2026-08-20 09:51:47' },
    { type: 'ai',    text: '觉渊 于 2026-08-20 09:51:29 回复: "长沙当前多云，气温33.1度，北风0级，湿度71%，空气质量指数36（优），09:40更新。"', time: '2026-08-20 09:51:29' },
    { type: 'user',  text: 'esp-vocat 于 2026-08-20 09:51:28 发送: 今天天气怎么样？', time: '2026-08-20 09:51:28' },
    { type: 'ai',    text: '觉渊 于 2026-08-20 09:50:59 回复: 您好！我在听着呢。您是想说什么事情吗？或者需要我帮您查询天气、设置提醒、播放音乐之类的？请告诉我您的需求吧。', time: '2026-08-20 09:50:59' },
    { type: 'user',  text: 'esp-vocat 于 2026-08-20 09:50:59 发送: 真的。', time: '2026-08-20 09:50:59' }
  ];

  var DEVICES = []; // 源站当前为空表

  /* ---------- 问候语（源站 greeting 逻辑：按小时） ---------- */
  function greetingText(name) {
    var h = new Date().getHours();
    var greet;
    if (h < 6) greet = '夜深了';
    else if (h < 9) greet = '早上好';
    else if (h < 12) greet = '上午好';
    else if (h < 14) greet = '中午好';
    else if (h < 18) greet = '下午好';
    else if (h < 23) greet = '晚上好';
    else greet = '夜深了';
    var follows = ['要不要打一把游戏', '休息一会儿吧', '准备吃什么呢', '我猜你可能累了'];
    var follow = follows[Math.floor(Math.random() * follows.length)];
    return greet + '，' + name + '，' + follow;
  }

  /* ---------- 渲染侧边栏菜单 ---------- */
  function renderMenu() {
    var menu = document.getElementById('sidebar-menu');
    var html = '';

    var items = [
      { key: 'dashboard', icon: 'dashboard', title: 'Dashboard', active: true },
      { key: 'user', icon: 'team', title: '用户管理' },
      { key: 'device', icon: 'robot', title: '设备管理' },
      { key: 'role', icon: 'user', title: '角色配置' }
    ];
    items.forEach(function (it) {
      html += '<div class="menu-item' + (it.active ? ' selected' : '') + '" data-key="' + it.key + '">'
        + '<span class="menu-icon">' + iconSvg(it.icon) + '</span>'
        + '<span class="menu-title">' + it.title + '</span>'
        + '</div>';
    });

    // 记忆管理子菜单（源站为 submenu）
    html += '<div class="submenu-title" id="submenu-memory">'
      + '<span class="menu-icon">' + iconSvg('database') + '</span>'
      + '<span class="menu-title">记忆管理</span>'
      + '<span class="submenu-arrow"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></span>'
      + '</div>'
      + '<div class="submenu-children" id="submenu-memory-children">'
      + '<div class="menu-item" data-key="memory-chat"><span class="menu-icon">' + iconSvg('message') + '</span><span class="menu-title">短期记忆</span></div>'
      + '<div class="menu-item" data-key="memory-summary"><span class="menu-icon">' + iconSvg('fileText') + '</span><span class="menu-title">记忆总结</span></div>'
      + '<div class="menu-item" data-key="memory-long"><span class="menu-icon">' + iconSvg('archive') + '</span><span class="menu-title">长期记忆</span></div>'
      + '</div>';

    menu.innerHTML = html;

    // 子菜单展开/收起
    document.getElementById('submenu-memory').addEventListener('click', function () {
      this.classList.toggle('open');
      document.getElementById('submenu-memory-children').classList.toggle('open');
    });

    // 菜单点击：选中态 + 面包屑更新
    menu.querySelectorAll('.menu-item').forEach(function (el) {
      el.addEventListener('click', function () {
        menu.querySelectorAll('.menu-item').forEach(function (n) { n.classList.remove('selected'); });
        el.classList.add('selected');
        var title = el.querySelector('.menu-title').textContent;
        document.getElementById('breadcrumb-active').textContent = title;
        if (el.dataset.key !== 'dashboard') {
          renderPlaceholder(title);
        } else {
          renderDashboard();
        }
      });
    });
  }

  /* ---------- 渲染 Dashboard 内容 ---------- */
  function renderDashboard() {
    var view = document.getElementById('dashboard-view');
    var user = (function () {
      try { return sessionStorage.getItem('qx-clone-user') || '小智'; } catch (e) { return '小智'; }
    })();

    var msgHtml = MESSAGES.map(function (m) {
      return '<div class="message-item' + (m.type === 'user' ? ' user-message' : '') + '">'
        + '<div class="message-content">'
        + '<div class="message-text">' + escapeHtml(m.text) + '</div>'
        + '<div class="message-time">' + m.time + '</div>'
        + '</div></div>';
    }).join('');

    var deviceRows = DEVICES.length
      ? DEVICES.map(function (d) {
          var online = d.online === 1;
          return '<tr><td>' + escapeHtml(d.name) + '</td><td>' + escapeHtml(d.role) + '</td>'
            + '<td><span class="status-tag ' + (online ? 'online' : 'offline') + '"><span class="tag-dot"></span>' + (online ? '在线' : '离线') + '</span></td>'
            + '<td>' + escapeHtml(d.lastOnline || '—') + '</td></tr>';
        }).join('')
      : '<tr><td colspan="4"><div class="table-empty">暂无数据</div></td></tr>';

    view.innerHTML =
      '<div class="user-info-card">'
      + '<div class="card-body"><div class="user-info-content">'
      + '<div class="user-avatar">' + escapeHtml(user.charAt(0)) + '</div>'
      + '<div class="user-greeting">'
      + '<h2>' + escapeHtml(greetingText(user)) + '</h2>'
      + '<p class="daily-sentence" title="点击翻译">"Rain on the roof is the sky\'s lullaby."</p>'
      + '</div>'
      + '<div class="user-statistics">'
      + '<div class="statistic-item"><div class="statistic-title">对话总数</div><div class="statistic-value">' + STATS.messages + '</div></div>'
      + '<div class="statistic-item"><div class="statistic-title">设备总数</div><div class="statistic-value">' + STATS.devices + '</div></div>'
      + '<div class="statistic-item"><div class="statistic-title">智能体总数</div><div class="statistic-value">' + STATS.roles + '</div></div>'
      + '</div>'
      + '</div></div>'
      + '</div>'
      + '<div class="content-grid">'
      + '<div class="qx-card">'
      + '<div class="card-head"><span class="card-title">对话管理</span><span class="card-extra">共 ' + MESSAGES.length + ' 条</span></div>'
      + '<div class="card-body"><div class="chat-messages"><div class="message-list">' + msgHtml + '</div></div></div>'
      + '</div>'
      + '<div class="qx-card">'
      + '<div class="card-head"><span class="card-title">设备管理</span><span class="card-extra">共 ' + DEVICES.length + ' 台</span></div>'
      + '<div class="card-body">'
      + '<table class="qx-table"><thead><tr><th>设备名称</th><th>角色名称</th><th>在线</th><th>最后在线时间</th></tr></thead>'
      + '<tbody>' + deviceRows + '</tbody></table>'
      + '</div>'
      + '</div>'
      + '</div>';

    // 每日一句点击翻译
    var sentence = view.querySelector('.daily-sentence');
    sentence.addEventListener('click', function () {
      if (sentence.dataset.translated) {
        sentence.textContent = '"Rain on the roof is the sky\'s lullaby."';
        delete sentence.dataset.translated;
      } else {
        sentence.textContent = '「屋顶上的雨声，是天空的摇篮曲。」';
        sentence.dataset.translated = '1';
      }
    });
  }

  /* ---------- 占位页（其他菜单） ---------- */
  function renderPlaceholder(title) {
    var view = document.getElementById('dashboard-view');
    view.innerHTML =
      '<div class="qx-card" style="margin-top:8px">'
      + '<div class="card-head"><span class="card-title">' + escapeHtml(title) + '</span></div>'
      + '<div class="card-body"><div class="table-empty" style="min-height:300px;display:flex;align-items:center;justify-content:center">该页面为 UI 特效复刻演示，功能未接入后端</div></div>'
      + '</div>';
  }

  /* ---------- 工具 ---------- */
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---------- 顶栏交互 ---------- */
  function bindHeader() {
    var user = (function () {
      try { return sessionStorage.getItem('qx-clone-user') || '小智'; } catch (e) { return '小智'; }
    })();
    document.getElementById('user-name').textContent = user;
    document.getElementById('user-avatar').textContent = user.charAt(0);

    document.getElementById('btn-reload').addEventListener('click', function () {
      renderDashboard();
    });

    document.getElementById('btn-fullscreen').addEventListener('click', function () {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    });

    document.getElementById('btn-locale').addEventListener('click', function () {
      var t = window.QXTheme.toggle();
      this.title = t === 'dark' ? '切换浅色' : '切换深色';
    });

    document.getElementById('user-dropdown').addEventListener('click', function () {
      location.href = 'login.html';
    });
  }

  /* ---------- 启动 ---------- */
  bindHeader();
  renderMenu();
  renderDashboard();
})();
