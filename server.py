import base64, json, os, urllib.error, urllib.request, uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

for line in open('.env', encoding='utf-8') if os.path.exists('.env') else []:
    if '=' in line and not line.lstrip().startswith('#'):
        name, value = line.strip().split('=', 1)
        os.environ.setdefault(name, value)

API_URL = os.getenv('IMAGE_API_URL', 'https://xjjuhe.site/v1/images/edits')
API_KEY = os.getenv('IMAGE_API_KEY', '')
MODEL = 'nano_banana_2'
GENERATED = {}

class Handler(SimpleHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/generate':
            return self.send_json(404, {'error': 'Not found'})
        if not API_KEY:
            return self.send_json(500, {'error': '服务端未配置 IMAGE_API_KEY'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 15 * 1024 * 1024:
                return self.send_json(413, {'error': '照片过大，请选择 10MB 以内的 JPG、PNG 或 WEBP'})
            incoming = json.loads(self.rfile.read(length))
            data_url = incoming.get('image', '')
            prompt = incoming.get('prompt', '').strip()
            if not data_url.startswith('data:') or ',' not in data_url:
                raise ValueError('图片数据格式不正确')
            header, encoded = data_url.split(',', 1)
            mime = header.split(';', 1)[0].split(':', 1)[1]
            if mime not in ('image/jpeg', 'image/png', 'image/webp'):
                raise ValueError('仅支持 JPG、PNG 或 WEBP 照片')
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 10 * 1024 * 1024:
                return self.send_json(413, {'error': '照片超过 10MB，请换一张较小的照片'})
            boundary = '----NewLookBoundary7MA4YWxkTrZu0gW'
            def field(name, value):
                return (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode()
            body = field('model', MODEL) + field('prompt', prompt) + field('aspect_ratio', '3:4') + field('response_format', 'url')
            filename = 'photo.' + mime.split('/')[-1].replace('jpeg', 'jpg')
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
            req = urllib.request.Request(API_URL, body, {'Authorization': 'Bearer ' + API_KEY, 'Content-Type': 'multipart/form-data; boundary=' + boundary})
            with urllib.request.urlopen(req, timeout=130) as response:
                result = json.loads(response.read().decode())
            item = (result.get('data') or [{}])[0]
            image = item.get('url') or ('data:image/png;base64,' + item['b64_json'] if item.get('b64_json') else None)
            if not image: raise ValueError('接口返回中没有图片结果')
            download_url = None
            if image.startswith('https://'):
                download_id = uuid.uuid4().hex
                GENERATED[download_id] = image
                download_url = '/api/download/' + download_id
            self.send_json(200, {'image': image, 'download_url': download_url})
        except urllib.error.HTTPError as exc:
            self.send_json(502, {'error': f'生图接口返回 {exc.code}', 'detail': exc.read().decode(errors='replace')[:1200]})
        except Exception as exc:
            self.send_json(400, {'error': str(exc)})

    def do_GET(self):
        if self.path.startswith('/api/download/'):
            image_url = GENERATED.get(self.path.removeprefix('/api/download/'))
            if not image_url:
                return self.send_json(404, {'error': '图片链接已过期，请重新生成'})
            if urlparse(image_url).scheme != 'https':
                return self.send_json(400, {'error': '图片地址不安全'})
            try:
                req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'image/*'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    image_data = response.read(20 * 1024 * 1024 + 1)
                    content_type = response.headers.get('Content-Type', 'image/png')
                if len(image_data) > 20 * 1024 * 1024:
                    return self.send_json(413, {'error': '生成图片超过 20MB'})
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Disposition', 'attachment; filename="new-look.png"')
                self.send_header('Content-Length', str(len(image_data)))
                self.end_headers(); self.wfile.write(image_data)
            except Exception as exc:
                self.send_json(502, {'error': f'下载生成图片失败：{exc}'})
            return
        if urlparse(self.path).path not in ('/', '/index.html', '/assets/sample-portrait.jpg'):
            return self.send_json(404, {'error': 'Not found'})
        return super().do_GET()

if __name__ == '__main__':
    print('New Look running at http://localhost:8000')
    ThreadingHTTPServer(('127.0.0.1', int(os.getenv('PORT', '8000'))), Handler).serve_forever()
