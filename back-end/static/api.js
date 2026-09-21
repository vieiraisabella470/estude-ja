/* Integração do frontend existente com a API do EstudaJá. */
(() => {
  'use strict';

  let account = null;
  let csrf = null;

  async function request(path, data) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    const options = { credentials: 'same-origin', cache: 'no-store', headers: {}, signal: controller.signal };
    if (data !== undefined) {
      options.method = 'POST';
      options.headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf || '' };
      options.body = JSON.stringify(data);
    }
    try {
      const response = await fetch('/api/' + path, options);
      if (!response.headers.get('Content-Type')?.includes('application/json')) {
        throw new Error('Abra o site pelo servidor Python em http://127.0.0.1:8000/.');
      }
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'Não foi possível concluir esta ação.');
      return body;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('O servidor demorou para responder. Confira o terminal do Python e tente novamente.');
      if (error instanceof TypeError) throw new Error('Sem conexão com o servidor. Inicie python app.py e abra http://127.0.0.1:8000/.');
      throw error;
    } finally { clearTimeout(timer); }
  }

  async function finishLogin() {
    const signedIn = await loadAccount();
    if (!signedIn || !csrf) throw new Error('A sessão não foi confirmada. Permita cookies neste site e tente entrar novamente.');
    window.location.replace('/acesso.html');
  }

  function message(text, type = 'error') {
    const status = document.getElementById('status');
    if (!status) return window.alert(text);
    status.className = 'status show ' + type;
    status.textContent = text;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  }

  async function loadAccount() {
    const state = await request('me');
    account = state.user;
    csrf = state.csrf;
    document.querySelectorAll('.botao-login').forEach(button => {
      if (!account) return;
      button.textContent = '👤 ' + account.name + ' · Sair';
      button.href = '#sair';
      button.addEventListener('click', async event => {
        event.preventDefault();
        try {
          await request('logout', {});
          window.location.href = '/login.html';
        } catch (error) { window.alert(error.message); }
      });
    });
    return account;
  }

  function registrationDialog() {
    const dialog = document.createElement('dialog');
    dialog.className = 'register-dialog';
    dialog.innerHTML = `<form method="dialog" class="register-box">
      <button type="button" class="register-close" aria-label="Fechar">×</button>
      <h2>Crie sua conta</h2>
      <p>Comece sua jornada no Estuda Já.</p>
      <label>Nome<input name="name" required minlength="2" maxlength="80" autocomplete="name"></label>
      <label>E-mail<input name="email" type="email" required autocomplete="email"></label>
      <label>Senha<input name="password" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label>
      <label>Confirme a senha<input name="confirmation" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label>
      <p class="register-status" role="alert"></p>
      <button class="register-submit" type="submit">Criar conta</button>
    </form>`;
    document.body.append(dialog);
    dialog.showModal();
    dialog.querySelector('.register-close').onclick = () => dialog.close();
    const form = dialog.querySelector('form');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form));
      const status = dialog.querySelector('.register-status');
      if (data.password !== data.confirmation) { status.textContent = 'As senhas precisam ser iguais.'; return; }
      const button = dialog.querySelector('.register-submit');
      button.disabled = true;
      try {
        await request('register', data);
        await finishLogin();
      } catch (error) {
        status.textContent = error.message;
        button.disabled = false;
      }
    });
    dialog.addEventListener('close', () => dialog.remove());
  }

  function setupLogin() {
    const form = document.getElementById('loginForm');
    if (!form) return;
    const button = document.getElementById('submitBtn');
    button.disabled = false;
    button.textContent = 'Entrar';
    const passwordInput = document.getElementById('password');
    const toggle = document.getElementById('toggleVis');
    toggle.onclick = () => {
      const visible = passwordInput.type === 'password';
      passwordInput.type = visible ? 'text' : 'password';
      toggle.textContent = visible ? 'ocultar' : 'mostrar';
      toggle.setAttribute('aria-label', visible ? 'Ocultar senha' : 'Mostrar senha');
    };
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (button.disabled) return;
      document.getElementById('emailMsg').textContent = '';
      document.getElementById('passwordMsg').textContent = '';
      document.getElementById('status').className = 'status';
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      if (!email || !password) { message('Informe e-mail e senha.'); return; }
      if (!document.getElementById('email').checkValidity()) { message('Informe um e-mail válido.'); return; }
      button.disabled = true;
      button.textContent = 'Entrando…';
      try {
        await request('login', { email, password });
        await finishLogin();
      } catch (error) {
        message(error.message);
        button.disabled = false;
        button.textContent = 'Entrar';
      }
    });
    document.getElementById('signupLink').addEventListener('click', event => {
      event.preventDefault();
      registrationDialog();
    });
    document.getElementById('forgotLink').addEventListener('click', event => {
      event.preventDefault();
      message('Peça ao responsável pelo Estuda Já para redefinir sua senha.');
    });
  }

  function popup(title, innerHtml) {
    const dialog = document.createElement('dialog');
    dialog.className = 'content-dialog';
    dialog.innerHTML = `<button class="register-close" aria-label="Fechar">×</button><h2>${escapeHtml(title)}</h2>${innerHtml}`;
    document.body.append(dialog);
    dialog.querySelector('button').onclick = () => dialog.close();
    dialog.addEventListener('close', () => dialog.remove());
    dialog.showModal();
    return dialog;
  }

  function renderVideos(items) {
    const target = document.querySelector('.video-grid');
    if (!target || !items.length) return;
    target.innerHTML = items.map(item => `<article class="video-card" data-subject="${escapeHtml(item.subject)}">
      <button class="video-thumb content-open" data-id="${item.id}" aria-label="Abrir ${escapeHtml(item.title)}">▶️<span class="duracao">${escapeHtml(item.duration || 'Aula')}</span></button>
      <div class="video-info"><h3>${escapeHtml(item.title)}</h3><p class="professor">${escapeHtml(item.teacher || item.subject)}</p><p class="tempo">🕒 ${escapeHtml(item.duration || 'Disponível')}</p></div></article>`).join('');
  }

  function renderActivities(items, quiz) {
    const target = document.querySelector(quiz ? '#gradeQuizzes' : '.lista-itens');
    if (!target || !items.length) return;
    if (quiz) {
      target.innerHTML = items.map(item => `<article class="quiz-card" data-assunto="${escapeHtml(item.subject.toLowerCase())}">
        <div class="quiz-top"><div class="quiz-icone">❓</div><span class="selo facil">Disponível</span></div>
        <p class="assunto">${escapeHtml(item.subject)}</p><h3>${escapeHtml(item.title)}</h3>
        <div class="quiz-meta"><span>📝 ${item.questions.length} perguntas</span></div><button class="botao content-open" data-id="${item.id}">Começar quiz</button></article>`).join('');
    } else {
      target.innerHTML = items.map(item => `<article class="item-lista"><div class="item-icone">📋</div><div class="item-info">
        <h3>${escapeHtml(item.title)}</h3><p class="professor">${escapeHtml(item.teacher || item.subject)}</p>
        <div class="meta"><span>📝 ${item.questions.length} questões</span><span>${escapeHtml(item.subject)}</span></div></div>
        <button class="botao content-open" data-id="${item.id}">Resolver</button></article>`).join('');
    }
  }

  function setupContent(content) {
    const pathname = window.location.pathname;
    if (pathname.endsWith('video-aulas.html')) renderVideos(content.filter(item => item.kind === 'video'));
    if (pathname.endsWith('atividades.html')) renderActivities(content.filter(item => item.kind === 'activity'), false);
    if (pathname.endsWith('quizzes.html')) renderActivities(content.filter(item => item.kind === 'quiz'), true);
    document.addEventListener('click', event => {
      const trigger = event.target.closest('.content-open');
      if (!trigger) return;
      const item = content.find(entry => entry.id === Number(trigger.dataset.id));
      if (!item) return;
      if (item.kind === 'video') {
        const link = item.url ? `<p><a class="botao" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Abrir aula</a></p>` : '<p>O vídeo será adicionado pelo administrador.</p>';
        popup(item.title, `<p>${escapeHtml(item.description)}</p>${link}`);
        return;
      }
      const options = item.questions.map((question, index) => `<fieldset><legend>${index + 1}. ${escapeHtml(question.prompt)}</legend>${question.options.map((option, answer) => `<label><input required type="radio" name="q${index}" value="${answer}"> ${escapeHtml(option)}</label>`).join('')}</fieldset>`).join('');
      const dialog = popup(item.title, `<p>${escapeHtml(item.description)}</p><form class="answer-form">${options}<p class="register-status"></p><button class="register-submit">Enviar respostas</button></form>`);
      dialog.querySelector('.answer-form').addEventListener('submit', async submit => {
        submit.preventDefault();
        const answers = item.questions.map((_, index) => Number(new FormData(submit.currentTarget).get('q' + index)));
        const button = dialog.querySelector('.register-submit');
        button.disabled = true;
        try {
          const result = await request('answer', { id: item.id, answers });
          dialog.querySelector('.register-status').textContent = `Atividade concluída: ${result.score}% de aproveitamento.`;
        } catch (error) { dialog.querySelector('.register-status').textContent = error.message; button.disabled = false; }
      });
    });
  }

  function addStyles() {
    const style = document.createElement('style');
    style.textContent = `.register-dialog,.content-dialog{border:0;border-radius:16px;max-width:560px;width:calc(100% - 30px);padding:28px;box-shadow:0 25px 70px #1e123866}.register-dialog::backdrop,.content-dialog::backdrop{background:#29135399}.register-box{display:grid;gap:12px}.register-box h2,.content-dialog h2{color:#392075;margin:0}.register-box p{margin:0;color:#666}.register-box label{display:grid;gap:5px;font-weight:bold;color:#392075}.register-box input{border:1px solid #ddd;border-radius:8px;padding:10px;font:inherit}.register-close{position:absolute;right:12px;top:8px;border:0;background:transparent;font-size:25px;cursor:pointer}.register-submit{border:0;border-radius:9px;background:#5720b7;color:#fff;padding:11px;font-weight:bold;cursor:pointer}.register-status{color:#b0223d;min-height:20px}.content-dialog fieldset{border:1px solid #ddd;border-radius:8px;margin:14px 0;padding:12px}.content-dialog label{display:block;padding:6px 0;cursor:pointer}.content-dialog .video-thumb{border:0;width:100%;cursor:pointer}`;
    document.head.append(style);
  }

  async function start() {
    addStyles();
    setupLogin();
    try {
      const signedIn = await loadAccount();
      const confirmation = document.getElementById('auth-confirmation');
      if (confirmation) {
        if (!signedIn) { window.location.replace('/login.html'); return; }
        document.getElementById('account-name').textContent = signedIn.name;
        document.getElementById('account-email').textContent = signedIn.email;
        document.getElementById('auth-loading').hidden = true;
        confirmation.hidden = false;
        return;
      }
      if (signedIn && !window.location.pathname.endsWith('login.html')) setupContent(await request('content'));
    } catch (error) {
      if (document.getElementById('auth-loading')) document.getElementById('auth-loading').textContent = error.message;
      else message(error.message);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
