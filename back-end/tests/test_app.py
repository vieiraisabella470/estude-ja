"""Testes de integração HTTP com banco temporário e biblioteca padrão."""
import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        app.DB=Path(cls.temp.name)/'test.db'
        app.initialize()
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()
    def setUp(self):
        app.ATTEMPTS.clear()
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(self,path,data=None,csrf='',client=None):
        req=urllib.request.Request(self.base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        try:
            with (client or self.client).open(req) as response:
                return response.status,json.load(response)
        except urllib.error.HTTPError as e:
            return e.code,json.load(e)
    def account(self,name):
        code,_=self.request('register',{'name':name,'email':name+'@example.com','password':'test-password-123'})
        self.assertEqual(code,200)
        return self.request('me')[1]['csrf']
    def test_frontend_is_served_by_backend(self):
        with self.client.open(self.base + '/') as response:
            page = response.read().decode('utf-8')
            self.assertEqual(response.status, 200)
            self.assertIn('Bem-vindo de volta!', page)
            self.assertIn('src="api.js"', page)
            self.assertEqual(page.count('src="api.js"'), 1)
            self.assertNotIn('Login validado no front-end', page)
        with self.client.open(self.base + '/video-aulas.html') as response:
            self.assertIn('Vídeo Aulas', response.read().decode('utf-8'))
    def test_auth_permissions_and_csrf(self):
        self.assertEqual(self.request('content')[0],401)
        csrf=self.account('student')
        self.assertEqual(self.request('admin/delete',{'id':1},csrf)[0],403)
        self.assertEqual(self.request('complete',{'id':1})[0],403)
        self.assertEqual(self.request('logout',{},csrf)[0],200)
        self.assertEqual(self.request('content')[0],401)
        self.assertEqual(self.request('login',{'email':'student@example.com','password':'incorrect-123'})[0],401)
        self.assertEqual(self.request('login',{'email':'student@example.com','password':'test-password-123'})[0],200)
        with app.database() as db:
            self.assertNotIn('test-password',db.execute('SELECT password FROM users WHERE email=?',('student@example.com',)).fetchone()[0])
    def test_login_confirms_persisted_session(self):
        csrf = self.account('persistent')
        self.request('logout', {}, csrf)
        with app.database() as db:
            user_id = db.execute('SELECT id FROM users WHERE email=?', ('persistent@example.com',)).fetchone()[0]
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE user_id=?', (user_id,)).fetchone()[0], 0)
        self.assertEqual(self.request('login', {'email':'persistent@example.com','password':'wrong'})[0], 401)
        self.assertIsNone(self.request('me')[1]['user'])
        self.assertEqual(self.request('login', {'email':' PERSISTENT@EXAMPLE.COM ','password':'test-password-123'})[0], 200)
        state = self.request('me')[1]
        self.assertEqual(state['user']['id'], user_id)
        self.assertTrue(state['csrf'])
        with app.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE user_id=?', (user_id,)).fetchone()[0], 1)
        app.initialize()
        self.assertEqual(self.request('me')[1]['user']['id'], user_id)
        self.assertEqual(self.request('logout', {}, state['csrf'])[0], 200)
        self.assertIsNone(self.request('me')[1]['user'])
    def test_grading_and_isolation(self):
        csrf=self.account('learner')
        rows=self.request('content')[1]
        activity=next(x for x in rows if x['kind']=='activity')
        self.assertNotIn('answer',activity['questions'][0])
        self.assertEqual(self.request('complete',{'id':activity['id']},csrf)[0],400)
        self.assertEqual(self.request('answer',{'id':activity['id'],'answers':[1]},csrf)[0],400)
        result=self.request('answer',{'id':activity['id'],'answers':[1,2]},csrf)
        self.assertEqual(result,(200,{'score':100}))
        self.assertEqual(len(self.request('progress')[1]),1)
        self.request('plans/save',{'title':'Revisão','day':'2026-09-22'},csrf)
        plan=self.request('plans')[1][0]
        self.request('logout',{},csrf)
        other=self.account('other')
        self.assertEqual(self.request('progress')[1],[])
        self.request('plans/toggle',{'id':plan['id']},other)
        with app.database() as db:
            self.assertEqual(db.execute('SELECT done FROM plans WHERE id=?',(plan['id'],)).fetchone()[0],0)
    def test_admin_crud_validation(self):
        csrf=self.account('owner')
        with app.database() as db:
            db.execute("UPDATE users SET admin=1 WHERE email='owner@example.com'")
        item={'kind':'site','title':'Site de teste','subject':'Geral','url':'javascript:alert(1)'}
        self.assertEqual(self.request('admin/save',item,csrf)[0],400)
        item['url']='https://example.com'
        self.assertEqual(self.request('admin/save',item,csrf)[0],200)
        added=next(x for x in self.request('content')[1] if x['title']=='Site de teste')
        added['title']='Site atualizado'
        self.assertEqual(self.request('admin/save',added,csrf)[0],200)
        self.assertEqual(self.request('admin/delete',{'id':added['id']},csrf)[0],200)
        self.assertFalse(any(x['id']==added['id'] for x in self.request('content')[1]))
    def test_rate_limit_and_origin(self):
        for _ in range(20):
            self.request('login',{'email':'x@example.com','password':'wrong-password'})
        self.assertEqual(self.request('login',{'email':'x@example.com','password':'wrong-password'})[0],429)
        request=urllib.request.Request(self.base+'/api/register',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(request)
        self.assertEqual(error.exception.code,403)

if __name__=='__main__':
    unittest.main(verbosity=2)
