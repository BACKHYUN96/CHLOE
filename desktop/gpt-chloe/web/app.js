const $ = id => document.getElementById(id);
let state, session = null, busy = false, editing = "memory", toastTimer;
function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}
function notify(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").hidden = true, 5500);
}
async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json", "X-Chloe-Token": state.token},
    body: JSON.stringify(body)
  };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "요청에 실패했어요.");
  return data;
}
function action(label, run, className = "") {
  const button = el("button", className, label);
  button.type = "button";
  button.addEventListener("click", async () => {
    try { await run(); } catch (error) { notify(error.message); }
  });
  return button;
}
function view(name) {
  history.replaceState(null, "", "#" + name);
  document.querySelectorAll(".view").forEach(node => node.hidden = node.id !== "view-" + name);
  document.querySelectorAll(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.view === name));
  $("page-name").textContent = {chat:"대화",memory:"기억",studio:"말투 학습",settings:"API · 설정"}[name];
  if (name === "chat") $("message").focus();
}
function modelDescription() {
  const model = $("model").value;
  $("model-description").textContent = {
    "gpt-6.1-terra": "일상 대화의 속도와 자연스러운 문장을 위한 기본 선택. 추론 없이 바로 답해요.",
    "gpt-6.2-sol": "복잡한 맥락을 더 살펴보고 싶을 때. 낮은 추론 강도로 답해요.",
    "gpt-6-luna": "많이 대화하며 비용을 아끼고 싶을 때. 어려운 문맥은 직접 비교해 보세요."
  }[model];
}
async function refresh() {
  state = await api("/api/state");
  $("model-short").textContent = state.models[state.settings.model].name + " ▾";
  $("key-status").textContent = state.has_key ? "● API 키 등록됨" : "○ API 연결 필요";
  $("key-status").classList.toggle("ready", state.has_key);
  $("usage").textContent = "이 앱 추정 비용 $" + state.usage.cost.toFixed(4);
  $("connection-note").hidden = state.has_key;
  $("key-description").textContent = state.has_key
    ? (state.key_saved ? "API 키가 Windows 계정에 암호화 저장되어 있어요." : "현재 실행에서 API 키를 사용할 수 있어요.")
    : (state.key_warning || "API 키를 연결하면 클로이와 대화할 수 있어요.");
  for (const [key,value] of Object.entries(state.settings)) $(key).value = value;
  modelDescription();
  const list = $("session-list");
  list.replaceChildren();
  for (const row of state.sessions) {
    const button = action(row.title, () => openSession(row.id), "session");
    button.classList.toggle("selected", row.id === session);
    list.append(button);
  }
  renderCards();
}
function renderCards() {
  for (const [type, rows] of [["memory",state.memories],["lesson",state.lessons]]) {
    const list = $(type + "-list");
    list.replaceChildren();
    if (!rows.length) {
      list.append(el("div","empty-card",type === "memory"
        ? "아직 저장한 기억이 없어요.\n내 취향, 자주 하는 일, 기억해 줬으면 하는 사실을 추가해 보세요."
        : "아직 배운 말투가 없어요.\n원하는 표현이나 피하고 싶은 말버릇을 알려 주세요."));
    }
    for (const row of rows) {
      const card = el("article","card");
      card.append(el("h2","",type === "memory" ? row.subject : "말투 피드백"),
                  el("p","",type === "memory" ? row.detail : row.instruction));
      if (row.example_reply) {
        card.append(el("blockquote","","나 · " + row.example_user + "\n클로이 · " + row.example_reply));
      }
      const meta = el("div","card-meta");
      meta.append(el("span","",new Date(row.updated * 1000).toLocaleDateString("ko-KR")));
      const controls = el("div");
      controls.append(action("수정",() => edit(type,row)),action("삭제",async () => {
        if (!confirm("이 항목을 삭제할까요?")) return;
        await api("/api/" + (type === "memory" ? "memories" : "lessons") + "/remove",{id:row.id});
        await refresh();
      }));
      meta.append(controls);card.append(meta);list.append(card);
    }
  }
}
function welcome() {
  $("messages").replaceChildren();
  const box = el("div","welcome");
  box.append(el("div","welcome-symbol","✳"),el("h1","","오늘은 어떤 하루였어?"),
    el("p","","가벼운 수다부터 마음에 남은 이야기까지.\n편하게 말해 줘. 여기서 듣고 있을게."));
  const options = el("div","welcome-options");
  for (const label of ["오늘 하루 이야기할래","너는 어떤 친구야?","그냥 편하게 수다 떨자"]) {
    options.append(action(label,() => {$("message").value = label;$("message").focus();}));
  }
  box.append(options);$("messages").append(box);
}
async function newSession() {
  if (busy) return notify("답변이 끝나면 새 대화를 시작할 수 있어요.");
  session = (await api("/api/sessions",{})).id;
  localStorage.setItem("chloe-session",session);
  await refresh();welcome();view("chat");
}
function addMessage(role, content, question = "") {
  const node = el("article","message " + role);
  node.append(el("div","message-head",role === "assistant" ? "✳ 클로이" : "나"));
  const body = el("div","message-body",content);
  node.append(body);
  const controls = el("div","message-actions");
  if (role === "user") controls.append(action("기억에 추가",()=>edit("memory",{subject:"사용자",detail:content})));
  if (role === "assistant") controls.append(action("말투 피드백",()=>edit("lesson",{example_user:question,example_reply:body.textContent})));
  node.append(controls);$("messages").append(node);
  return {node,body,controls};
}
async function openSession(id) {
  if (busy) return notify("답변이 끝나면 다른 대화를 열 수 있어요.");
  const rows = await api("/api/messages/" + id);
  session = id;localStorage.setItem("chloe-session",session);
  $("messages").replaceChildren();
  if (!rows.length) welcome();
  for (let i=0;i<rows.length;i++) addMessage(rows[i].role,rows[i].content,i ? rows[i-1].content : "");
  await refresh();view("chat");scrollDown();
}
function scrollDown() { $("messages").scrollTop = $("messages").scrollHeight; }
async function sendMessage(message) {
  if (busy || !message.trim()) return;
  if (!state.has_key) { view("settings");$("api-key").focus();return notify("API 키를 연결한 뒤 대화를 시작해 주세요."); }
  if (!session) await newSession();
  busy = true;$("send").disabled = true;$("message").value = "";
  $("messages").querySelector(".welcome")?.remove();
  addMessage("user",message);
  const reply = addMessage("assistant","생각을 정리하고 있어…",message);
  reply.controls.hidden = true;
  scrollDown();
  let started = false, done = false, failure = null;
  try {
    const response = await fetch("/api/chat",{
      method:"POST",headers:{"Content-Type":"application/json","X-Chloe-Token":state.token},
      body:JSON.stringify({session,message,request_id:crypto.randomUUID()})
    });
    if (!response.ok) throw Error("연결에 실패했어요. 앱을 새로고침해 주세요.");
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let pending = "";
    while (true) {
      const chunk = await reader.read();
      pending += decoder.decode(chunk.value || new Uint8Array(),{stream:!chunk.done});
      let index;
      while ((index = pending.indexOf("\n\n")) >= 0) {
        const block = pending.slice(0,index);pending = pending.slice(index+2);
        const dataLine = block.split("\n").find(line=>line.startsWith("data: "));
        const eventLine = block.split("\n").find(line=>line.startsWith("event: "));
        if (!dataLine || !eventLine) continue;
        const data = JSON.parse(dataLine.slice(6)), event = eventLine.slice(7);
        if (event === "delta") {
          if (!started) { reply.body.textContent = "";started = true; }
          reply.body.textContent += data.text;
          scrollDown();
        }
        if (event === "done") {
          done = true;
          reply.controls.append(el("span","", "첫 답변 " + ((data.first_ms||0)/1000).toFixed(1) + "초 · 약 $" + data.cost.toFixed(4)));
        }
        if (event === "error") failure = data.error;
      }
      if (chunk.done) break;
    }
    if (!done) throw Error(failure || "연결이 끊겼어요. 대화를 다시 열어 저장 여부를 확인해 주세요.");
    reply.controls.hidden = false;
  } catch (error) {
    reply.node.classList.add("error");
    reply.body.textContent = error.message;
    $("message").value = message;
    notify("입력한 메시지를 복구했어요. 저장된 대화는 왼쪽에서 다시 확인할 수 있어요.");
  } finally {
    busy = false;$("send").disabled = false;
    try { await refresh(); } catch { notify("PC 서버 연결을 확인해 주세요."); }
    scrollDown();
  }
}
function edit(type,row={}) {
  editing = type;
  $("dialog-title").textContent = type === "memory" ? "기억 알려 주기" : "말투 가르치기";
  $("memory-fields").hidden = type !== "memory";
  $("lesson-fields").hidden = type !== "lesson";
  $("edit-id").value = row.id || "";
  for (const key of ["subject","detail","instruction"]) $(key).value = row[key] || "";
  $("example-user").value = (row.example_user || "").slice(0,500);
  $("example-reply").value = (row.example_reply || "").slice(0,1000);
  $("edit-error").textContent = "";
  $("edit-dialog").showModal();
}
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>view(button.dataset.view)));
$("new-chat").addEventListener("click",()=>newSession().catch(e=>notify(e.message)));
$("model-short").addEventListener("click",()=>view("settings"));
$("setup-link").addEventListener("click",()=>{view("settings");$("api-key").focus();});
$("model").addEventListener("change",modelDescription);
$("add-memory").addEventListener("click",()=>edit("memory"));
$("add-lesson").addEventListener("click",()=>edit("lesson"));
$("close-dialog").addEventListener("click",()=>$("edit-dialog").close());
$("chat-form").addEventListener("submit",event=>{event.preventDefault();sendMessage($("message").value.trim()).catch(e=>notify(e.message));});
$("message").addEventListener("keydown",event=>{
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();$("chat-form").requestSubmit();
  }
});
$("settings-form").addEventListener("submit",async event=>{
  event.preventDefault();
  try {
    await api("/api/settings",Object.fromEntries(["model","register","length","nickname"].map(key=>[key,$(key).value])));
    await refresh();notify("다음 답변부터 새 설정으로 이야기할게요.");
  } catch(e) {notify(e.message);}
});
$("key-form").addEventListener("submit",async event=>{
  event.preventDefault();
  try {
    await api("/api/key",{key:$("api-key").value.trim(),persist:$("persist-key").checked});
    $("api-key").value = "";await refresh();notify("API 키를 저장했어요. 연결 확인 후 대화해 보세요.");
  } catch(e) {notify(e.message);}
});
$("check-key").addEventListener("click",async ()=>{
  $("check-key").disabled = true;$("connection-result").textContent = "연결 확인 중…";
  try {
    const result = await api("/api/key/check",{});
    $("connection-result").textContent = result.available.length
      ? "연결됐어요. 사용 가능한 모델 · " + result.available.map(id=>state.models[id].name).join(", ")
      : "키는 연결됐지만 추천 모델 접근 권한을 확인하지 못했어요.";
  } catch(e) {$("connection-result").textContent = e.message;}
  finally {$("check-key").disabled = false;}
});
$("remove-key").addEventListener("click",async ()=>{
  if (!confirm("등록한 API 키를 이 앱에서 지울까요?")) return;
  try { await api("/api/key/remove",{});await refresh();notify("이 앱에서 API 키를 지웠어요."); } catch(e) {notify(e.message);}
});
$("edit-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const body = {id:$("edit-id").value || undefined};
  if (editing === "memory") Object.assign(body,{subject:$("subject").value,detail:$("detail").value});
  else Object.assign(body,{instruction:$("instruction").value,example_user:$("example-user").value,example_reply:$("example-reply").value});
  try {
    await api("/api/" + (editing === "memory" ? "memories" : "lessons"),body);
    $("edit-dialog").close();await refresh();notify("저장했어요. 다음 대화부터 참고할게요.");
  } catch(e) {$("edit-error").textContent=e.message;}
});
document.querySelectorAll("[data-sample]").forEach(button=>button.addEventListener("click",async ()=>{
  try {
    if (busy) return notify("현재 답변이 끝난 뒤 연습해 주세요.");
    await newSession();$("message").value=button.dataset.sample;
    await sendMessage(button.dataset.sample);
  } catch(e) {notify(e.message);}
}));
(async ()=>{
  const requestedView = location.hash.slice(1);
  await refresh();
  const saved=localStorage.getItem("chloe-session");
  if (state.sessions.some(row=>row.id===saved)) await openSession(saved);
  else if (state.sessions.length) await openSession(state.sessions[0].id);
  else welcome();
  if (["chat", "memory", "studio", "settings"].includes(requestedView)) view(requestedView);
})().catch(()=>notify("PC 서버에 연결하지 못했어요. 실행 파일을 다시 열어 주세요."));
