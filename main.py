import asyncio, json, time, uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

MAX_LEN=1000
RATE_LIMIT=8
RATE_WINDOW=10
clients={}
waiting=defaultdict(deque)
lock=asyncio.Lock()
rates=defaultdict(deque)

PAGE="""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WorldHello</title><style>
*{box-sizing:border-box}body{margin:0;padding:18px;background:#0b1020;color:#f8fafc;font:16px system-ui;display:grid;place-items:center;min-height:100vh}main{width:min(720px,100%);background:#121a2d;border:1px solid #29344d;border-radius:22px;padding:24px}h1{margin:0;font-size:38px}.blue{color:#7dd3fc}p{color:#b8c4d9}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.controls>*{flex:1;min-width:120px}input,select,button{font:inherit;border-radius:10px;padding:12px;border:1px solid #394762;background:#1b2740;color:white}button{cursor:pointer}.primary{background:#0284c7;border-color:#0284c7}#status{background:#1b2740;padding:10px;border-radius:10px}#messages{height:300px;overflow:auto;margin:12px 0;border:1px solid #29344d;border-radius:12px;padding:10px}.msg{padding:8px;margin:6px 0;border-radius:8px;background:#1b2740;overflow-wrap:anywhere}form{display:flex;gap:8px}form input{flex:1;min-width:0}.fine{font-size:12px;color:#94a3b8}</style></head><body><main><h1>World<span class="blue">Hello</span></h1><p>Meet someone new. One conversation at a time.</p><div class="controls"><input id="nick" maxlength="24" placeholder="Nickname (not real name)" value="Guest"><select id="lang"><option value="any">Any language</option><option>English</option><option>Hindi</option><option>Assamese</option><option>Japanese</option><option>Spanish</option><option>French</option></select><button id="start" class="primary">Find a stranger</button><button id="next" disabled>Next</button></div><div id="status" role="status">Choose a nickname to start.</div><div id="messages" aria-live="polite"></div><form id="form"><input id="msg" maxlength="1000" placeholder="Write a message…" disabled><button id="send" class="primary" disabled>Send</button></form><p class="fine">Early prototype for adults 18+. Do not share personal information. Safety reporting, persistent blocks, and production moderation are not yet implemented.</p></main><script>
const $=x=>document.getElementById(x);let ws=null,matched=false;function say(s){$('status').textContent=s}function add(s){let d=document.createElement('div');d.className='msg';d.textContent=s;$('messages').append(d);$('messages').scrollTop=$('messages').scrollHeight}
function start(){if(ws){ws.onclose=null;ws.close()}matched=false;$('messages').replaceChildren();$('msg').disabled=true;$('send').disabled=true;$('next').disabled=true;say('Connecting…');ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');ws.onopen=()=>ws.send(JSON.stringify({type:'join',nickname:$('nick').value.trim().slice(0,24)||'Guest',language:$('lang').value}));ws.onmessage=e=>{let d;try{d=JSON.parse(e.data)}catch{return}if(d.type==='waiting')say('Looking for someone…');if(d.type==='matched'){matched=true;$('msg').disabled=false;$('send').disabled=false;$('next').disabled=false;say('Connected. Say hello!');add('You are connected with a stranger.')}if(d.type==='message')add((d.nickname||'Stranger')+': '+d.text);if(d.type==='partner_left'){matched=false;$('msg').disabled=true;$('send').disabled=true;say('Stranger disconnected. Tap Next to find someone else.')}if(d.type==='error')say(d.message)};ws.onclose=()=>{matched=false;$('msg').disabled=true;$('send').disabled=true;if($('status').textContent==='Connecting…')say('Connection closed. Try again.')};ws.onerror=()=>say('Connection error. Try again.')}
$('start').onclick=start;$('next').onclick=start;$('form').onsubmit=e=>{e.preventDefault();let s=$('msg').value.trim();if(!s||!matched||!ws)return;ws.send(JSON.stringify({type:'message',text:s}));add('You: '+s);$('msg').value=''};
</script></body></html>"""

async def disconnect(cid):
    async with lock:
        c=clients.pop(cid,None)
        if not c:return
        partner=c.get("partner")
        if partner in clients:
            clients[partner]["partner"]=None
            try: await clients[partner]["ws"].send_json({"type":"partner_left"})
            except Exception: pass
        try: waiting[c["language"]].remove(cid)
        except ValueError: pass
        rates.pop(cid,None)

app=FastAPI(title="WorldHello",version="0.1.0")
@app.get("/",response_class=HTMLResponse)
async def home(): return HTMLResponse(PAGE)
@app.get("/health")
async def health(): return {"status":"ok","service":"worldhello"}
@app.websocket("/ws")
async def chat(ws:WebSocket):
    await ws.accept();cid=uuid.uuid4().hex
    try:
        raw=await asyncio.wait_for(ws.receive_text(),timeout=20)
        if len(raw)>4000: await ws.close(code=1009);return
        try: hello=json.loads(raw)
        except ValueError: await ws.close(code=1008);return
        if hello.get("type")!="join": await ws.close(code=1008);return
        nickname=str(hello.get("nickname","Guest")).strip()[:24] or "Guest"
        language=str(hello.get("language","any"))[:30]
        allowed={"any","English","Hindi","Assamese","Japanese","Spanish","French"}
        if language not in allowed: language="any"
        async with lock:
            clients[cid]={"ws":ws,"nickname":nickname,"language":language,"partner":None}
            candidate=None
            queues=[waiting[language]] if language!="any" else []
            if language!="any": queues.append(waiting["any"])
            queues += [q for k,q in waiting.items() if k!=language and (language=="any" or k not in {"any"})]
            for q in queues:
                while q:
                    possible=q.popleft()
                    if possible in clients and clients[possible]["partner"] is None:
                        candidate=possible;break
                if candidate:break
            if candidate:
                clients[cid]["partner"]=candidate;clients[candidate]["partner"]=cid
            else: waiting[language].append(cid)
        if candidate:
            await ws.send_json({"type":"matched"})
            await clients[candidate]["ws"].send_json({"type":"matched"})
        else: await ws.send_json({"type":"waiting"})
        while True:
            raw=await ws.receive_text()
            if len(raw)>MAX_LEN+200:
                await ws.send_json({"type":"error","message":"Message too large."});continue
            try:data=json.loads(raw)
            except ValueError:continue
            if data.get("type")!="message":continue
            message=str(data.get("text","")).strip()
            if not message:continue
            if len(message)>MAX_LEN:
                await ws.send_json({"type":"error","message":"Message too long."});continue
            now=time.monotonic();bucket=rates[cid]
            while bucket and now-bucket[0]>RATE_WINDOW:bucket.popleft()
            if len(bucket)>=RATE_LIMIT:
                await ws.send_json({"type":"error","message":"Sending too quickly. Wait a moment."});continue
            bucket.append(now);partner=clients.get(cid,{}).get("partner")
            if partner in clients:
                await clients[partner]["ws"].send_json({"type":"message","nickname":clients[cid]["nickname"],"text":message})
    except (WebSocketDisconnect,asyncio.TimeoutError):pass
    except Exception:pass
    finally:await disconnect(cid)
