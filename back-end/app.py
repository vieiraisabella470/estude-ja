import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('ESTUDAJA_DB', str(ROOT / 'data' / 'estudaja.db')))
SECURE = os.environ.get('ESTUDAJA_HTTPS') == '1'
LOCK = threading.Lock()
ATTEMPTS = {}

@contextmanager
def database():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return salt + ':' + digest

def password_ok(password, encoded):
    return hmac.compare_digest(password_hash(password, encoded.split(':')[0]), encoded)

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
          password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS content (
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
          subject TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          url TEXT NOT NULL DEFAULT '', image TEXT NOT NULL DEFAULT '',
          teacher TEXT NOT NULL DEFAULT '', duration TEXT NOT NULL DEFAULT '',
          questions TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS progress (
          user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          content_id INTEGER REFERENCES content(id) ON DELETE CASCADE,
          score INTEGER NOT NULL DEFAULT 100, completed TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,content_id));
        CREATE TABLE IF NOT EXISTS plans (
          id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL, day TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        if not db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            rows = [
                ('video','Introdução à álgebra','Matemática','Aprenda a encontrar o valor de uma incógnita.','','','Prof. João Silva','12:30',[]),
                ('video','Civilizações antigas','História','Uma viagem pelas primeiras civilizações.','','','Prof.ª Ana Moreira','15:45',[]),
                ('video','Gramática básica','Português','Construa uma base para escrever melhor.','','','Prof.ª Carla Souza','10:50',[]),
                ('material','Seu primeiro guia de álgebra','Matemática','Em uma equação, os dois lados precisam permanecer iguais. Em x + 3 = 7, subtraia 3 dos dois lados: x = 4.','','','','5 min',[]),
                ('material','Como organizar seus estudos','Geral','Escolha uma matéria, estude por 25 minutos e faça uma pausa de 5 minutos. Termine escrevendo o que aprendeu.','','','','3 min',[]),
                ('activity','Lista de exercícios de álgebra I','Matemática','Pratique equações e operações básicas.','','','Prof. João Silva','',[
                  {'prompt':'Qual é o valor de x em x + 3 = 7?','options':['3','4','7','10'],'answer':1},
                  {'prompt':'Quanto é 3 × (2 + 4)?','options':['10','12','18','24'],'answer':2}]),
                ('activity','Civilizações antigas','História','Relembre o que você aprendeu.','','','Prof.ª Ana Moreira','',[
                  {'prompt':'Qual civilização construiu as pirâmides de Gizé?','options':['Egípcia','Romana','Inca'],'answer':0}]),
                ('quiz','Desafio de português','Português','Teste seus conhecimentos.','','','','',[
                  {'prompt':'Qual destas palavras é um verbo?','options':['Casa','Estudar','Bonito'],'answer':1}]),
            ]
            for row in rows:
                db.execute('INSERT INTO content(kind,title,subject,description,url,image,teacher,duration,questions) VALUES(?,?,?,?,?,?,?,?,?)', (*row[:-1],json.dumps(row[-1],ensure_ascii=False)))
            db.execute("INSERT INTO settings VALUES('seeded','1')")

def valid_url(value):
    if not value:
        return True
    try:
        p = urlsplit(value)
        return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False

def validate_content(data):
    result = {}
    for key, limit in [('kind',20),('title',160),('subject',60),('description',10000),('url',2000),('image',2000),('teacher',100),('duration',30)]:
        value = data.get(key, '')
        if not isinstance(value,str) or len(value)>limit:
            raise ValueError('Campo inválido: ' + key)
        result[key] = value.strip()
    if result['kind'] not in ['video','material','activity','quiz','site'] or not result['title'] or not result['subject']:
        raise ValueError('Informe tipo, título e matéria.')
    if not valid_url(result['url']) or not valid_url(result['image']):
        raise ValueError('Use links completos começando com https://.')
    questions = data.get('questions',[])
    if not isinstance(questions,list) or len(questions)>50:
        raise ValueError('Use uma lista com até 50 questões.')
    for q in questions:
        if not isinstance(q,dict) or not isinstance(q.get('prompt'),str) or not 1 <= len(q['prompt']) <= 1000 or not isinstance(q.get('options'),list) or not 2 <= len(q['options']) <= 6 or not all(isinstance(x,str) and 1 <= len(x) <= 500 for x in q['options']) or type(q.get('answer')) is not int or not 0 <= q['answer'] < len(q['options']):
            raise ValueError('Cada questão precisa de enunciado, 2 a 6 alternativas e índice da resposta correta.')
    if result['kind'] in ['activity','quiz'] and not questions:
        raise ValueError('Adicione pelo menos uma questão.')
    result['questions'] = json.dumps(questions,ensure_ascii=False)
    return result

class Handler(BaseHTTPRequestHandler):
    server_version = 'EstudaJa'

    def log_message(self, fmt, *args):
        # Evita registrar dados enviados, tokens ou senhas.
        pass

    def respond(self,status,data=None,raw=None,mime='application/json; charset=utf-8',cookie=None):
        body = raw if raw is not None else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Cache-Control','no-store')
        # As páginas do frontend existente usam estilos e pequenos scripts inline.
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' https: data:; frame-src https://www.youtube-nocookie.com https://player.vimeo.com; media-src 'self' https:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        c = cookies.SimpleCookie()
        try:
            c.load(self.headers.get('Cookie',''))
        except cookies.CookieError:
            return None
        token = c.get('estudaja_session')
        if not token:
            return None
        with database() as db:
            return db.execute('SELECT sessions.*, users.name,users.email,users.admin FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?',(hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            self.respond(500,{'error':'Não foi possível carregar os dados.'})

    def get(self):
        path = urlsplit(self.path).path
        # O backend entrega o frontend do grupo na mesma origem; assim sessões e
        # chamadas à API não dependem do Go Live nem de CORS.
        if path == '/':
            path = '/login.html'
        static_root = (ROOT / 'static').resolve()
        candidate = (static_root / unquote(path).lstrip('/')).resolve()
        if candidate.is_file() and static_root in candidate.parents:
            mimes = {
                '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8',
                '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml',
                '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.webp': 'image/webp', '.ico': 'image/x-icon',
            }
            raw = candidate.read_bytes()
            mime = mimes.get(candidate.suffix.lower(), 'application/octet-stream')
            if candidate.suffix.lower() == '.html':
                # api.js integra as telas existentes sem reescrever o trabalho visual.
                if b'src="api.js"' not in raw and b'src="/api.js"' not in raw:
                    raw = raw.replace(b'</body>', b'<script src="/api.js" defer></script></body>')
            return self.respond(200, raw=raw, mime=mime)
        session = self.session()
        if path == '/api/me':
            return self.respond(200,{'user':dict(id=session['user_id'],name=session['name'],email=session['email'],admin=bool(session['admin'])) if session else None,'csrf':session['csrf'] if session else None})
        if not session:
            return self.respond(401,{'error':'Entre na sua conta para continuar.'})
        with database() as db:
            if path == '/api/content':
                rows = [dict(x) for x in db.execute('SELECT * FROM content ORDER BY id')]
                for item in rows:
                    item['questions'] = json.loads(item['questions'])
                    if not session['admin']:
                        for q in item['questions']:
                            q.pop('answer',None)
                return self.respond(200,rows)
            if path == '/api/progress':
                return self.respond(200,[dict(x) for x in db.execute('SELECT content_id,score,completed FROM progress WHERE user_id=?',(session['user_id'],))])
            if path == '/api/plans':
                return self.respond(200,[dict(x) for x in db.execute('SELECT id,title,day,done FROM plans WHERE user_id=? ORDER BY day,id',(session['user_id'],))])
        self.respond(404,{'error':'Página não encontrada.'})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 100000:
                return self.respond(413,{'error':'Dados ausentes ou muito grandes.'})
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                return self.respond(415,{'error':'Envie JSON.'})
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.respond(403,{'error':'Origem não permitida.'})
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                return self.respond(403,{'error':'Origem não permitida.'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise ValueError('Formato inválido.')
            self.post(urlsplit(self.path).path,data)
        except (ValueError,TypeError,KeyError):
            self.respond(400,{'error':'Confira os dados informados.'})
        except sqlite3.IntegrityError:
            self.respond(409,{'error':'Não foi possível salvar. Verifique se o e-mail já está cadastrado.'})
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            self.respond(500,{'error':'Não foi possível concluir. Tente novamente.'})

    def post(self,path,data):
        if path in ['/api/login','/api/register']:
            address = self.client_address[0]
            now = time.time()
            with LOCK:
                for key in list(ATTEMPTS):
                    if not ATTEMPTS[key] or ATTEMPTS[key][-1] < now-900:
                        del ATTEMPTS[key]
                attempts = [x for x in ATTEMPTS.get(address,[]) if x>now-900]
                if len(attempts)>=20:
                    return self.respond(429,{'error':'Muitas tentativas. Aguarde 15 minutos.'})
                ATTEMPTS[address] = attempts+[now]
            email,password = data.get('email',''),data.get('password','')
            minimum = 10 if path == '/api/register' else 1
            if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or not minimum<=len(password)<=128:
                return self.respond(400,{'error':'Use um e-mail válido e senha de 10 a 128 caracteres.' if minimum == 10 else 'Informe seu e-mail e sua senha.'})
            email = email.strip().lower()
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
                return self.respond(400,{'error':'Informe um e-mail válido.'})
            with database() as db:
                if path.endswith('register'):
                    name = data.get('name','')
                    if not isinstance(name,str) or not 2<=len(name.strip())<=80:
                        return self.respond(400,{'error':'Informe seu nome (2 a 80 caracteres).'})
                    db.execute('INSERT INTO users(name,email,password) VALUES(?,?,?)',(name.strip(),email,password_hash(password)))
                user = db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                # Mesmo custo de derivação para contas inexistentes.
                encoded = user['password'] if user else '0'*32+':'+'0'*64
                if not password_ok(password,encoded) or not user:
                    return self.respond(401,{'error':'E-mail ou senha incorretos.'})
                token,csrf = secrets.token_urlsafe(32),secrets.token_urlsafe(32)
                db.execute('DELETE FROM sessions WHERE expires<?',(now,))
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,now+43200))
            # A transação acima já foi confirmada antes de informar sucesso.
            return self.respond(200,{'ok':True},cookie=f'estudaja_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200'+('; Secure' if SECURE else ''))
        session = self.session()
        if not session:
            return self.respond(401,{'error':'Entre na sua conta para continuar.'})
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
            return self.respond(403,{'error':'Sessão inválida. Atualize a página.'})
        with database() as db:
            if path == '/api/logout':
                db.execute('DELETE FROM sessions WHERE token=?',(session['token'],))
                return self.respond(200,{'ok':True},cookie='estudaja_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'+('; Secure' if SECURE else ''))
            if path.startswith('/api/admin/'):
                if not session['admin']:
                    return self.respond(403,{'error':'Acesso exclusivo do administrador.'})
                if path == '/api/admin/delete':
                    db.execute('DELETE FROM content WHERE id=?',(int(data['id']),))
                elif path == '/api/admin/save':
                    try:
                        item = validate_content(data)
                    except ValueError as exc:
                        return self.respond(400,{'error':str(exc)})
                    if data.get('id'):
                        db.execute('UPDATE content SET '+','.join(k+'=?' for k in item)+' WHERE id=?',(*item.values(),int(data['id'])))
                        # Uma atividade alterada precisa ser resolvida novamente.
                        db.execute('DELETE FROM progress WHERE content_id=?',(int(data['id']),))
                    else:
                        db.execute('INSERT INTO content('+','.join(item)+') VALUES('+','.join('?' for _ in item)+')',tuple(item.values()))
                else:
                    return self.respond(404,{'error':'Ação não encontrada.'})
                return self.respond(200,{'ok':True})
            if path in ['/api/complete','/api/answer']:
                item = db.execute('SELECT * FROM content WHERE id=?',(int(data['id']),)).fetchone()
                if not item:
                    return self.respond(404,{'error':'Conteúdo não encontrado.'})
                score = 100
                if item['kind'] in ['quiz','activity']:
                    if path != '/api/answer':
                        return self.respond(400,{'error':'Responda às questões primeiro.'})
                    questions = json.loads(item['questions'])
                    answers = data.get('answers')
                    if not isinstance(answers,list) or len(answers)!=len(questions) or any(type(a) is not int or a<0 or a>=len(q['options']) for a,q in zip(answers,questions)):
                        return self.respond(400,{'error':'Responda a todas as questões.'})
                    score = round(100*sum(a==q['answer'] for a,q in zip(answers,questions))/len(questions))
                elif path != '/api/complete':
                    return self.respond(400,{'error':'Este conteúdo não possui questões.'})
                db.execute('INSERT INTO progress(user_id,content_id,score) VALUES(?,?,?) ON CONFLICT(user_id,content_id) DO UPDATE SET score=excluded.score,completed=CURRENT_TIMESTAMP',(session['user_id'],item['id'],score))
                return self.respond(200,{'score':score})
            if path == '/api/plans/save':
                title,day = data.get('title',''),data.get('day','')
                import datetime
                datetime.date.fromisoformat(day)
                if not isinstance(title,str) or not 1<=len(title.strip())<=160:
                    raise ValueError()
                db.execute('INSERT INTO plans(user_id,title,day) VALUES(?,?,?)',(session['user_id'],title.strip(),day))
                return self.respond(200,{'ok':True})
            if path == '/api/plans/toggle':
                db.execute('UPDATE plans SET done=1-done WHERE id=? AND user_id=?',(int(data['id']),session['user_id']))
                return self.respond(200,{'ok':True})
            if path == '/api/plans/delete':
                db.execute('DELETE FROM plans WHERE id=? AND user_id=?',(int(data['id']),session['user_id']))
                return self.respond(200,{'ok':True})
        self.respond(404,{'error':'Ação não encontrada.'})

def main():
    parser = argparse.ArgumentParser(description='EstudaJá — plataforma de estudos')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--create-admin',action='store_true')
    parser.add_argument('--reset-password',action='store_true')
    args = parser.parse_args()
    initialize()
    if args.create_admin or args.reset_password:
        email = input('E-mail: ').strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            raise SystemExit('E-mail inválido.')
        password = getpass.getpass('Nova senha (10 a 128 caracteres): ')
        if not 10<=len(password)<=128 or password!=getpass.getpass('Confirme a senha: '):
            raise SystemExit('Senha inválida ou confirmação diferente.')
        with database() as db:
            user = db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
            if args.reset_password:
                if not user:
                    raise SystemExit('Conta não encontrada.')
                db.execute('UPDATE users SET password=? WHERE id=?',(password_hash(password),user['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            elif user:
                db.execute('UPDATE users SET admin=1,password=? WHERE id=?',(password_hash(password),user['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            else:
                db.execute('INSERT INTO users(name,email,password,admin) VALUES(?,?,?,1)',('Administrador',email,password_hash(password)))
        print('Conta atualizada com sucesso.')
        return
    server = ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'EstudaJá disponível em http://{args.host}:{args.port} — Ctrl+C para encerrar.',flush=True)
    print(f'Banco de dados: {DB.resolve()}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
