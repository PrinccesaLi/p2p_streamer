import json
import random
import os
from aiohttp import web

rooms = {}

async def index_handle(request):
    """Отдает HTML-страницу зрителю для корня и для ссылок с кодом"""
    with open("index.html", "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    my_role = None
    my_code = None

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                action = data.get("action")
                
                if action == "ping":
                    continue

                if action == "create":
                    code = data.get("code")
                    my_role = "streamer"
                    
                    if code and code in rooms:
                        print(f"[{code}] Стример переподключился к сети. Комната восстановлена.")
                        rooms[code]["streamer_ws"] = ws
                        my_code = code
                        await ws.send_json({"action": "created", "code": code})
                    else:
                        code = str(random.randint(1000, 9999)) 
                        my_code = code
                        rooms[code] = {"streamer_ws": ws, "viewer_ws": None, "offer": None, "preset": None}
                        print(f"[{code}] КОМНАТА СОЗДАНА")
                        await ws.send_json({"action": "created", "code": code})
                    
                elif action == "offer":
                    code = data.get("code")
                    if code in rooms:
                        rooms[code]["offer"] = data.get("data")
                        if "preset" in data:
                            rooms[code]["preset"] = data["preset"]
                        
                        print(f"[{code}] Стример загрузил видео-пакет")
                        
                        if rooms[code]["viewer_ws"]:
                            payload = {"action": "offer", "data": rooms[code]["offer"]}
                            if rooms[code]["preset"]: payload["preset"] = rooms[code]["preset"]
                            await rooms[code]["viewer_ws"].send_json(payload)
                            print(f"[{code}] ГОРЯЧИЙ РЕСТАРТ: Пакет отправлен зрителю!")
                        
                elif action == "join":
                    code = data.get("code")
                    if code in rooms:
                        my_role = "viewer"
                        my_code = code
                        rooms[code]["viewer_ws"] = ws
                        print(f"[{code}] 👤 Зритель зашел (или нажал F5). Запрашиваю свежий поток у стримера!")
                        
                        if rooms[code]["streamer_ws"]:
                            await rooms[code]["streamer_ws"].send_json({"action": "viewer_request_restart"})
                        else:
                            await ws.send_json({"action": "error", "message": "Стример временно не в сети! Подождите..."})
                    else:
                        await ws.send_json({"action": "error", "message": "Неверный код комнаты!"})
                        
                # 4. Зритель сгенерировал ответ (Answer)
                elif action == "answer":
                    code = data.get("code")
                    if code in rooms and rooms[code]["streamer_ws"]:
                        await rooms[code]["streamer_ws"].send_json({"action": "answer", "data": data.get("data")})
                        print(f"[{code}]P2P ТУННЕЛЬ УСТАНОВЛЕН")

                # 5. Зритель просит экстренный рестарт
                elif action == "request_restart":
                    code = data.get("code")
                    if code in rooms and rooms[code]["streamer_ws"]:
                        await rooms[code]["streamer_ws"].send_json({"action": "viewer_request_restart"})
                        print(f"[{code}]Зритель сообщил о зависании! Команда на рестарт передана.")
                        
    finally:
        if my_code in rooms:
            if my_role == "streamer":
                print(f"[{my_code}]Стример потерял связь с сервером (Ждем реконнект...)")
                rooms[my_code]["streamer_ws"] = None
            elif my_role == "viewer":
                print(f"[{my_code}]Зритель отключился.")
                rooms[my_code]["viewer_ws"] = None
                
    return ws

app = web.Application()

app.router.add_static('/static', os.path.join(os.path.dirname(__file__), 'static'))

app.router.add_get('/ws', websocket_handler)
app.router.add_get('/', index_handle)
app.router.add_get('/{code}', index_handle)

if __name__ == "__main__":
    print("Сигнальный сервер запущен на порту 8080")
    web.run_app(app, host='0.0.0.0', port=8080)