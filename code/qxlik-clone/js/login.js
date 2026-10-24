/* 登录页交互：密码显隐 + 真实登录（POST /api/auth/login） */
(function () {
  'use strict';

  // 已登录直接进首页
  if (window.QXAuth && QXAuth.getToken()) {
    location.replace('pages/index.html');
    return;
  }

  // 密码显隐切换
  var toggleBtn = document.getElementById('toggle-pwd');
  var pwdInput = document.getElementById('password');
  toggleBtn.addEventListener('click', function () {
    var show = pwdInput.type === 'password';
    pwdInput.type = show ? 'text' : 'password';
    toggleBtn.style.color = show ? 'var(--ant-color-text-secondary)' : '';
  });

  function shake(el) {
    el.style.borderColor = 'var(--ant-color-error)';
    el.style.animation = 'shake .5s ease-in-out';
    setTimeout(function () { el.style.animation = ''; }, 600);
    setTimeout(function () { el.style.borderColor = ''; }, 1800);
  }

  // 提示条（复用源站 error-icon 动画节奏）
  function showMsg(text, isError) {
    var bar = document.getElementById('login-msg');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'login-msg';
      bar.style.cssText = 'margin:0 0 12px;padding:8px 12px;border-radius:8px;font-size:13px;' +
        (isError
          ? 'background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);color:#EF4444;'
          : 'background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.35);color:#10B981;');
      var form = document.getElementById('login-form');
      form.insertBefore(bar, form.firstChild);
    }
    bar.textContent = text;
    bar.style.display = 'block';
  }

  // 提交 → 真实登录
  var form = document.getElementById('login-form');
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var u = document.getElementById('username').value.trim();
    var p = pwdInput.value;
    if (!u || !p) {
      shake(!u ? document.getElementById('username') : pwdInput);
      return;
    }
    var btn = form.querySelector('.submit-btn');
    btn.disabled = true;
    btn.textContent = '登录中...';

    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p })
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.code === 200 && j.data && j.data.token) {
          QXAuth.save(j.data.token, j.data.user);
          showMsg('登录成功，正在进入...', false);
          location.href = 'pages/index.html';
        } else {
          showMsg(j.message || '用户名或密码错误', true);
          shake(pwdInput);
          btn.disabled = false;
          btn.textContent = '登录';
        }
      })
      .catch(function () {
        showMsg('网络异常，请稍后重试', true);
        btn.disabled = false;
        btn.textContent = '登录';
      });
  });
})();
