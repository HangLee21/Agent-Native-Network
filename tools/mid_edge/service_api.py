"""LoRa extensions to the existing single-owner local Wi-Fi business API."""
import json
from urllib.parse import urlsplit,parse_qs
from tools.mid_sim_console.local_edge import Handler as BaseHandler
from .client import EdgeError,UnsupportedFirmware


class Handler(BaseHandler):
    def handle_api(self,write):
        url=urlsplit(self.path)
        if not url.path.startswith('/api/edge/lora/'):
            return super().handle_api(write)
        try:
            self.connection.settimeout(12)
            host=self.headers.get('Host');port=self.server.server_port
            if self.headers.get_all('Host')!=[host] or host not in (f'localhost:{port}',f'127.0.0.1:{port}'):
                return self.reply(403,dict(error='loopback Host required'))
            origins=self.headers.get_all('Origin',[])
            if len(origins)>1 or (write or origins) and origins!=['http://'+host]:
                return self.reply(403,dict(error='same origin required'))
            edge=self.server.app.edge
            if not write and url.path=='/api/edge/lora/status':return self.reply(200,edge.lora_status())
            if not write and url.path=='/api/edge/lora/events':
                q=parse_qs(url.query)
                return self.reply(200,edge.lora_events(int(q.get('after',['0'])[0]),float(q.get('wait',['0'])[0])))
            if write and url.path=='/api/edge/lora/config':
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('bounded configuration JSON required')
                fields=json.loads(self.rfile.read(size))
                if not isinstance(fields,dict):raise ValueError('configuration object required')
                return self.reply(200,edge.lora_config(**fields))
            return self.reply(404,dict(error='unsupported LoRa operation'))
        except UnsupportedFirmware as exc:return self.reply(422,dict(error=str(exc),supported=False))
        except (ValueError,TypeError) as exc:return self.reply(400,dict(error=str(exc)))
        except (EdgeError,TimeoutError,OSError) as exc:return self.reply(503,dict(error=str(exc),retry_automatically=False))
