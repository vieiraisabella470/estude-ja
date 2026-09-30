(() => {
    'use strict';

    const ACCOUNT_KEY = 'estudaJa.account';
    const SESSION_KEY = 'estudaJa.session';

    function read(key) {
        try {
            const value = JSON.parse(localStorage.getItem(key));
            return value && typeof value === 'object' ? value : null;
        } catch {
            return null;
        }
    }

    function account() {
        const value = read(ACCOUNT_KEY);
        return value && typeof value.name === 'string' && typeof value.email === 'string' ? value : null;
    }

    function session() {
        const value = read(SESSION_KEY);
        return value && typeof value.name === 'string' && typeof value.email === 'string' ? value : null;
    }

    function firstName(name) {
        return name.trim().split(/\s+/)[0];
    }

    function saveAccount(data) {
        const saved = { name: data.name.trim(), email: data.email.trim().toLowerCase() };
        localStorage.setItem(ACCOUNT_KEY, JSON.stringify(saved));
        return saved;
    }

    function startSession(data = account()) {
        if (!data) return null;
        localStorage.setItem(SESSION_KEY, JSON.stringify(data));
        updateNavigation();
        return data;
    }

    function endSession() {
        localStorage.removeItem(SESSION_KEY);
        window.location.href = 'sobre-nos.html';
    }

    function updateHeroActions() {
        const actions = document.querySelector('.hero-botoes');
        if (!actions) return;

        const continueButton = actions.querySelector('a[href="cadastro.html"]');
        const loggedMessage = actions.querySelector('a[href="login.html"]');
        if (continueButton) {
            continueButton.href = 'materias.html';
            continueButton.textContent = 'Retorne aos estudos →';
        }
        if (loggedMessage) {
            loggedMessage.removeAttribute('href');
            loggedMessage.classList.add('botao-logado');
            loggedMessage.textContent = '✓ Você já está logado';
            loggedMessage.setAttribute('aria-disabled', 'true');
        }
    }

    function updateNavigation() {
        const user = session();
        if (!user) return;

        document.querySelectorAll('.botao-login').forEach(button => {
            button.textContent = `👤 Olá, ${firstName(user.name)}`;
            button.href = 'materias.html';
            button.title = `Acessar a área de ${user.name}`;
            button.setAttribute('aria-label', `Acessar a área de ${user.name}`);

            const actions = button.closest('.acoes-publicas') || button.parentElement;
            if (!actions) return;
            const signup = actions.querySelector('a[href="cadastro.html"]');
            if (signup && actions.classList.contains('acoes-publicas')) signup.hidden = true;
            if (actions.querySelector('.botao-sair')) return;

            const logout = document.createElement('button');
            logout.type = 'button';
            logout.className = 'botao-sair';
            logout.textContent = 'Sair';
            logout.setAttribute('aria-label', 'Sair da conta');
            logout.addEventListener('click', endSession);
            button.insertAdjacentElement('afterend', logout);
        });

        updateHeroActions();
    }

    function animatePageChange(event) {
        const link = event.target.closest('a[href$=".html"]');
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target) return;
        const destination = new URL(link.href, window.location.href);
        if (destination.origin !== window.location.origin || destination.pathname === window.location.pathname) return;
        event.preventDefault();
        document.body.classList.add('pagina-saindo');
        window.setTimeout(() => { window.location.href = destination.href; }, 180);
    }

    window.EstudaJaSession = Object.freeze({ account, session, saveAccount, startSession, endSession });
    document.addEventListener('DOMContentLoaded', updateNavigation, { once: true });
    document.addEventListener('click', animatePageChange);
})();
