/**
 * web/app.js — TTMEvolve 桌面 GUI 前端
 *
 * 通过 SSE 与 App Server 通信，渲染 ReAct 事件流，
 * 处理审批弹窗，并在 Command Log 中展示等价的 CLI 命令。
 */

const API_BASE = window.location.origin;

class TTMEvolveGUI {
  constructor() {
    this.sessionId = null;
    this.eventSource = null;
    this.provider = "local";
    this.profile = "default";
    this.pendingApproval = null;

    this.timeline = document.getElementById("timeline");
    this.taskInput = document.getElementById("task-input");
    this.runBtn = document.getElementById("run-btn");
    this.statusText = document.getElementById("status-text");
    this.statusDot = document.getElementById("status-dot");
    this.approvalModal = document.getElementById("approval-modal");
    this.approvalMessage = document.getElementById("approval-message");
    this.approvalAllow = document.getElementById("approval-allow");
    this.approvalDeny = document.getElementById("approval-deny");
    this.commandBody = document.getElementById("command-body");
    this.emptyState = document.getElementById("empty-state");

    this._bindEvents();
    this._detectProvider();
  }

  _bindEvents() {
    this.runBtn.addEventListener("click", () => this._onRun());
    this.taskInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this._onRun();
    });

    this.approvalAllow.addEventListener("click", () => this._respondApproval(true));
    this.approvalDeny.addEventListener("click", () => this._respondApproval(false));

    document.getElementById("toggle-cmd").addEventListener("click", () => {
      document.getElementById("command-log").classList.toggle("collapsed");
    });
  }

  _detectProvider() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("provider")) this.provider = params.get("provider");
    if (params.get("profile")) this.profile = params.get("profile");
  }

  _setStatus(text, state = "ready") {
    this.statusText.textContent = text;
    this.statusDot.className = "dot";
    if (state === "waiting") this.statusDot.classList.add("waiting");
    if (state === "error") this.statusDot.classList.add("error");
  }

  _logCommand(label, command) {
    const entry = document.createElement("div");
    entry.className = "command-entry";
    entry.innerHTML = `
      <div class="command-label">${this._escapeHtml(label)}</div>
      <pre class="command-code">${this._escapeHtml(command)}</pre>
    `;
    this.commandBody.appendChild(entry);
    this.commandBody.scrollTop = this.commandBody.scrollHeight;
  }

  _escapeHtml(text) {
    return String(text)
      .replace(&amp;, "&amp;")
      .replace(<, "&lt;")
      .replace(>, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  _onRun() {
    const task = this.taskInput.value.trim();
    if (!task) return;
    this.startTask(task);
  }

  async startTask(task) {
    if (this.emptyState) {
      this.emptyState.remove();
      this.emptyState = null;
    }

    this._setStatus("运行中", "waiting");
    this.taskInput.value = "";
    this.taskInput.disabled = true;
    this.runBtn.disabled = true;

    this._logCommand(
      "启动任务（等价的 CLI）",
      `python main.py --provider ${this.provider} --profile ${this.profile} ${this._shellQuote(task)}`
    );

    try {
      const resp = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task, provider: this.provider, profile: this.profile }),
      });
      const data = await resp.json();
      if (data.error) {
        throw new Error(data.error);
      }
      this.sessionId = data.session_id;
      this._connectSSE(this.sessionId);
    } catch (err) {
      this._renderError(`创建会话失败：${err.message}`);
      this._setStatus("错误", "error");
      this._unlockInput();
    }
  }

  _connectSSE(sessionId) {
    if (this.eventSource) {
      this.eventSource.close();
    }
    this.eventSource = new EventSource(`${API_BASE}/sessions/${sessionId}/events`);
    this.eventSource.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        this._handleEvent(event);
      } catch (err) {
        console.error("Failed to parse SSE event", err, e.data);
      }
    };
    this.eventSource.onerror = () => {
      this._setStatus("连接中断", "error");
      this._unlockInput();
    };
  }

  _handleEvent(event) {
    const type = event.type;
    const payload = event.payload || {};

    if (type === "approval_request") {
      this._showApproval(payload);
      return;
    }

    if (type === "output" || (type === "status" && payload.done)) {
      this._setStatus("就绪");
      this._unlockInput();
    }

    if (type === "error") {
      this._setStatus("错误", "error");
    }

    this._renderEvent(event);
  }

  _renderEvent(event) {
    const type = event.type;
    const payload = event.payload || {};
    const source = payload.source || event.source || "local";

    const card = document.createElement("div");
    card.className = `event event-${type}`;

    let title = type;
    let body = "";

    switch (type) {
      case "status":
        title = "状态";
        body = this._escapeHtml(payload.message || "");
        break;
      case "thought":
        title = "思考";
        body = this._escapeHtml(payload.thought || "");
        break;
      case "action":
        title = "决策";
        body = `<pre>${this._escapeHtml(JSON.stringify(payload.action, null, 2))}</pre>`;
        break;
      case "tool_call":
        title = "调用工具";
        body = `<div><strong>${this._escapeHtml(payload.tool)}</strong></div>`;
        body += `<pre>${this._escapeHtml(JSON.stringify(payload.params, null, 2))}</pre>`;
        break;
      case "observation": {
        title = "观察结果";
        const ok = payload.observation?.ok;
        if (!ok) card.classList.add("fail");
        body = `<pre>${this._escapeHtml(JSON.stringify(payload.observation, null, 2))}</pre>`;
        break;
      }
      case "output":
        title = "最终结果";
        body = `<pre>${this._escapeHtml(payload.output || "")}</pre>`;
        break;
      case "error":
        title = "错误";
        body = this._escapeHtml(payload.message || "");
        break;
      default:
        body = `<pre>${this._escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
    }

    card.innerHTML = `
      <div class="event-header">
        <span>${this._escapeHtml(title)}</span>
        ${source !== "local" ? `<span class="event-source">${this._escapeHtml(source)}</span>` : ""}
      </div>
      <div class="event-body">${body}</div>
    `;

    this.timeline.appendChild(card);
    this.timeline.scrollTop = this.timeline.scrollHeight;
  }

  _renderError(message) {
    const card = document.createElement("div");
    card.className = "event event-error";
    card.innerHTML = `
      <div class="event-header"><span>前端错误</span></div>
      <div class="event-body">${this._escapeHtml(message)}</div>
    `;
    this.timeline.appendChild(card);
    this.timeline.scrollTop = this.timeline.scrollHeight;
  }

  _showApproval(payload) {
    this.pendingApproval = payload.action_id;
    this.approvalMessage.textContent = payload.message || "Agent 请求执行一个高风险动作。";
    this.approvalModal.classList.remove("hidden");
    this._setStatus("等待审批", "waiting");

    this._logCommand(
      "审批动作（等价的 CLI）",
      `curl -X POST ${API_BASE}/sessions/${this.sessionId}/approve \\\n  -H "Content-Type: application/json" \\\n  -d '{"action_id": "${payload.action_id}", "allowed": true}'`
    );
  }

  async _respondApproval(allowed) {
    if (!this.pendingApproval || !this.sessionId) return;

    this.approvalModal.classList.add("hidden");
    this._setStatus("运行中", "waiting");

    try {
      const resp = await fetch(`${API_BASE}/sessions/${this.sessionId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: this.pendingApproval, allowed }),
      });
      const data = await resp.json();
      if (data.error) {
        throw new Error(data.error);
      }
      this.pendingApproval = null;
    } catch (err) {
      this._renderError(`审批提交失败：${err.message}`);
      this._setStatus("错误", "error");
    }
  }

  _unlockInput() {
    this.taskInput.disabled = false;
    this.runBtn.disabled = false;
    this.taskInput.focus();
  }

  _shellQuote(text) {
    if (/[\s"'\\$|&;<>()]/.test(text)) {
      return `"${text.replace(/"/g, '\\"')}"`;
    }
    return text;
  }
}

// 如果 URL 带有 ?task=... 则自动启动
document.addEventListener("DOMContentLoaded", () => {
  const gui = new TTMEvolveGUI();
  const params = new URLSearchParams(window.location.search);
  const autoTask = params.get("task");
  if (autoTask) {
    setTimeout(() => gui.startTask(autoTask), 300);
  }
  window.ttmGUI = gui;
});
