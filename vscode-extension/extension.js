// 개인 비서 대시보드 — VSCode 안 탭 담당 (아주 작게: 판단은 엔진이 한다).
// 10초마다 엔진에 '이 VSCode 창이 살아 있음'을 알리고, 엔진이 열라고 하면 Simple Browser 탭으로 대시보드를 연다.
// 엔진이 꺼져 있으면 아무것도 하지 않는다.
const vscode = require("vscode");

const EVERY = 10 * 1000;
const ID = Math.random().toString(36).slice(2, 10);  // 이 VSCode 창의 id (여러 창이면 엔진이 한 창에만 열라고 함)

function base() {
  const u = vscode.workspace.getConfiguration("paDashboard").get("url") || "http://localhost:8765/";
  return u.endsWith("/") ? u : u + "/";
}

function show() {
  return vscode.commands.executeCommand("simpleBrowser.show", base());
}

async function poll() {
  try {
    const r = await fetch(base() + "api/vscode?w=" + ID, { cache: "no-store" });
    if (!r.ok) return;
    const j = await r.json();
    if (j.open) await show();
  } catch (e) { /* 엔진 꺼짐 — 조용히 다음 번에 */ }
}

function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand("paDashboard.open", show));
  poll();
  const t = setInterval(poll, EVERY);
  context.subscriptions.push({ dispose: () => clearInterval(t) });
}

function deactivate() {}

module.exports = { activate, deactivate };
