"""
llm/local_llm.py — 本地 GGUF 模型实现

基于 llama-cpp-python 加载 MiniCPM5-1B 等 GGUF 模型，实现 LLMInterface。
针对 MiniCPM5-1B 做了优化：
- 懒加载：首次调用时才加载模型
- System KV Cache：每个 system prompt + thinking 模式的状态复用
- 上下文预算管理：通过 ContextBudgetManager 自动截断旧轨迹，保留最近若干步
- 启动预热：加载后做一次极小推理，避免首次正式调用卡顿
- 混合 thinking：推理类调用开 thinking，动作/代码类调用关 thinking
"""

from __future__ import annotations
import hashlib
import os
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import Config
from llm.context_budget import BudgetStats, ContextBudgetManager
from llm.interface import LLMInterface
from llm.llama_tuning import LlamaTuning, resolve_llama_tuning
from llm.utils import parse_llm_json

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None


DEFAULT_MODEL_REPO = "openbmb/MiniCPM5-1B-GGUF"
DEFAULT_MODEL_FILE = "MiniCPM5-1B-Q4_K_M.gguf"

# MiniCPM5-1B special tokens
IM_START = "<|im_start|>"
IM_END = "<|im_end|>"
ENDOFTEXT = "<|endoftext|>"
THINK_START = "<think>"
THINK_END = "</think>"


class LocalLLM(LLMInterface):
    """本地 GGUF 模型，默认 MiniCPM5-1B。"""

    def __init__(self, config: Optional[Config] = None):
        if Llama is None:
            raise ImportError(
                "请安装 llama-cpp-python：pip install llama-cpp-python\n"
                "Windows GPU 加速：$env:CMAKE_ARGS='-DLLAMA_CUDA=on'; "
                "pip install llama-cpp-python --no-cache-dir --force-reinstall"
            )

        self.cfg = config or Config()
        self.model_path = Path(self.cfg.get("llm.model_path", f"./models/{DEFAULT_MODEL_FILE}"))
        self.tuning: LlamaTuning = resolve_llama_tuning(self.cfg)
        self.n_ctx = self.tuning.n_ctx
        self.n_gpu_layers = self.tuning.n_gpu_layers
        self.n_batch = self.tuning.n_batch
        self.n_ubatch = self.tuning.n_ubatch
        self.n_threads = self.tuning.n_threads
        self.n_threads_batch = self.tuning.n_threads_batch
        self.use_mmap = self.tuning.use_mmap
        self.use_mlock = self.tuning.use_mlock
        self.flash_attn = self.tuning.flash_attn
        self.offload_kqv = self.tuning.offload_kqv
        self.cache_type_k = self.cfg.get("llm.cache_type_k", "f16")
        self.cache_type_v = self.cfg.get("llm.cache_type_v", "f16")
        self.temperature = self.cfg.get("llm.temperature", 0.7)
        self.top_p = self.cfg.get("llm.top_p", 0.95)
        self.max_history_steps = self.cfg.get("llm.max_history_steps", 6)
        self._reserve_tokens = self.cfg.get("llm.reserve_tokens", 256)
        self._verbose = self.cfg.get("llm.verbose", False)
        self._enable_thinking_for_reasoning = self.cfg.get("llm.enable_thinking_for_reasoning", True)
        # Disabled by default for correctness. The previous cache path saved state
        # after generation, which can leak prior assistant output into later turns.
        self._enable_kv_cache = self.cfg.get("llm.compression.enable_kv_cache", False)
        self._kv_cache_max_entries = self.cfg.get("llm.kv_cache_max_entries", 8)

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"本地模型未找到：{self.model_path}\n"
                f"请运行：python scripts/download_model.py\n"
                f"或在 config.json 中配置 llm.model_path"
            )

        # 懒加载占位
        self._model: Optional[Llama] = None
        # KV cache keyed by (system_prompt, enable_thinking). LRU eviction.
        self._system_states: "OrderedDict[Tuple[str, bool], bytes]" = OrderedDict()
        # 全轮次 KV cache keyed by prompt hash. 用于 trajectory 追加场景。
        self._turn_states: "OrderedDict[str, bytes]" = OrderedDict()
        self._turn_cache_max_entries = max(0, self.cfg.get("llm.turn_cache_max_entries", 2))
        self._loaded_at: Optional[float] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local_llm_")

        self._budget = ContextBudgetManager(
            n_ctx=self.n_ctx,
            reserve_tokens=self._reserve_tokens,
            tokenizer=self._token_count,
        )
        self._last_budget_stats: Optional[BudgetStats] = None
        self._last_call_stats: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 模型生命周期
    # ------------------------------------------------------------------
    @property
    def model(self) -> Llama:
        if self._model is None:
            print(f"[LocalLLM] 正在加载模型：{self.model_path}")
            start = time.time()
            self._model = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_gpu_layers=self.n_gpu_layers,
                n_batch=self.n_batch,
                n_ubatch=self.n_ubatch,
                n_threads=self.n_threads,
                n_threads_batch=self.n_threads_batch,
                use_mmap=self.use_mmap,
                use_mlock=self.use_mlock,
                flash_attn=self.flash_attn,
                offload_kqv=self.offload_kqv,
                cache_type_k=self.cache_type_k,
                cache_type_v=self.cache_type_v,
                verbose=self._verbose,
            )
            self._loaded_at = time.time()
            print(f"[LocalLLM] 模型加载完成，耗时 {self._loaded_at - start:.2f}s")
            self._warmup()
        return self._model

    def _warmup(self) -> None:
        """加载后做一次极小推理，避免首次正式调用冷启动。"""
        try:
            prompt = self._build_prompt(
                [
                    {"role": "system", "content": "你是一个有用的助手。"},
                    {"role": "user", "content": "你好"},
                ],
                enable_thinking=False,
            )
            self.model(
                prompt,
                max_tokens=1,
                temperature=0.0,
                stop=[IM_END, IM_START, ENDOFTEXT],
            )
            print("[LocalLLM] 预热完成")
        except Exception as e:
            print(f"[LocalLLM] 预热跳过：{e}")

    # ------------------------------------------------------------------
    # 提示词格式：MiniCPM5-1B chat template
    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        messages: List[Dict[str, str]],
        enable_thinking: bool,
        add_generation_prompt: bool = True,
    ) -> str:
        """Render MiniCPM5-1B chat prompt.

        Template:
        {% for message in messages %}
        <|im_start|>{{ message.role }}
        {{ message.content }}<|im_end|>
        {% endfor %}
        {% if add_generation_prompt %}
        <|im_start|>assistant
        {% if not enable_thinking %}<think>

        </think>

        {% endif %}
        {% endif %}
        """
        lines: List[str] = []
        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            lines.append(f"{IM_START}{role}\n{content}{IM_END}")

        # Add generation prompt
        if add_generation_prompt:
            lines.append(f"{IM_START}assistant")
            if not enable_thinking:
                lines.append(f"{THINK_START}\n\n{THINK_END}\n")

        return "\n".join(lines)

    def _token_count(self, text: str) -> int:
        return len(self.model.tokenize(text.encode("utf-8"), add_bos=True))

    # ------------------------------------------------------------------
    # 核心调用：复用 system prompt 的 KV Cache
    # ------------------------------------------------------------------
    def _call(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        enable_thinking: bool = False,
    ) -> str:
        m = self.model
        total_t0 = time.time()

        system_messages = [{"role": "system", "content": system}]
        system_prompt = self._build_prompt(
            system_messages,
            enable_thinking=enable_thinking,
            add_generation_prompt=False,
        )

        # 上下文预算：按 token 数截断 user 文本
        fit_t0 = time.time()
        fitted_user, stats = self._budget.fit(system_prompt, user, max_tokens)
        fit_ms = (time.time() - fit_t0) * 1000
        self._last_budget_stats = stats

        messages = system_messages + [{"role": "user", "content": fitted_user}]
        prompt = self._build_prompt(messages, enable_thinking=enable_thinking)

        # 全轮次 KV cache：若 prompt 仅追加，命中后可直接复用
        prompt_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()
        turn_state = self._turn_states.get(prompt_hash)
        if turn_state and self._enable_kv_cache:
            try:
                load_t0 = time.time()
                m.load_state(turn_state)
                load_ms = (time.time() - load_t0) * 1000
                # 状态已包含完整 prompt，直接生成
                gen_t0 = time.time()
                output = self._executor.submit(
                    m,
                    "",
                    max_tokens=max_tokens,
                    temperature=temperature if temperature is not None else self.temperature,
                    top_p=self.top_p,
                    stop=stop or [IM_END, IM_START, ENDOFTEXT],
                ).result()
                gen_ms = (time.time() - gen_t0) * 1000
                text = output["choices"][0]["text"]
                self._record_perf("turn_cache_hit", output, 0, load_ms, gen_ms, 0, len(text), stats)
                return text.strip()
            except Exception:
                pass

        # 复用 system prompt 的 KV state（如果已缓存）
        state_key = (system, enable_thinking)
        state = self._system_states.get(state_key)
        if state and self._enable_kv_cache:
            try:
                load_t0 = time.time()
                m.load_state(state)
                load_ms = (time.time() - load_t0) * 1000
                continuation = prompt[len(system_prompt):].lstrip("\n")
                token_t0 = time.time()
                tokenize_len = self._token_count(continuation)
                token_ms = (time.time() - token_t0) * 1000
                gen_t0 = time.time()
                output = self._executor.submit(
                    m,
                    continuation,
                    max_tokens=max_tokens,
                    temperature=temperature if temperature is not None else self.temperature,
                    top_p=self.top_p,
                    stop=stop or [IM_END, IM_START, ENDOFTEXT],
                ).result()
                gen_ms = (time.time() - gen_t0) * 1000
                text = output["choices"][0]["text"]
                self._record_perf("system_cache_hit", output, token_ms, load_ms, gen_ms, tokenize_len, len(text), stats)
                # 保存全轮次状态供后续追加复用
                self._save_turn_state(prompt_hash)
                return text.strip()
            except Exception:
                pass

        # 首次调用：完整 prompt
        token_t0 = time.time()
        tokenize_len = self._token_count(prompt)
        token_ms = (time.time() - token_t0) * 1000
        gen_t0 = time.time()
        output = self._executor.submit(
            m,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            top_p=self.top_p,
            stop=stop or [IM_END, IM_START, ENDOFTEXT],
        ).result()
        gen_ms = (time.time() - gen_t0) * 1000
        try:
            save_t0 = time.time()
            self._system_states[state_key] = m.save_state()
            self._system_states.move_to_end(state_key)
            while len(self._system_states) > self._kv_cache_max_entries:
                self._system_states.popitem(last=False)
            save_ms = (time.time() - save_t0) * 1000
        except Exception:
            save_ms = 0.0
        self._save_turn_state(prompt_hash)
        text = output["choices"][0]["text"]
        self._record_perf("full_eval", output, token_ms, 0, gen_ms, tokenize_len, len(text), stats, save_ms=save_ms)
        return text.strip()

    def _save_turn_state(self, prompt_hash: str) -> None:
        """保存完整 prompt 的 KV state，用于 trajectory 追加场景。"""
        if not self._enable_kv_cache:
            return
        try:
            self._turn_states[prompt_hash] = self._model.save_state()
            self._turn_states.move_to_end(prompt_hash)
            while len(self._turn_states) > self._turn_cache_max_entries:
                self._turn_states.popitem(last=False)
        except Exception:
            pass

    def _record_perf(
        self,
        mode: str,
        output: Dict[str, Any],
        tokenize_ms: float,
        kv_load_ms: float,
        generate_ms: float,
        input_tokens: int,
        output_chars: int,
        stats: Optional[BudgetStats],
        save_ms: float = 0.0,
    ) -> None:
        usage = output.get("usage", {}) if isinstance(output, dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens") or input_tokens or 0)
        completion_tokens = int(usage.get("completion_tokens") or usage.get("completion_tokens_details", {}).get("tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        if completion_tokens <= 0:
            try:
                completion_tokens = len(self.model.tokenize(output["choices"][0]["text"].encode("utf-8"), add_bos=False))
                total_tokens = prompt_tokens + completion_tokens
            except Exception:
                pass
        tokens_per_sec = (completion_tokens / (generate_ms / 1000)) if generate_ms > 0 else 0.0
        budget = {
            "token_usage_ratio": stats.token_usage_ratio if stats else 0.0,
            "context_window_ratio": stats.context_window_ratio if stats else 0.0,
        } if stats else {}
        self._last_call_stats = {
            "provider": "local",
            "mode": mode,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tokenize_ms": round(tokenize_ms, 1),
            "kv_load_ms": round(kv_load_ms, 1),
            "generate_ms": round(generate_ms, 1),
            "save_ms": round(save_ms, 1),
            "tokens_per_sec": round(tokens_per_sec, 2),
            "budget": budget,
        }
        print(
            f"[LocalLLM] mode={mode} tokenize={tokenize_ms:.1f}ms "
            f"kv_load={kv_load_ms:.1f}ms generate={generate_ms:.1f}ms "
            f"save={save_ms:.1f}ms prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
            f"tokens/sec={tokens_per_sec:.1f} output_chars={output_chars} "
            f"budget={budget}"
        )

    def last_budget_stats(self) -> Optional[BudgetStats]:
        return self._last_budget_stats

    def last_call_stats(self) -> Dict[str, Any]:
        return dict(self._last_call_stats)

    def tuning_info(self) -> Dict[str, Any]:
        return self.tuning.as_dict()

    # ------------------------------------------------------------------
    # LLMInterface 实现
    # ------------------------------------------------------------------
    def think(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
    ) -> str:
        system = (
            "You are TTMEvolve, a local TapTap Maker development agent running inside an IDE. "
            "Think briefly about the next useful step. Do not copy tool schemas. "
            "Do not output template fragments."
        )
        if not trajectory and not tools_description:
            user = context
        else:
            user = self._build_think_user(task, context, trajectory, tools_description)
        enable_thinking = self._enable_thinking_for_reasoning
        return self._call(system, user, max_tokens=512, enable_thinking=enable_thinking)

    def think_multimodal(
        self,
        task: str,
        content,
        trajectory,
        tools_description,
        *,
        attachments=None,
    ) -> str:
        """Local LLM multimodal think. Most local models do not support
        image inputs; the default implementation degrades to a text
        description. Subclasses that wire a multimodal local model
        (e.g. llama.cpp with mmproj) should override and set
        ``supports_multimodal = True``."""
        from llm.content import to_text_fallback
        text = to_text_fallback(list(content) + list(attachments or []))
        return self.think(task, text, trajectory, tools_description)

    def choose_action(
        self,
        task: str,
        thought: str,
        tools_description: str,
    ) -> Dict[str, Any]:
        system = (
            "You are an action selector. Output exactly one valid JSON object. "
            "No Markdown, no explanation, no code fences, no copied schema text.\n"
            "To call a tool, output: {\"tool\":\"tool_name\",\"params\":{...}}\n"
            "When the task is complete, output: {\"done\":true,\"output\":\"final answer\"}\n"
            "If unsure, use a read-only tool such as list_directory or read_file."
        )
        user = (
            f"Task: {task}\n"
            f"Thought: {thought}\n\n"
            "Available tools. Choose exactly one tool name from this list:\n"
            f"{tools_description}\n\n"
            "Output action JSON now:"
        )
        raw = self._call(system, user, max_tokens=512, temperature=0.1, enable_thinking=False)
        action = parse_llm_json(raw, fallback_done=False)
        if action.get("_parse_error"):
            repair_system = "You repair malformed JSON. Output valid JSON only."
            repair_user = (
                "Repair the following text into action JSON.\n"
                "Valid formats:\n"
                '{"tool":"tool_name","params":{}}\n'
                'or {"done":true,"output":"final answer"}\n\n'
                f"Raw text:\n{raw}"
            )
            repaired = self._call(repair_system, repair_user, max_tokens=256, temperature=0.0, enable_thinking=False)
            action = parse_llm_json(repaired, fallback_done=False)
        return action

    def reflect(self, prompt: str) -> str:
        system = "You are a reflection engine. Extract reusable rules from experience."
        enable_thinking = self._enable_thinking_for_reasoning
        return self._call(system, prompt, max_tokens=2048, enable_thinking=enable_thinking)

    def generate_code(self, prompt: str) -> str:
        system = "You are a code generator. Output code only, without explanation."
        return self._call(system, prompt, max_tokens=2048, temperature=0.1, enable_thinking=False)

    def _build_think_user(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
    ) -> str:
        trajectory_str = self._budget.slice_trajectory(
            trajectory,
            max_steps=self.max_history_steps,
            max_chars_per_step=200,
        )
        omitted = len(trajectory) - self.max_history_steps if len(trajectory) > self.max_history_steps else 0
        prefix = f"[已省略前 {omitted} 步]\n" if omitted > 0 else ""

        lines = [f"任务：{task}", context, tools_description, "请思考下一步。"]
        if trajectory_str:
            lines.append(prefix + trajectory_str)
        return "\n\n".join(lines)
