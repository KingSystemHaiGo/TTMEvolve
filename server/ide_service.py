"""
server/ide_service.py — IDE 文件系统服务

为 Electron / Web GUI 提供直接的文件 CRUD 与预览端点。
复用 Executor 的本地处理器与 Sandbox 路径校验，但跳过 ApprovalEngine，
因为这里的人类操作不等同于 Agent 提出的动作。
"""

from __future__ import annotations
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class IdeService:
    """轻量 IDE 文件服务，挂载在 AppServer 的 /fs/* 与 /preview/file 路由下。"""

    MAX_TEXT_SIZE = 1024 * 1024  # 1 MB

    # 常见扩展名 -> MIME（补充 mimetypes 库可能缺失的类型）
    MIME_OVERRIDES = {
        ".js": "application/javascript; charset=utf-8",
        ".ts": "application/typescript; charset=utf-8",
        ".tsx": "application/typescript; charset=utf-8",
        ".jsx": "application/javascript; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        # image
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".ico": "image/x-icon",
        # audio
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
        ".m4a": "audio/mp4",
        # video
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
    }

    # 扩展名 -> 素材类型
    ASSET_TYPE_MAP = {
        # image
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".gif": "image",
        ".svg": "image",
        ".webp": "image",
        ".bmp": "image",
        ".ico": "image",
        # audio
        ".mp3": "audio",
        ".wav": "audio",
        ".ogg": "audio",
        ".flac": "audio",
        ".aac": "audio",
        ".m4a": "audio",
        # video
        ".mp4": "video",
        ".webm": "video",
        ".mov": "video",
        ".mkv": "video",
    }

    # 扫描素材时忽略的目录
    IGNORED_DIRS = {
        "node_modules",
        ".venv",
        "vendor",
        "storage",
        ".git",
        "__pycache__",
        "dist",
        ".tmp",
        ".claude",
    }

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    def _sandbox_check(self, tool_name: str, path: str) -> Dict[str, Any]:
        return self.agent.executor.sandbox.validate(tool_name, {"path": path})

    def list_directory(self, path: str) -> Tuple[Dict[str, Any], int]:
        verdict = self._sandbox_check("list_directory", path)
        if not verdict["allowed"]:
            return {"ok": False, "error": verdict["reason"]}, 403

        result = self.agent.executor._list_directory(path)
        if not result.get("ok"):
            return result, 500

        items = result.get("items", [])
        # 目录在前，文件在后，均按名称排序
        items.sort(key=lambda item: (not item.get("is_dir", False), item["name"].lower()))
        return {"ok": True, "items": items}, 200

    def read_file(self, path: str) -> Tuple[Dict[str, Any], int]:
        verdict = self._sandbox_check("read_file", path)
        if not verdict["allowed"]:
            return {"ok": False, "error": verdict["reason"]}, 403

        target = self.agent.executor.project_root / path
        try:
            size = target.stat().st_size
            if size > self.MAX_TEXT_SIZE:
                return {"ok": False, "error": "文件超过 1MB，请用外部编辑器打开"}, 413
            content = target.read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "content": content}, 200
        except FileNotFoundError:
            return {"ok": False, "error": "文件不存在"}, 404
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500

    def write_file(self, path: str, content: str) -> Tuple[Dict[str, Any], int]:
        verdict = self._sandbox_check("modify_file", path)
        if not verdict["allowed"]:
            return {"ok": False, "error": verdict["reason"]}, 403

        if len(content.encode("utf-8")) > self.MAX_TEXT_SIZE:
            return {"ok": False, "error": "内容超过 1MB"}, 413

        result = self.agent.executor._modify_file(path, content)
        if not result.get("ok"):
            return result, 500
        return result, 200

    def delete_file(self, path: str) -> Tuple[Dict[str, Any], int]:
        verdict = self._sandbox_check("delete_file", path)
        if not verdict["allowed"]:
            return {"ok": False, "error": verdict["reason"]}, 403

        result = self.agent.executor._delete_file(path)
        if not result.get("ok"):
            return result, 500
        return result, 200

    def _mime_for_path(self, target: Path) -> str:
        """返回文件对应的 MIME 类型，优先使用覆盖表保证跨平台一致。"""
        suffix = target.suffix.lower()
        if suffix in self.MIME_OVERRIDES:
            return self.MIME_OVERRIDES[suffix]
        mime, _ = mimetypes.guess_type(str(target))
        return mime or "application/octet-stream"

    def scan_assets(
        self, path: str, extensions: Optional[str] = None
    ) -> Tuple[Dict[str, Any], int]:
        """递归扫描项目目录下的媒体素材文件。"""
        verdict = self._sandbox_check("list_directory", path)
        if not verdict["allowed"]:
            return {"ok": False, "error": verdict["reason"]}, 403

        root = self.agent.executor.project_root / path
        if not root.exists() or not root.is_dir():
            return {"ok": False, "error": "路径不存在或不是目录"}, 400

        ext_filter: Optional[set[str]] = None
        if extensions:
            ext_filter = {
                e.strip().lower()
                for e in extensions.split(",")
                if e.strip()
            }

        assets: List[Dict[str, Any]] = []
        try:
            for p in root.rglob("*"):
                rel = p.relative_to(root)
                # 跳过隐藏目录与已忽略目录
                if any(
                    part.startswith(".") or part in self.IGNORED_DIRS
                    for part in rel.parts
                ):
                    continue
                if not p.is_file():
                    continue
                suffix = p.suffix.lower()
                if ext_filter and suffix not in ext_filter:
                    continue
                asset_type = self.ASSET_TYPE_MAP.get(suffix, "unknown")
                if asset_type == "unknown" and not ext_filter:
                    continue
                assets.append(
                    {
                        "name": p.name,
                        "path": str(
                            p.relative_to(self.agent.executor.project_root)
                        ).replace("\\", "/"),
                        "type": asset_type,
                        "size": p.stat().st_size,
                    }
                )
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500

        assets.sort(key=lambda a: a["path"])
        return {"ok": True, "assets": assets}, 200

    def stat_file(self, path: str) -> Tuple[Dict[str, Any], int]:
        """返回文件的元数据（大小、MIME、修改时间等）。"""
        verdict = self._sandbox_check("read_file", path)
        if not verdict["allowed"]:
            return {"ok": False, "error": verdict["reason"]}, 403

        target = self.agent.executor.project_root / path
        if not target.exists():
            return {"ok": False, "error": "文件不存在"}, 404

        try:
            st = target.stat()
            return {
                "ok": True,
                "name": target.name,
                "path": str(
                    target.relative_to(self.agent.executor.project_root)
                ).replace("\\", "/"),
                "size": st.st_size,
                "mime": self._mime_for_path(target),
                "is_dir": target.is_dir(),
                "modified": st.st_mtime,
            }, 200
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500

    def preview_file(self, path: str) -> Tuple[bool, bytes, str, int]:
        """返回 (ok, bytes_or_error_text, mime_type, http_status)。"""
        verdict = self._sandbox_check("read_file", path)
        if not verdict["allowed"]:
            return False, verdict["reason"].encode("utf-8"), "text/plain; charset=utf-8", 403

        target = self.agent.executor.project_root / path
        if not target.exists():
            return False, b"Not found", "text/plain; charset=utf-8", 404
        if target.is_dir():
            return False, b"Cannot preview directory", "text/plain; charset=utf-8", 400

        mime = self._mime_for_path(target)

        try:
            data = target.read_bytes()
        except Exception as e:
            return False, str(e).encode("utf-8"), "text/plain; charset=utf-8", 500

        return True, data, mime, 200
