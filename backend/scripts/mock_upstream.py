"""本地开发用 mock 上游：OpenAI 兼容 /models 与 /chat/completions（流式 + 非流式）。

用途：联调与验收时不消耗真实 API 额度。回复内容携带注入消息数与首条 role，
便于验证 persona 注入与历史组装链路。

运行（backend 目录下）：..\\.venv\\Scripts\\python.exe scripts\\mock_upstream.py
监听 127.0.0.1:18080。
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


def _marker(payload: dict) -> str:
    messages = payload.get("messages", [])
    first = messages[0].get("role") if messages else "none"
    return f"mock收到{len(messages)}条消息,首条role={first}"


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/models":
            self._json(200, {"object": "list", "data": [{"id": "mock-chat", "object": "model"}]})
        else:
            self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:
        if self.path != "/chat/completions":
            self._json(404, {"detail": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        marker = _marker(payload)
        usage = {"prompt_tokens": 5, "completion_tokens": 7}
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            frames = [
                {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
                {"choices": [{"index": 0, "delta": {"content": marker}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage},
            ]
            for frame in frames:
                self.wfile.write(f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self._json(200, {
                "choices": [{"index": 0, "message": {"role": "assistant", "content": marker}}],
                "usage": usage,
            })

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 18080), Handler).serve_forever()
