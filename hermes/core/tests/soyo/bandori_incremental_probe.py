"""Actual native worker/subprocess/HTTP/files: detail priority, incremental state and versions."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib,json,os,subprocess,sys,threading
from soyo.qq import automation_worker


def main():
    root=Path(sys.argv[1]);assert root.is_absolute() and not root.exists();root.mkdir(mode=0o700)
    revision=[1];requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get('Authorization') is None
            requests.append(self.path)
            if self.path=='/sitemap.xml':
                body='<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://bandori.fans/sitemap/ja.xml</loc></sitemap><sitemap><loc>https://bandori.fans/sitemap/zh-Hans.xml</loc></sitemap></sitemapindex>'
            elif self.path=='/sitemap/zh-Hans.xml':
                body='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(
                    f'<url><loc>https://bandori.fans{url}</loc><lastmod>{stamp}</lastmod></url>' for url,stamp in [
                    ('/zh-Hans/bands','2026-10-13T00:00:00Z'),('/zh-Hans/browse/bands-1','2026-10-13T00:00:00Z'),
                    ('/zh-Hans/bands/fixture-a',f'2026-10-{10+revision[0]:02}T00:00:00Z'),
                    ('/zh-Hans/news/fixture-b','2026-10-10T00:00:00Z')])+'</urlset>'
            elif self.path in ('/zh-Hans/bands/fixture-a','/zh-Hans/news/fixture-b'):
                body=f'<html><head><title>Fixture article</title></head><body><nav>must remove navigation</nav><main><h1>Fixture article {revision[0]}</h1><p>'+('明确虚构的详细音乐资讯。'*20)+'</p></main></body></html>'
            else:
                self.send_response(404);self.end_headers();return
            raw=body.encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config={'bandori_knowledge_root':str(root/'knowledge'),'bandori_fixture_allow_loopback':True,
            'bandori_fixture_api_base':f'http://127.0.0.1:{server.server_port}'}
    path=root/'config.json';path.write_text(json.dumps(config));path.chmod(0o600)
    proof={'status':'unverified','platform':'loopback-HTTP','model_calls':0,'actual_bandori_requests':0,'platform_sends':0}
    try:
        def run():
            result=subprocess.run([sys.executable,'-B',automation_worker.__file__,str(path)],input=json.dumps({'action':'bandori_sync','limit':10}),
                text=True,capture_output=True,timeout=30,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'})
            assert result.returncode==0,result.stderr;return json.loads(result.stdout)
        first=run();assert first['state']=='completed' and first['imported_pages']==2 and first['pending_changed_pages']==0
        assert '/zh-Hans/bands' not in requests and '/zh-Hans/browse/bands-1' not in requests and '/sitemap/ja.xml' not in requests
        for receipt in first['artifact_receipts']:
            file=root/'knowledge'/receipt['relative_path'];assert hashlib.sha256(file.read_bytes()).hexdigest()==receipt['artifact_sha256']
            page=json.loads(file.read_text());assert page['title'] and 'must remove navigation' not in page['text']
        before=len(requests);repeat=run();assert repeat['imported_pages']==0 and len(requests)-before==2
        revision[0]=2;changed=run();assert changed['imported_pages']==1
        versions=list((root/'knowledge/native-versions').glob('*/*.json'));assert len(versions)==1
        assert json.loads(versions[0].read_text())['title']=='Fixture article 1'
        proof.update(status='verified_native_bandori_incremental_artifacts',detail_pages_over_navigation=True,only_chinese_sitemap=True,
                     unchanged_pages_not_fetched=True,previous_version_retained=True,artifact_hashes_verified=True,loopback_requests=len(requests))
    except BaseException as error:proof['error']=type(error).__name__+': '+str(error);raise
    finally:
        server.shutdown();server.server_close();thread.join(timeout=10)
        (root/'probe.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof),flush=True)


if __name__=='__main__':main()
