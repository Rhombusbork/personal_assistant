// 개인 비서 대시보드 — VSCode 안 탭 담당 (작게: 판단은 엔진이 한다).
// - 비서 폴더(엔진이 도는 폴더)를 연 창: 처음 한 번 대시보드 탭을 자동으로 연다. 이미 탭이 있으면(복원 등) 그대로.
// - 어느 창이든: 탭 줄 오른쪽 위 버튼 · 아래 상태 줄 '비서' · Ctrl+Alt+D 로 연다. 닫아도 다시 열지 않는다.
// - 엔진이 꺼져 있을 때 누르면: 비서 폴더 창이면 '비서: 자동 감시' 작업으로 켠 뒤 연다.
// - 10초마다 엔진에 '이 창이 살아 있음' + 이 창의 폴더를 알린다 (bin/pa open 요청은 비서 폴더 창이 가져감).
const vscode = require("vscode");

const EVERY = 10 * 1000;
const AUTO_WINDOW = 3 * 60 * 1000;  // 창을 연 뒤 이 안에 엔진이 응답하면 자동으로 연다 (늦게 켜진 엔진이 갑자기 탭을 띄우지 않게)
const ENGINE_TASK = "비서: 자동 감시";
const ID = Math.random().toString(36).slice(2, 10);  // 이 VSCode 창의 id
const started = Date.now();
let bar, autoPending = true, home = false;

function base() {
  const u = vscode.workspace.getConfiguration("paDashboard").get("url") || "http://localhost:8765/";
  return u.endsWith("/") ? u : u + "/";
}

const folders = () => (vscode.workspace.workspaceFolders || []).map(f => f.uri.path);

function hasTab() {  // 이 창에 Simple Browser 탭(대시보드)이 이미 있나
  return vscode.window.tabGroups.all.some(g => g.tabs.some(t =>
    t.input instanceof vscode.TabInputWebview && /simpleBrowser/i.test(t.input.viewType)));
}

function show() {  // Simple Browser 는 창마다 탭 하나를 다시 쓴다 (있으면 그 탭을 앞으로)
  return vscode.commands.executeCommand("simpleBrowser.show", base());
}

async function ping() {
  try {
    const r = await fetch(base() + "api/vscode?w=" + ID + "&f=" + encodeURIComponent(JSON.stringify(folders())), { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;  // 엔진 꺼짐
  }
}

function setBar(state) {
  bar.text = { on: "$(checklist) 비서", off: "$(circle-slash) 비서", starting: "$(sync~spin) 비서" }[state];
  bar.tooltip = { on: "비서 대시보드 열기 (Ctrl+Alt+D)", off: "비서 엔진이 꺼져 있음 — 눌러서 켜고 열기", starting: "비서 엔진을 켜는 중…" }[state];
}

async function poll() {
  const j = await ping();
  if (!j) {
    if (!bar.text.includes("sync")) setBar("off");
    return;
  }
  setBar("on");
  home = !!j.home;
  if (autoPending) {
    autoPending = false;
    const auto = vscode.workspace.getConfiguration("paDashboard").get("autoOpen", true);
    if (auto && home && Date.now() - started < AUTO_WINDOW && !hasTab()) await show();
  }
  if (j.open) await show();
}

async function startEngine() {
  try {
    const t = (await vscode.tasks.fetchTasks()).find(x => x.name === ENGINE_TASK);
    if (!t) return false;
    await vscode.tasks.executeTask(t);
    return true;
  } catch (e) {
    return false;
  }
}

async function open() {
  if (await ping()) return show();
  if (!(await startEngine())) {
    vscode.window.showWarningMessage("비서 엔진이 꺼져 있어요 — 비서 폴더 창에서 Ctrl+Shift+P → 작업 실행 → '" + ENGINE_TASK + "'");
    return;
  }
  setBar("starting");
  for (let i = 0; i < 90; i++) {  // 엔진 서버가 뜰 때까지 (보통 몇 초)
    await new Promise(r => setTimeout(r, 1000));
    if (await ping()) { setBar("on"); return show(); }
  }
  setBar("off");
  vscode.window.showWarningMessage("엔진을 켰지만 아직 응답이 없어요 — 잠시 뒤 다시 눌러 주세요 (아래 터미널 '" + ENGINE_TASK + "' 참고)");
}

function activate(context) {
  bar = vscode.window.createStatusBarItem("paDashboard.status", vscode.StatusBarAlignment.Right, 100);
  bar.name = "비서 대시보드";
  bar.command = "paDashboard.open";
  setBar("off");
  bar.show();
  context.subscriptions.push(bar, vscode.commands.registerCommand("paDashboard.open", open));
  poll();
  const t = setInterval(poll, EVERY);
  context.subscriptions.push({ dispose: () => clearInterval(t) });
}

function deactivate() {}

module.exports = { activate, deactivate };
