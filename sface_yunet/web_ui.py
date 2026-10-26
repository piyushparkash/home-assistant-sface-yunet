"""Ingress-only management UI with per-process CSRF protection."""
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit


def handler_for(manager):
    token=secrets.token_urlsafe(32)
    assets=Path(__file__).with_name('web')
    allowed=set(os.environ.get('UI_TRUSTED_IPS','127.0.0.1,::1,172.30.32.2').split(','))

    class Handler(BaseHTTPRequestHandler):
        def send(self,body,status=200,content_type='application/json'):
            if isinstance(body,(dict,list)):
                body=json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store, private')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def trusted(self):
            if self.client_address[0] not in allowed:
                self.send({'error':'Open this app through Home Assistant Ingress'},403)
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            path=urlsplit(self.path).path
            try:
                if path in ('/','/index.html','/app.js','/style.css'):
                    name='index.html' if path=='/' else path[1:]
                    mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
                    self.send((assets/name).read_bytes(),content_type=mime[Path(name).suffix])
                elif path=='/api/state':
                    self.send({**manager.state(),'csrf_token':token})
                elif path=='/api/cameras':
                    try:
                        self.send({'cameras':manager.available_cameras()})
                    except Exception:
                        self.send({'error':'Cannot list Home Assistant cameras. Check app permissions and restart it.'},503)
                elif path.startswith('/api/photo/'):
                    self.send(manager.photo(path.rsplit('/',1)[-1]),content_type='image/jpeg')
                else:
                    self.send({'error':'Not found'},404)
            except ValueError as exc:
                self.send({'error':str(exc)},404)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def do_POST(self):
            if not self.trusted():
                return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=12*1024*1024:
                    raise ValueError('Request is empty or larger than 12 MiB')
                raw=self.rfile.read(size)
            except ValueError as exc:
                self.send({'error':str(exc)},413)
                return
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),token):
                self.send({'error':'Session expired. Refresh the page and try again.'},403)
                return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.send({'error':'JSON required'},415)
                return
            try:
                data=json.loads(raw)
                if not isinstance(data,dict):
                    raise ValueError('Expected a JSON object')
                action=urlsplit(self.path).path.removeprefix('/api/')
                if action=='camera':
                    manager.save_camera(data)
                elif action=='scan':
                    manager.enqueue(data)
                else:
                    manager.change(action,data)
                self.send({'success':True})
            except (ValueError,TypeError,KeyError) as exc:
                self.send({'error':str(exc)},400)
            except Exception:
                self.send({'error':'Unable to save changes. Check the app log and try again.'},500)

        def log_message(self,*args):
            pass

    return Handler
