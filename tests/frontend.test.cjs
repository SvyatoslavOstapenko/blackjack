const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

// Изолированная DOM-модель для асинхронных ответов, без браузера и настоящей БД.
class Element {
  constructor() {
    Object.assign(this, {textContent:"", hidden:false, disabled:false, value:"", children:[], dataset:{}});
    this.classList = {toggle(){}};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
}
const response = (data) => ({ok:true,status:200,json:async()=>data});
const flush = () => new Promise(setImmediate);
async function createPage() {
  const nodes = new Map(), stored = new Map(), requests = [], timers = new Map();
  let nextTimer = 0;
  const context = vm.createContext({
    document:{ getElementById(id){if(!nodes.has(id)) nodes.set(id,new Element());return nodes.get(id);},
      querySelectorAll(){return [];}, createElement(){return new Element();}},
    sessionStorage:{getItem:(key)=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:(key)=>stored.delete(key)},
    Node:Element, AbortController,
    setTimeout(fn){const id=++nextTimer;timers.set(id,fn);return id;},
    clearTimeout(id){timers.delete(id);},
    fetch:async(url)=>{requests.push(url);return response({status:"ok"});},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,"../app/static/app.js"),"utf8"),context);
  await flush();
  return {context,nodes,requests,timers,run:(code)=>vm.runInContext(code,context)};
}

test("Ответ старого сеанса не возвращает пользователя после выхода", async()=>{
  const page=await createPage(); let finish;
  page.context.fetch=()=>new Promise(resolve=>{finish=resolve;});
  page.run('state.user={nickname:"old",balance:1000};state.token="test-token";updateAccount()');
  const pending=page.run("refreshProfile()");
  page.run("forget()");
  finish(response({nickname:"old",balance:1000,is_admin:true}));
  await assert.rejects(pending,{name:"SessionChanged"});
  assert.equal(page.nodes.get("account-name").textContent,"Гость");
  assert.equal(page.nodes.get("admin-nav").hidden,true);
  assert.equal(page.nodes.get("guest-panel").hidden,false);
});

test("Ответ HTML вместо JSON даёт понятную ошибку без текста парсера",async()=>{
  const page=await createPage();
  page.context.fetch=async()=>({ok:false,status:502,json:async()=>{throw new SyntaxError("Unexpected token <");}});
  await assert.rejects(page.run('api("/leaderboard")'), /неожиданный ответ/);
});

test("Истёкшее ожидание не повторяет изменяющий запрос",async()=>{
  const page=await createPage();let calls=0;
  page.context.fetch=(_url,options)=>new Promise((_resolve,reject)=>{
    calls++;options.signal.addEventListener("abort",()=>{const error=new Error();error.name="AbortError";reject(error);});
  });
  const pending=page.run('api("/game/start",{method:"POST"})');
  assert.equal(page.timers.size,1);
  [...page.timers.values()][0]();
  await assert.rejects(pending,/Время ожидания истекло/);
  assert.equal(calls,1);
});

test("Карты и баланс отображаются из успешного ответа без дополнительного /me",async()=>{
  const page=await createPage();page.requests.length=0;
  page.run('state.user={nickname:"player",balance:1000};state.token="test-token";updateAccount()');
  page.nodes.get("bet").value="100";
  page.context.fetch=async(url)=>{
    page.requests.push(url);
    if(url!=="/game/start") throw new Error("Profile unavailable");
    return response({round_id:1,status:"in_progress",balance:900,rounds_played:0,bet:100,payout:null,
      dealer_cards:[{rank:"9",suit:"H"}],player_cards:[{rank:"K",suit:"S"},{rank:"7",suit:"D"}],player_score:17,dealer_score:null});
  };
  await page.nodes.get("start").onclick();
  assert.deepEqual(page.requests,["/game/start"]);
  assert.equal(page.nodes.get("balance").textContent,"900");
  assert.equal(page.nodes.get("player-cards").children.length,2);
  assert.equal(page.nodes.get("hit").disabled,false);
});

test("Запоздавший ответ после выхода не заменяет сообщение об окончании сеанса",async()=>{
  const page=await createPage();let finish;
  page.context.fetch=()=>new Promise(resolve=>{finish=resolve;});
  page.run('state.user={nickname:"old",balance:1000};updateAccount()');
  const pending=page.run("run(refreshProfile)");
  page.run('forget();notice("Вы вышли из аккаунта")');
  finish(response({nickname:"old",balance:1000}));
  await pending;
  assert.equal(page.nodes.get("notice").textContent,"Вы вышли из аккаунта");
});
