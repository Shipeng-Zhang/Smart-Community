const AUTH_TOKEN_KEY = 'community_auth_token';

function $(id) {
  return document.getElementById(id);
}

function setMessage(message, type = '') {
  const el = $('authMessage');
  if (!el) return;
  el.className = `auth-message ${type}`.trim();
  el.textContent = message || '';
}

function getQuery() {
  return new URLSearchParams(location.search);
}

function getRedirectTarget() {
  const redirect = getQuery().get('redirect') || '/index.html';
  return redirect.startsWith('/') ? redirect : '/index.html';
}

function getToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || '';
}

function saveToken(token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

async function requestJson(url, payload, token = '') {
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, {
    method: 'POST',
    headers,
    cache: 'no-store',
    body: JSON.stringify(payload ?? {}),
  });
  return response.json();
}

async function requestMe(token) {
  const response = await fetch('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error('invalid session');
  }
  return response.json();
}

function hydrateQueryState() {
  const query = getQuery();
  const message = query.get('message');
  const account = query.get('account');
  if (message === 'registered') {
    setMessage('注册成功，请登录系统。', 'success');
  }
  if (account && $('loginAccount')) {
    $('loginAccount').value = account;
  }
}

async function redirectIfLoggedIn() {
  const token = getToken();
  if (!token) return;
  try {
    const payload = await requestMe(token);
    if (payload.ok && payload.user) {
      location.replace(getRedirectTarget());
      return;
    }
  } catch (error) {
    clearToken();
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector('button[type="submit"]');
  const account = $('loginAccount').value.trim();
  const password = $('loginPassword').value;

  if (!account || !password) {
    setMessage('请输入账号和密码。', 'error');
    return;
  }

  button.disabled = true;
  setMessage('正在登录，请稍候...', 'success');
  try {
    const payload = await requestJson('/api/auth/login', { account, password });
    if (!payload.ok || !payload.token) {
      setMessage(payload.message || '登录失败，请检查账号或密码。', 'error');
      return;
    }
    saveToken(payload.token);
    setMessage('登录成功，正在进入系统...', 'success');
    setTimeout(() => {
      location.replace(getRedirectTarget());
    }, 300);
  } catch (error) {
    setMessage('登录请求失败，请稍后重试。', 'error');
  } finally {
    button.disabled = false;
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector('button[type="submit"]');
  const username = $('registerUsername').value.trim();
  const email = $('registerEmail').value.trim();
  const password = $('registerPassword').value;
  const confirmPassword = $('registerConfirmPassword').value;

  if (!username || !email || !password || !confirmPassword) {
    setMessage('请完整填写注册信息。', 'error');
    return;
  }
  if (password !== confirmPassword) {
    setMessage('两次输入的密码不一致。', 'error');
    return;
  }

  button.disabled = true;
  setMessage('正在创建账号，请稍候...', 'success');
  try {
    const payload = await requestJson('/api/auth/register', { username, email, password });
    if (!payload.ok) {
      setMessage(payload.message || '注册失败，请检查输入内容。', 'error');
      return;
    }
    setMessage('注册成功，正在跳转到登录页...', 'success');
    setTimeout(() => {
      location.href = `/login.html?message=registered&account=${encodeURIComponent(email)}`;
    }, 500);
  } catch (error) {
    setMessage('注册请求失败，请稍后重试。', 'error');
  } finally {
    button.disabled = false;
  }
}

async function bootstrapAuthPage() {
  hydrateQueryState();
  await redirectIfLoggedIn();

  const page = document.body.dataset.page;
  if (page === 'login' && $('loginForm')) {
    $('loginForm').addEventListener('submit', handleLogin);
  }
  if (page === 'register' && $('registerForm')) {
    $('registerForm').addEventListener('submit', handleRegister);
  }
}

bootstrapAuthPage().catch(() => {
  clearToken();
});
