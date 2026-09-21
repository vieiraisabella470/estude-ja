# Backend do Estuda Já

Este backend Python entrega uma cópia das telas existentes em `front-isa e costa` e conecta o login, cadastro, videoaulas, atividades e quizzes à API e ao banco SQLite. A pasta original do frontend não é modificada.

## Executar

Na pasta `back-end`, use Python 3.10 ou superior:

```powershell
python app.py
```

Abra `http://127.0.0.1:8000`. Não use Go Live: o servidor Python serve o frontend e a API na mesma porta, mantendo o login funcionando.

Use **Inscreva-se** para criar uma conta ou entre com a conta já cadastrada.
O cadastro exige senha de 10 a 128 caracteres. Depois do login, a tela **Login realizado com sucesso!** mostra o usuário confirmado pela sessão no banco e oferece **Continuar para o site**.

Se o servidor já estava aberto antes de atualizar o código, pare com `Ctrl+C` e execute `python app.py` novamente. O terminal mostra o caminho exato do banco em uso.

Para criar um administrador, use `python app.py --create-admin`. Para redefinir uma senha esquecida, use `python app.py --reset-password`. Não é necessário recriar a conta toda vez que iniciar o site.

### Banco e login

O banco SQLite é criado automaticamente em `back-end/data/estudaja.db`. Contas e sessões persistem após reiniciar o servidor. A senha é armazenada como derivação PBKDF2 com salt; o navegador recebe um cookie HttpOnly e confirma a sessão em `/api/me` antes de mostrar sucesso. O login não usa dados simulados nem armazenamento local do navegador.

Ao copiar o projeto para outra máquina, as contas não são copiadas pelo Git: o banco fica ignorado. Nesse computador, cadastre uma conta nova. Não apague o banco para corrigir problemas de acesso.

## O que funciona

- Cadastro, login e logout com sessão.
- Videoaulas cadastradas no banco aparecem na tela de videoaulas.
- Atividades e quizzes carregam do banco, são corrigidos no servidor e salvam a pontuação.
- As demais páginas já existentes continuam disponíveis conforme foram criadas.

Os dados locais ficam em `data/estudaja.db` e não são enviados ao Git.

## Testes

```powershell
python -m unittest discover -s tests -v
```
