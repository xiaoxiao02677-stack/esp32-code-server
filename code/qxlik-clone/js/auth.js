/* auth.js —— 认证与 API 通道（全站加载，须在 static.js / demo-data.js 之前）
 *
 * 职责：
 *   1. token/user 会话存取（localStorage）
 *   2. QXAuth.api() 统一请求（自动带 Bearer；401 清会话跳登录）
 *   3. 页面守卫：/pages/ 业务页无 token → 跳登录
 *   4. 顶栏昵称 / 首页问候语联动
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'qx-token';
  var USER_KEY = 'qx-user';

  function loginHref() {
    return location.pathname.indexOf('/pages/') >= 0 ? '../login.html' : 'login.html';
  }

  var QXAuth = {
    getToken: function () {
      try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
    },
    getUser: function () {
      try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (e) { return null; }
    },
    save: function (token, user) {
      try {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
      } catch (e) {}
    },
    clear: function () {
      try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch (e) {}
    },

    /* 统一请求：带 token；HTTP 401 → 清会话跳登录 */
    api: function (path, opts) {
      opts = opts || {};
      opts.headers = Object.assign(
        { 'Authorization': 'Bearer ' + this.getToken() },
        opts.headers || {}
      );
      var self = this;
      return fetch(path, opts).then(function (r) {
        if (r.status === 401) {
          self.clear();
          if (location.pathname.indexOf('login.html') < 0) {
            location.href = loginHref();
          }
          return Promise.reject({ status: 401, message: '未登录或会话已过期' });
        }
        return r.json();
      });
    },

    /* 退出登录：调 API 注销 token，再清本地跳登录 */
    logout: function () {
      var self = this;
      return this.api('/api/auth/logout', { method: 'POST' })
        .catch(function () {})
        .then(function () {
          self.clear();
          location.href = loginHref();
        });
    },

    /* 页面守卫：/pages/ 业务页（错误页除外）无 token 跳登录 */
    guard: function () {
      var p = location.pathname;
      if (p.indexOf('/pages/') < 0) return;
      if (p.indexOf('403.html') >= 0 || p.indexOf('404.html') >= 0) return;
      if (!this.getToken()) {
        location.replace('../login.html');
      }
    },

    /* 顶栏昵称 + 首页问候语 */
    applyUser: function () {
      var u = this.getUser();
      if (!u) return;
      var el = document.querySelector('.user-name');
      if (el && u.nickname) el.textContent = u.nickname;
      var h2 = document.querySelector('.user-greeting h2');
      if (h2 && u.nickname) {
        h2.textContent = h2.textContent.replace('小智', u.nickname);
      }
    }
  };

  window.QXAuth = QXAuth;

  /* ---------- setting-account 页：个人资料表单 ---------- */
  function setupAccountPage() {
    if (location.pathname.indexOf('setting-account.html') < 0) return;
    var form = document.querySelector('.bento-content-panel form');
    if (!form) return;

    function fieldVal(id) {
      var el = document.getElementById(id);
      return el ? el.value.trim() : '';
    }

    // SSO 模式：登录走主站账号，本地密码无意义 → 隐藏密码/确认密码两项
    ['form_item_password', 'form_item_confirmPassword'].forEach(function (fid) {
      var label = form.querySelector('label[for="' + fid + '"]');
      var item = label ? label.closest('.ant-form-item') : null;
      if (item) item.style.display = 'none';
    });

    // 表单回填（GET /api/user/profile）
    QXAuth.api('/api/user/profile')
      .then(function (j) {
        if (j && j.code === 200 && j.data) {
          var map = { form_item_name: 'nickname', form_item_tel: 'tel', form_item_email: 'email' };
          Object.keys(map).forEach(function (fid) {
            var el = document.getElementById(fid);
            if (el && j.data[map[fid]]) el.value = j.data[map[fid]];
          });
        }
      })
      .catch(function () {});

    // 保存（POST /api/user/profile，SSO 模式不再发送密码字段）
    var btn = null;
    form.querySelectorAll('button').forEach(function (b) {
      if (b.textContent.replace(/\s/g, '') === '保存') btn = b;
    });
    if (!btn) return;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var body = {
        nickname: fieldVal('form_item_name'),
        tel: fieldVal('form_item_tel'),
        email: fieldVal('form_item_email')
      };
      btn.disabled = true;
      QXAuth.api('/api/user/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
        .then(function (j) {
          btn.disabled = false;
          if (j && j.code === 200) {
            var u = QXAuth.getUser() || {};
            u.nickname = body.nickname || u.nickname;
            QXAuth.save(QXAuth.getToken(), u);
            QXAuth.applyUser();
            alert(j.message || '保存成功');
          } else {
            alert((j && j.message) || '保存失败');
          }
        })
        .catch(function () {
          btn.disabled = false;
          alert('网络异常，请稍后重试');
        });
    });
  }

  QXAuth.guard();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { QXAuth.applyUser(); setupAccountPage(); });
  } else {
    QXAuth.applyUser();
    setupAccountPage();
  }
})();
