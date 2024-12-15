import tornado.ioloop
import tornado.web
import tornado.websocket
import redis
import asyncio
import json

# Подключение к Redis
redis_client = redis.Redis()

class ChatHandler(tornado.websocket.WebSocketHandler):
    clients = set()
    usernames = {}

    def check_origin(self, origin):
        return True

    def open(self):
        ChatHandler.clients.add(self)
        self.username = None

    def on_message(self, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "set_username":
                username = data.get("username", "").strip()
                if username:
                    self.username = username
                    ChatHandler.usernames[self] = self.username
                    self.write_message(json.dumps({"type": "info", "message": f"Привет, {self.username}!"}))
                    redis_client.publish("chat_channel", f"🌟{self.username} подключился!")
                    self.update_user_list()
                else:
                    self.write_message(json.dumps({"type": "error", "message": "Некорректный ник"}))
            elif msg_type == "message":
                if self.username:
                    redis_client.publish("chat_channel", f"{self.username}: {data.get('message', '').strip()}")
                else:
                    self.write_message(json.dumps({"type": "error", "message": "Нельзя отправлять сообщения без ника"}))
        except Exception as e:
            self.write_message(json.dumps({"type": "error", "message": "Некорректный формат сообщения"}))

    def on_close(self):
        ChatHandler.clients.remove(self)
        username = ChatHandler.usernames.pop(self, "Unknown user")
        redis_client.publish("chat_channel", f"👋 {username} отключился!")
        self.update_user_list()

    def update_user_list(self):
        user_list = list(ChatHandler.usernames.values())
        message = json.dumps({"type": "user_list", "users": user_list})
        for client in ChatHandler.clients:
            if client.ws_connection:
                client.write_message(message)

    @classmethod
    async def send_message_to_all(cls, message):
        for client in cls.clients:
            if client.ws_connection:
                client.write_message(json.dumps({"type": "message", "message": message}))

async def redis_listener():
    pubsub = redis_client.pubsub()
    pubsub.subscribe("chat_channel")
    while True:
        message = pubsub.get_message(ignore_subscribe_messages=True)
        if message:
            await ChatHandler.send_message_to_all(message["data"].decode("utf-8"))
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    app = tornado.web.Application([
        (r"/ws", ChatHandler),
    ])
    app.listen(8888)
    print("WebSocket server started at ws://localhost:8888/ws")

    loop = asyncio.get_event_loop()
    loop.create_task(redis_listener())
    tornado.ioloop.IOLoop.current().start()
