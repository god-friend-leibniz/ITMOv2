import json
import sys
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lab'))
from service import Shop, ShopHTTPServer, make_handler

results=[]
shop=Shop()
server=ShopHTTPServer(('127.0.0.1',0),make_handler(shop))
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
opener=build_opener(ProxyHandler({}))
base=f'http://127.0.0.1:{server.server_port}'

def call(label, method, path, body=None, auth=None, expected=200):
    request=Request(base+path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json', **(auth or {})},method=method)
    try:
        response=opener.open(request,timeout=5)
    except HTTPError as e:
        response=e
    with response:
        result=json.loads(response.read())
        safe_result={'token':'[redacted]'} if path=='/login' and response.status==200 else result
        results.append({'label':label,'status':response.status,'expected':expected,'result':safe_result})
        assert response.status==expected,results[-1]
        return result

try:
    auth={}
    for user in ['alice','bob','staff']:
        auth[user]={'X-Token':call('login-'+user,'POST','/login',{'username':user,'password':'learn-'+user})['token']}
    orders={}
    for user, product in [('alice','lamp'),('bob','chair')]:
        orders[user]=call('purchase-'+user,'POST','/orders',{'product':product},auth[user],201)
    for caller in ['anonymous','alice','bob','staff']:
        for user in ['alice','bob']:
            oid=orders[user]['id']
            allowed=caller in [user,'staff']
            expected=401 if caller=='anonymous' else 200 if allowed else 404
            for route in ['files','assistant']:
                path=f'files/{user}/orders/{oid}/receipt.txt'
                result=call(f'{route}:{caller}:{user}','GET' if route=='files' else 'POST','/files?'+urlencode({'user':user,'path':f'orders/{oid}/receipt.txt'}) if route=='files' else '/assistant/execute', None if route=='files' else {'decision':{'tool':'read_file','arguments':{'path':path}}},auth.get(caller),expected)
                if allowed:
                    assert orders[user]['product'] in result['content']
                    assert f'order {oid}' in result['content']
            call(f'context:{caller}:{user}','GET',f'/assistant/context?order_id={oid}',auth=auth.get(caller),expected=expected)
    for user in ['alice','bob','staff']:
        for path in ['files/alice/orders/3 OR 1=1/receipt.txt','files/alice/orders/03/receipt.txt','files/alice/orders/../bob/receipt.txt','files/alice/orders/2/receipt.txt','files/bob/orders/3/receipt.txt','private/operator-note.txt']:
            call(f'bad-path:{user}:{path}','POST','/assistant/execute',{'decision':{'tool':'read_file','arguments':{'path':path}}},auth[user],404)
    Path(__file__).with_name('files-ai-http-after.json').write_text(json.dumps({'checks':len(results),'all_passed':True,'model_called':False,'results':results},ensure_ascii=False,indent=2))
    print(f'{len(results)} HTTP checks passed')
finally:
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()
    shop.close()
