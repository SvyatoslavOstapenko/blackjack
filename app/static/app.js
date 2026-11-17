"use strict";
const $ = (id) => document.getElementById(id);
const state = { token: sessionStorage.getItem("blackjack-token"), user: null, round: null,
  register: false, busy: false, historyOffset: 0, adminOffset: 0, epoch: 0, requests: new Set() };
const names = { in_progress: "Ваш ход", player_won: "Вы победили", dealer_won: "Победил дилер",
  push: "Ничья", player_blackjack: "Блэкджек! Вы победили", player_bust: "Перебор. Победил дилер", dealer_bust: "У дилера перебор. Вы победили" };
const suits = { S: "♠", H: "♥", D: "♦", C: "♣" };
const number = (value) => Number(value).toLocaleString("ru-RU");
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notice(text) { $("notice").textContent = text; $("notice").hidden = !text; }
function forget() {
  state.epoch += 1;
  for (const request of state.requests) request.abort();
  sessionStorage.removeItem("blackjack-token");
  Object.assign(state, { token: null, user: null, round: null, historyOffset: 0, adminOffset: 0 });
  $("history-list").replaceChildren(); $("admin-list").replaceChildren(); $("admin-rounds").replaceChildren();
  $("admin-rounds").hidden = true;
  updateAccount(); show("table"); renderRound();
}
async function api(path, options = {}) {
  const epoch = state.epoch;
  const guard = () => {
    if (epoch !== state.epoch) {
      const error = new Error("Сеанс изменён"); error.name = "SessionChanged"; throw error;
    }
  };
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const controller = new AbortController(); state.requests.add(controller);
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    let response, data;
    try { response = await fetch(path, { ...options, headers, signal: controller.signal }); }
    catch (error) {
      guard();
      throw new Error(error.name === "AbortError" ? "Время ожидания истекло. Обновите страницу, чтобы проверить результат операции." : "Нет соединения с сервером. Проверьте подключение и обновите страницу, чтобы проверить результат операции.");
    }
    guard();
    try { data = await response.json(); }
    catch { guard(); throw new Error("Сервер вернул неожиданный ответ. Обновите страницу, чтобы проверить результат операции."); }
    guard();
    if (!response.ok) {
      if (response.status === 401 && state.user) forget();
      throw new Error(typeof data.detail === "string" ? data.detail : "Не удалось выполнить запрос. Проверьте введённые данные.");
    }
    return data;
  } finally {
    clearTimeout(timer); state.requests.delete(controller);
  }
}
async function run(action) {
  if (state.busy) return;
  state.busy = true; notice(""); updateControls();
  try { await action(); } catch (error) { if (error.name !== "SessionChanged") notice(error.message); }
  finally { state.busy = false; updateControls(); }
}
function show(view) {
  if ((view === "history" && !state.user) || (view === "admin" && !state.user?.is_admin)) view = "table";
  for (const name of ["table", "history", "leaders", "admin"]) $(`${name}-view`).hidden = name !== view;
  document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
}
function updateAccount() {
  const loggedIn = Boolean(state.user);
  $("account-name").textContent = state.user?.nickname || "Гость";
  $("guest-panel").hidden = loggedIn; $("play-panel").hidden = !loggedIn;
  $("logout").hidden = !loggedIn; $("history-nav").hidden = !loggedIn;
  $("admin-nav").hidden = !state.user?.is_admin;
  $("balance").textContent = number(state.user?.balance || 0);
}
function updateControls() {
  const active = state.round?.status === "in_progress";
  $("start").disabled = state.busy || active || !state.user;
  $("bet").disabled = state.busy || active;
  $("hit").disabled = state.busy || !active;
  $("stand").disabled = state.busy || !active;
  $("auth-submit").disabled = state.busy;
  document.querySelectorAll("[data-bet]").forEach((b) => { b.disabled = active || state.busy; });
}
function renderCards(id, cards, hiddenCard) {
  const parent = $(id); parent.replaceChildren();
  if (!cards?.length) { parent.append(element("span", "", "card placeholder")); return; }
  for (const card of cards) {
    const node = element("div", undefined, `card${["H", "D"].includes(card.suit) ? " red" : ""}`);
    node.setAttribute("aria-label", `${card.rank} ${suits[card.suit]}`);
    node.append(element("span", card.rank), element("span", suits[card.suit])); parent.append(node);
  }
  if (hiddenCard) { const node = element("div", "", "card back"); node.setAttribute("aria-label", "Закрытая карта"); parent.append(node); }
}
function renderRound() {
  const round = state.round; const active = round?.status === "in_progress";
  renderCards("dealer-cards", round?.dealer_cards, active);
  renderCards("player-cards", round?.player_cards, false);
  $("dealer-score").textContent = active ? "?" : round?.dealer_score ?? "—";
  $("player-score").textContent = round?.player_score ?? "—";
  $("round-message").textContent = round ? names[round.status] : "Выберите ставку и начните раздачу";
  $("payout").textContent = !round ? "Ставка списывается в начале раздачи." : active ? `Ставка ${number(round.bet)} фишек принята.` : `Ставка: ${number(round.bet)}. Возвращено: ${number(round.payout)} фишек.`;
  updateControls();
}
async function refreshProfile() { state.user = await api("/me"); updateAccount(); }
function applyRound(round) {
  state.round = round;
  if (state.user && round) {
    state.user.balance = round.balance;
    state.user.rounds_played = round.rounds_played;
    updateAccount();
  }
  renderRound();
}
async function restore() { await refreshProfile(); applyRound(await api("/game/active")); }
function authMode(register) {
  state.register = register; $("register-tab").classList.toggle("selected", register);
  $("login-tab").classList.toggle("selected", !register);
  $("password").minLength = register ? 8 : 1;
  $("password").autocomplete = register ? "new-password" : "current-password";
  $("auth-hint").textContent = register ? "Пароль: 8–128 символов. Начальный баланс — 1000 фишек." : "Введите никнейм и пароль вашей учётной записи.";
  $("auth-submit").textContent = register ? "Создать аккаунт" : "Войти за стол";
}
$("login-tab").onclick = () => authMode(false);
$("register-tab").onclick = () => authMode(true);
$("auth-form").onsubmit = (event) => {
  event.preventDefault();
  run(async () => {
    const credentials = { nickname: $("nickname").value.trim(), password: $("password").value };
    if (state.register) await api("/register", { method: "POST", body: JSON.stringify(credentials) });
    const result = await api("/login", { method: "POST", body: JSON.stringify(credentials) });
    state.token = result.access_token; sessionStorage.setItem("blackjack-token", state.token);
    $("password").value = ""; await restore(); show("table");
  });
};
$("logout").onclick = () => { forget(); notice("Вы вышли из аккаунта в этом браузере."); };
$("rules-button").onclick = () => $("rules").showModal();
document.querySelectorAll("[data-bet]").forEach((b) => { b.onclick = () => { $("bet").value = b.dataset.bet; }; });
$("start").onclick = () => run(async () => {
  const bet = Number($("bet").value);
  if (!Number.isSafeInteger(bet) || bet <= 0 || bet % 2) throw new Error("Введите положительную чётную ставку, например 100.");
  applyRound(await api("/game/start", { method: "POST", body: JSON.stringify({ bet }) }));
});
for (const move of ["hit", "stand"]) $(move).onclick = () => run(async () => {
  applyRound(await api(`/game/${move}`, { method: "POST", body: JSON.stringify({ round_id: state.round.round_id }) }));
});
function table(headers, rows) {
  const wrapper = element("div", undefined, "table-wrap"); const node = element("table");
  const thead = element("thead"); const heading = element("tr");
  headers.forEach((h) => heading.append(element("th", h))); thead.append(heading); node.append(thead);
  const body = element("tbody");
  rows.forEach((cells) => { const row = element("tr"); cells.forEach((content) => {
    const cell = element("td"); if (content instanceof Node) cell.append(content); else cell.textContent = content; row.append(cell);
  }); body.append(row); });
  node.append(body); wrapper.append(node); return wrapper;
}
async function leaders() {
  const rows = await api("/leaderboard"); $("leaders-list").replaceChildren();
  $("leaders-list").append(rows.length ? table(["Место", "Игрок", "Баланс", "Раздач"], rows.map((p, i) => [i + 1, p.nickname, number(p.balance), p.rounds_played])) : element("p", "Пока нет игроков. Станьте первым!", "muted"));
}
function cardText(cards) { return cards.map((c) => `${c.rank}${suits[c.suit]}`).join(" · "); }
function roundEntry(round) {
  const entry = element("details", undefined, "round-entry");
  entry.append(element("summary", `№ ${round.round_id} · ${names[round.status]} · Ставка ${number(round.bet)} · Возврат ${number(round.payout)}`));
  entry.append(element("p", `Ваша рука: ${cardText(round.player_cards)} — ${round.player_score} очков`));
  entry.append(element("p", `Дилер: ${cardText(round.dealer_cards)} — ${round.dealer_score} очков`));
  if (round.started_at) entry.append(element("p", `Начало: ${new Date(round.started_at).toLocaleString("ru-RU", {timeZone: "Europe/Moscow"})} МСК`));
  return entry;
}
async function history() {
  const rows = await api(`/game/rounds?limit=20&offset=${state.historyOffset}`);
  $("history-list").replaceChildren(); rows.forEach((r) => $("history-list").append(roundEntry(r)));
  if (!rows.length) $("history-list").append(element("p", "Завершённых раздач пока нет.", "muted"));
  $("history-prev").disabled = state.historyOffset === 0; $("history-next").disabled = rows.length < 20;
  $("history-page").textContent = `Страница ${state.historyOffset / 20 + 1}`;
}
function actionButton(text, action, danger = false) {
  const button = element("button", text, `secondary${danger ? " danger" : ""}`);
  button.type = "button"; button.onclick = () => run(action); return button;
}
function askAction(title, message, amount = false) {
  const dialog = $("admin-action");
  $("action-title").textContent = title; $("action-message").textContent = message;
  $("action-amount-group").hidden = !amount;
  $("action-amount").disabled = !amount; $("action-amount").required = amount;
  $("action-amount").value = ""; dialog.returnValue = "";
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm" ? (amount ? $("action-amount").value : true) : null), {once:true});
    dialog.showModal();
  });
}
async function adminPlayers() {
  const rows = await api(`/admin/players?limit=20&offset=${state.adminOffset}`);
  $("admin-list").replaceChildren(table(["ID", "Игрок", "Баланс", "Действия"], rows.map((p) => {
    const actions = element("div", undefined, "admin-actions");
    actions.append(actionButton("Начислить", async () => {
      const answer = await askAction("Начисление фишек", `Игрок: ${p.nickname}. Введите положительное целое число.`, true);
      if (answer === null) return; const amount = Number(answer);
      if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error("Начисление должно быть положительным целым числом.");
      await api(`/admin/players/${p.id}/credit`, { method: "POST", body: JSON.stringify({ amount }) });
      await adminPlayers(); await refreshProfile();
    }), actionButton("Сбросить", async () => {
      if (!await askAction("Сброс баланса", `Восстановить баланс игрока «${p.nickname}» до 1000 фишек?`)) return;
      await api(`/admin/players/${p.id}/reset`, { method: "POST" }); await adminPlayers(); await refreshProfile();
    }), actionButton("Раздачи", async () => adminRounds(p)));
    return [p.id, p.nickname + (p.is_admin ? " · администратор" : ""), number(p.balance), actions];
  })));
  $("admin-prev").disabled = state.adminOffset === 0; $("admin-next").disabled = rows.length < 20;
  $("admin-page").textContent = `Страница ${state.adminOffset / 20 + 1}`;
}
async function adminRounds(player, offset = 0) {
  const rows = await api(`/admin/players/${player.id}/rounds?limit=20&offset=${offset}`);
  const panel = $("admin-rounds"); panel.hidden = false; panel.replaceChildren(element("h2", `Раздачи: ${player.nickname}`));
  if (!rows.length) panel.append(element("p", "Нет завершённых раздач.", "muted"));
  for (const round of rows) {
    const entry = roundEntry(round);
    entry.append(actionButton("Удалить ошибочную раздачу", async () => {
      if (!await askAction("Удаление раздачи", `Удалить раздачу № ${round.round_id}? Её ставка и выплата будут отменены, баланс пересчитан.`)) return;
      await api(`/admin/rounds/${round.round_id}`, { method: "DELETE" });
      await adminRounds(player, offset); await adminPlayers(); await refreshProfile();
    }, true)); panel.append(entry);
  }
  const pager = element("div", undefined, "pagination");
  const prev = actionButton("← Назад", () => adminRounds(player, offset - 20)); prev.disabled = offset === 0;
  const next = actionButton("Далее →", () => adminRounds(player, offset + 20)); next.disabled = rows.length < 20;
  pager.append(prev, element("span", `Страница ${offset / 20 + 1}`), next); panel.append(pager);
}
document.querySelectorAll("[data-view]").forEach((b) => { b.onclick = () => run(async () => {
  const view = b.dataset.view; show(view);
  if (view === "leaders") await leaders(); if (view === "history") await history(); if (view === "admin") await adminPlayers();
}); });
$("refresh-leaders").onclick = () => run(leaders); $("refresh-history").onclick = () => run(history);
$("refresh-admin").onclick = () => run(adminPlayers);
$("history-prev").onclick = () => run(async () => { state.historyOffset = Math.max(0, state.historyOffset - 20); await history(); });
$("history-next").onclick = () => run(async () => { state.historyOffset += 20; await history(); });
$("admin-prev").onclick = () => run(async () => { state.adminOffset = Math.max(0, state.adminOffset - 20); await adminPlayers(); });
$("admin-next").onclick = () => run(async () => { state.adminOffset += 20; await adminPlayers(); });
async function connection() {
  try { await api("/health"); $("connection").textContent = "● Сервер и база доступны"; }
  catch { $("connection").textContent = "○ Сервер или база недоступны"; }
}
run(async () => { await connection(); if (state.token) {
  try { await restore(); } catch (error) { forget(); throw error; }
} });
