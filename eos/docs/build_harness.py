"""Regenerate docs/harness.html — the EOS harness inspector.

    python docs/build_harness.py    # run from the eos/ directory

Runs the harness (rule-based baseline operator) and embeds the replayable
transcript into a single self-contained HTML file with three inspector views —
Systems, Help Desk, Operator — plus a Korean/English toggle and a play/scrub
transport. The browser only *replays* the Python run; it never re-implements
the simulation.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eos.harness.evaluator import baseline_factory, run_scenario

noprev = run_scenario(baseline_factory(False), with_transcript=False).ehs
res = run_scenario(baseline_factory(True), seed=7, ticks=240, ehs_noprev=noprev)
DATA = res.transcript

HTML = r"""<title>EOS — Harness Inspector</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root{
    color-scheme: light dark;
    --plane:#eef1f4; --surface:#ffffff; --surface-2:#f4f7f9; --inset:#e9eef2;
    --ink:#16202b; --ink-2:#47586a; --muted:#7c8b99;
    --hair:rgba(16,32,48,.11); --hair-2:rgba(16,32,48,.06);
    --accent:#0f8f86; --accent-ink:#0b6b64; --accent-soft:rgba(15,143,134,.12);
    --good:#0ca30c; --warn:#c98500; --serious:#d1622f; --crit:#c9332f;
    --shadow:0 1px 2px rgba(16,32,48,.06), 0 10px 28px rgba(16,32,48,.06);
    --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  }
  :root[data-theme="dark"],
  :root:where(:not([data-theme="light"])){}
  @media (prefers-color-scheme: dark){
    :root:where(:not([data-theme="light"])){
      --plane:#0b1118; --surface:#121c26; --surface-2:#0f1a24; --inset:#0d1620;
      --ink:#e8eef4; --ink-2:#9db0c1; --muted:#657888;
      --hair:rgba(255,255,255,.10); --hair-2:rgba(255,255,255,.05);
      --accent:#2bc0b2; --accent-ink:#7fe3d9; --accent-soft:rgba(43,192,178,.15);
      --good:#22b551; --warn:#e0a52a; --serious:#e88a52; --crit:#e35550;
      --shadow:0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.4);
    }
  }
  :root[data-theme="dark"]{
    --plane:#0b1118; --surface:#121c26; --surface-2:#0f1a24; --inset:#0d1620;
    --ink:#e8eef4; --ink-2:#9db0c1; --muted:#657888;
    --hair:rgba(255,255,255,.10); --hair-2:rgba(255,255,255,.05);
    --accent:#2bc0b2; --accent-ink:#7fe3d9; --accent-soft:rgba(43,192,178,.15);
    --good:#22b551; --warn:#e0a52a; --serious:#e88a52; --crit:#e35550;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.4);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--plane);color:var(--ink);font-family:var(--sans);line-height:1.5;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1200px;margin:0 auto;padding:20px 20px 60px}
  button{font-family:inherit;cursor:pointer}
  .mono{font-family:var(--mono);font-variant-numeric:tabular-nums}

  /* header */
  header{display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding-bottom:16px;
    border-bottom:1px solid var(--hair);margin-bottom:16px}
  .mark{width:36px;height:36px;border-radius:9px;flex:none;position:relative;
    background:linear-gradient(150deg,var(--accent),color-mix(in oklab,var(--accent),#000 32%))}
  .mark::before{content:"";position:absolute;left:8px;right:8px;top:10px;height:2px;border-radius:2px;
    background:var(--surface);opacity:.9;box-shadow:0 6px 0 var(--surface),0 12px 0 var(--surface)}
  h1{font-size:17px;margin:0;font-weight:650;letter-spacing:-.01em}
  .tagline{font-size:12px;color:var(--ink-2);margin-top:1px}
  .h-right{margin-left:auto;display:flex;align-items:center;gap:10px}
  .ehs-badge{display:flex;flex-direction:column;align-items:flex-end;line-height:1.1}
  .ehs-badge .n{font-family:var(--mono);font-size:22px;font-weight:650}
  .ehs-badge .l{font-size:10px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
  .lang{display:inline-flex;border:1px solid var(--hair);border-radius:999px;overflow:hidden;background:var(--surface)}
  .lang button{border:0;background:transparent;color:var(--ink-2);padding:6px 12px;font-size:12px;font-weight:600}
  .lang button[aria-pressed="true"]{background:var(--accent);color:#fff}

  .oper-note{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-2);
    background:var(--accent-soft);border:1px solid color-mix(in oklab,var(--accent) 30%,transparent);
    border-radius:10px;padding:7px 12px;margin-bottom:14px}
  .oper-note b{color:var(--accent-ink)}
  .oper-note .pulse{width:8px;height:8px;border-radius:50%;background:var(--accent);flex:none}

  /* transport */
  .transport{display:flex;flex-wrap:wrap;align-items:center;gap:14px;background:var(--surface);
    border:1px solid var(--hair);border-radius:13px;padding:12px 16px;margin-bottom:14px;box-shadow:var(--shadow)}
  .play{width:40px;height:40px;border-radius:10px;border:0;background:var(--accent);color:#fff;
    font-size:15px;display:flex;align-items:center;justify-content:center;flex:none}
  .clockbox{min-width:150px}
  .clockbox .t{font-family:var(--mono);font-size:15px;font-weight:650}
  .clockbox .p{font-size:11px;color:var(--ink-2)}
  .scrub{flex:1;min-width:200px;display:flex;flex-direction:column;gap:3px}
  input[type=range]{width:100%;accent-color:var(--accent);height:22px}
  .scrub .ends{display:flex;justify-content:space-between;font-size:10px;color:var(--muted)}
  .speeds{display:inline-flex;gap:4px}
  .speeds button{border:1px solid var(--hair);background:var(--surface-2);color:var(--ink-2);
    border-radius:7px;padding:5px 9px;font-size:11px;font-weight:600}
  .speeds button[aria-pressed="true"]{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
  .loadpill{font-size:11px;color:var(--ink-2);background:var(--inset);border-radius:999px;padding:5px 11px}
  .loadpill b{font-family:var(--mono);color:var(--ink)}

  /* tabs */
  nav.tabs{display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap}
  nav.tabs button{border:1px solid var(--hair);background:var(--surface);color:var(--ink-2);
    padding:9px 16px;border-radius:10px;font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px}
  nav.tabs button[aria-pressed="true"]{background:var(--ink);color:var(--plane);border-color:var(--ink)}
  nav.tabs .cnt{font-family:var(--mono);font-size:11px;opacity:.7}

  .card{background:var(--surface);border:1px solid var(--hair);border-radius:14px;box-shadow:var(--shadow)}
  .eyebrow{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 4px}

  /* systems grid */
  .sysgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
  .sys{padding:13px 14px;text-align:left;border:1px solid var(--hair);background:var(--surface);
    border-radius:13px;box-shadow:var(--shadow);position:relative;overflow:hidden;transition:transform .1s}
  .sys:hover{transform:translateY(-2px)}
  .sys .stripe{position:absolute;left:0;top:0;bottom:0;width:4px}
  .sys .row1{display:flex;align-items:center;justify-content:space-between;gap:8px}
  .sys .nm{font-weight:640;font-size:13.5px}
  .sys .sid{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
  .statepill{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:6px;letter-spacing:.02em}
  .sys .lchip{display:inline-block;margin-top:3px;font-size:10px;font-weight:600;color:var(--accent);
    background:var(--accent-soft);border-radius:5px;padding:1px 7px}
  .metrics{margin-top:11px;display:grid;grid-template-columns:1fr 1fr;gap:6px 12px}
  .met{font-size:10.5px}
  .met .k{color:var(--muted);display:flex;justify-content:space-between}
  .met .k b{color:var(--ink);font-family:var(--mono)}
  .met .bar{height:4px;border-radius:3px;background:var(--inset);margin-top:2px;overflow:hidden}
  .met .bar i{display:block;height:100%;border-radius:3px}
  .sys .inc{margin-top:10px;font-size:11px;color:var(--crit);display:flex;align-items:center;gap:6px}
  .sys .inc .d{width:7px;height:7px;border-radius:50%;background:var(--crit)}

  /* screen modal */
  .scrim{position:fixed;inset:0;background:rgba(6,12,18,.55);display:none;align-items:center;
    justify-content:center;padding:20px;z-index:40;backdrop-filter:blur(2px)}
  .scrim.on{display:flex}
  .screen{width:min(720px,96vw);max-height:90vh;overflow:auto;background:var(--surface);
    border:1px solid var(--hair);border-radius:16px;box-shadow:0 30px 80px rgba(0,0,0,.4)}
  .screen-top{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--hair);
    position:sticky;top:0;background:var(--surface)}
  .screen-top .dots{display:flex;gap:6px}.screen-top .dots i{width:11px;height:11px;border-radius:50%;display:block}
  .screen-top .title{font-weight:650;font-size:13.5px}
  .screen-top .url{font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:4px}
  .screen-top .x{margin-left:auto;border:0;background:var(--inset);width:28px;height:28px;border-radius:8px;
    color:var(--ink-2);font-size:15px}
  .banner{padding:11px 16px;font-size:13px;font-weight:600;display:flex;align-items:center;gap:9px}
  .app-body{padding:16px}
  .app-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
  .app-toolbar .tb{font-size:11px;padding:6px 11px;border-radius:7px;background:var(--surface-2);
    border:1px solid var(--hair);color:var(--ink-2)}
  .app-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  .tile{background:var(--surface-2);border:1px solid var(--hair);border-radius:10px;padding:11px 12px}
  .tile .k{font-size:10.5px;color:var(--muted)}
  .tile .v{font-family:var(--mono);font-size:19px;font-weight:640;margin-top:2px}
  .skeleton{height:9px;border-radius:5px;background:linear-gradient(90deg,var(--inset),var(--surface-2),var(--inset));
    margin:9px 0}
  .down-msg{text-align:center;padding:26px 16px;color:var(--crit);font-weight:600}

  /* help desk */
  .desk{display:grid;grid-template-columns:300px 1fr;gap:14px}
  .ticketlist{max-height:560px;overflow:auto;display:flex;flex-direction:column;gap:8px;padding:2px}
  .tk{width:100%;text-align:left;border:1px solid var(--hair);background:var(--surface);border-radius:11px;
    padding:10px 12px}
  .tk[aria-pressed="true"]{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
  .tk .r1{display:flex;align-items:center;gap:7px;margin-bottom:3px}
  .typechip{font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:5px;letter-spacing:.03em}
  .prio{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--muted)}
  .tk .sm{font-size:12px;color:var(--ink);line-height:1.35}
  .tk .mtline{font-size:10.5px;color:var(--muted);margin-top:4px;display:flex;justify-content:space-between}
  .conv{display:flex;flex-direction:column;min-height:420px}
  .conv-head{padding:12px 15px;border-bottom:1px solid var(--hair);display:flex;align-items:center;gap:9px}
  .conv-head .cid{font-family:var(--mono);font-size:11px;color:var(--muted)}
  .stream{flex:1;overflow:auto;max-height:430px;padding:15px;display:flex;flex-direction:column;gap:11px}
  .msg{display:flex;gap:9px;max-width:82%}
  .msg .av{width:27px;height:27px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
    font-size:11px;font-weight:700;color:#fff}
  .msg .bub{background:var(--surface-2);border:1px solid var(--hair);border-radius:12px;padding:8px 12px;font-size:12.5px}
  .msg .who{font-size:10px;color:var(--muted);margin-bottom:2px}
  .msg.sys{align-self:center;max-width:92%}
  .msg.sys .bub{background:var(--accent-soft);border-color:transparent;color:var(--accent-ink);font-size:11.5px;text-align:center}
  .msg.op{align-self:flex-end;flex-direction:row-reverse}
  .msg.op .bub{background:var(--ink);color:var(--plane);border-color:transparent}
  .msg.resolved .bub{background:color-mix(in oklab,var(--good) 16%,transparent);border-color:transparent;color:var(--ink)}
  .composer{border-top:1px solid var(--hair);padding:11px 13px;display:flex;flex-direction:column;gap:8px}
  .composer .row{display:flex;gap:8px}
  .composer select,.composer input,.actionpanel select{font-family:inherit;font-size:12px;padding:8px 10px;
    border:1px solid var(--hair);border-radius:9px;background:var(--surface-2);color:var(--ink)}
  .composer input{flex:1}
  .composer .send{border:0;background:var(--accent);color:#fff;border-radius:9px;padding:8px 15px;font-weight:600;font-size:12px}
  .whatif{font-size:10.5px;color:var(--muted);display:flex;align-items:center;gap:6px}

  /* operator */
  .oper{display:grid;grid-template-columns:1fr 320px;gap:14px}
  .feed{max-height:560px;overflow:auto;display:flex;flex-direction:column;gap:8px;padding:2px}
  .ev{border:1px solid var(--hair);background:var(--surface);border-radius:11px;padding:10px 13px;
    display:grid;grid-template-columns:46px 1fr auto;gap:10px;align-items:center}
  .ev .tt{font-family:var(--mono);font-size:11px;color:var(--muted)}
  .ev .act b{font-size:12.5px}
  .ev .act .diag{font-size:11px;color:var(--ink-2);margin-top:2px}
  .ev .out{font-size:10.5px;font-weight:700;padding:3px 8px;border-radius:6px;white-space:nowrap}
  .ev.prev{border-left:3px solid var(--accent)}
  .actionpanel{align-self:start;position:sticky;top:10px}
  .actionpanel .body{padding:15px}
  .actionpanel h3{margin:0 0 4px;font-size:14px}
  .actionpanel p.sub{margin:0 0 12px;font-size:11.5px;color:var(--ink-2)}
  .actionpanel label{font-size:11px;color:var(--muted);display:block;margin:9px 0 3px}
  .actionpanel select{width:100%}
  .actionpanel .queue{border:0;background:var(--ink);color:var(--plane);width:100%;border-radius:9px;
    padding:10px;font-weight:600;font-size:12.5px;margin-top:14px}
  .pending{margin-top:12px;display:flex;flex-direction:column;gap:6px}
  .pending .pi{font-size:11px;background:var(--surface-2);border:1px dashed var(--hair);border-radius:8px;
    padding:7px 10px;display:flex;justify-content:space-between;gap:8px}

  .subgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:9px;margin-top:14px}
  .subtile{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:10px 12px}
  .subtile .k{font-size:10.5px;color:var(--ink-2)}
  .subtile .v{font-family:var(--mono);font-size:18px;font-weight:640}
  .subtile .mb{height:4px;border-radius:3px;background:var(--inset);margin-top:6px;overflow:hidden}
  .subtile .mb i{display:block;height:100%}

  footer{margin-top:26px;padding-top:16px;border-top:1px solid var(--hair);font-size:11.5px;color:var(--muted);
    display:flex;flex-wrap:wrap;gap:6px 14px}
  .hidden{display:none!important}
  @media (max-width:860px){.desk{grid-template-columns:1fr}.oper{grid-template-columns:1fr}}
  @media (prefers-reduced-motion: reduce){*{transition:none!important}}
</style>

<div class="wrap">
  <header>
    <div class="mark" aria-hidden="true"></div>
    <div>
      <h1 id="ttl"></h1>
      <div class="tagline" id="tag"></div>
    </div>
    <div class="h-right">
      <div class="ehs-badge"><span class="n mono" id="ehsN">0</span><span class="l" id="ehsL">EHS</span></div>
      <div class="lang" role="group" aria-label="language">
        <button id="ko" aria-pressed="true">한국어</button>
        <button id="en" aria-pressed="false">EN</button>
      </div>
    </div>
  </header>

  <div class="oper-note">
    <span class="pulse" aria-hidden="true"></span>
    <span id="operNote"></span>
  </div>

  <div class="transport">
    <button class="play" id="playBtn" aria-label="play">▶</button>
    <div class="clockbox"><div class="t mono" id="clockT">D1 00:00</div><div class="p" id="clockP"></div></div>
    <div class="scrub">
      <input type="range" id="range" min="0" value="0" step="1">
      <div class="ends"><span id="e0">tick 0</span><span id="e1"></span></div>
    </div>
    <div class="speeds" id="speeds"></div>
    <div class="loadpill" id="loadpill"></div>
  </div>

  <nav class="tabs" id="tabs"></nav>

  <section id="view-systems"></section>
  <section id="view-desk" class="hidden"></section>
  <section id="view-oper" class="hidden"></section>

  <footer id="foot"></footer>
</div>

<div class="scrim" id="scrim"><div class="screen" id="screenBox"></div></div>

<script>
const DATA = /*__DATA__*/;
/* ---------------- i18n ---------------- */
const STR = {
  ko:{
    title:"EOS — 하네스 인스펙터", tag:"가상 엔터프라이즈 운영자 평가 하네스 · Phase 1",
    ehs:"기업 건강 점수", operNote:(op)=>`운영자: <b>${op}</b> (룰 기반 AI 베이스라인) · 사람이 직접 개입할 수도 있습니다`,
    tabs:{systems:"시스템", desk:"헬프데스크", oper:"운영자"},
    play:"재생", pause:"일시정지", tick:"틱", load:"부하",
    state:{up:"정상",degraded:"지연",down:"장애"},
    layer:{web:"웹",application:"애플리케이션",database:"데이터베이스",integration:"연계(EAI)",
      infrastructure:"인프라",observability:"관측",security:"보안"},
    metric:{cpu:"CPU",mem:"메모리",disk:"디스크",latency_ms:"응답",error_rate:"오류율",queue:"큐"},
    activeIncident:"활성 장애", noIncident:"장애 없음",
    screenOf:(n)=>`${n} — 가상 화면`, clickHint:"카드를 클릭하면 실제 가상 화면이 열립니다",
    bannerUp:"서비스 정상 — 모든 기능 사용 가능",
    bannerDeg:"서비스 지연 — 응답이 느리거나 일부 기능 불안정",
    bannerDown:"서비스 장애 — 현재 접속/처리가 불가합니다",
    downMsg:"⚠ 시스템에 연결할 수 없습니다. 운영자가 복구 중입니다.",
    ticketTypes:{incident:"인시던트",service_request:"서비스요청",change_request:"변경요청"},
    symptom:{cannot_connect:"접속이 안 됩니다",backlog:"처리가 계속 밀립니다",save_fails:"저장이 안 됩니다",
      crashes:"자꾸 멈춥니다",slow:"너무 느립니다"},
    request:{access_request:"접근 권한을 요청합니다",report_request:"신규 리포트를 요청합니다",
      password_reset:"비밀번호 초기화를 요청합니다",data_extract:"데이터 추출을 요청합니다",
      account_unlock:"계정 잠금 해제를 요청합니다",schedule_change:"배치 스케줄 변경을 요청합니다",
      config_change:"설정 변경을 요청합니다",new_user:"신규 사용자 등록을 요청합니다",
      capacity_upgrade:"용량 증설을 요청합니다"},
    action:{restart:"재시작",rolling_restart:"롤링 재시작",scale_out:"스케일 아웃",increase_heap:"힙 증설",
      increase_connection_pool:"커넥션 풀 증설",clear_cache:"캐시 정리",flush_queue:"큐 비우기",
      renew_certificate:"인증서 갱신",kill_slow_query:"슬로우 쿼리 종료",reindex:"인덱스 재구성",
      cleanup_logs:"로그 정리",add_disk:"디스크 증설",restart_worker:"워커 재시작",failover:"페일오버",patch:"패치"},
    fault:{memory_leak:"메모리 누수",jvm_oom:"JVM OOM",queue_overflow:"큐 오버플로우",ssl_expired:"인증서 만료",
      worker_down:"워커 다운",slow_query:"슬로우 쿼리",network_delay:"네트워크 지연",ec2_failure:"EC2 장애",
      disk_full:"디스크 풀",api_timeout:"API 타임아웃",db_lock:"DB 락",index_fragmentation:"인덱스 단편화"},
    phase:{night:"야간",morning:"출근",business:"업무",lunch:"점심",evening:"퇴근"},
    role:{"Planner":"플래너","Maintenance Engineer":"정비 엔지니어","Supervisor":"수퍼바이저","Buyer":"구매담당",
      "Manager":"매니저","Approver":"승인자","Accountant":"회계담당","Controller":"컨트롤러","Auditor":"감사담당",
      "Inventory Clerk":"자재담당","Procurement Lead":"구매리드","Safety Officer":"안전담당","Field Inspector":"현장점검원",
      "Data Scientist":"데이터과학자","Ops Engineer":"운영엔지니어","Sales Ops":"영업운영","Plant Scheduler":"생산계획"},
    helpdesk:"헬프데스크", you:"나(사용자)", operator:"운영자",
    classified:(t,p,a)=>`분류됨 · ${t} · 우선순위 P${p} · 담당 ${a} 배정`,
    diagnosing:(d)=>`원인 진단: ${d}`,
    acting:(a)=>`조치 실행: ${a}`,
    rcaOk:"진단 정확", rcaNo:"진단 오류", recOk:"복구 성공", recNo:"복구 실패",
    resolvedMsg:"해결됨 — 서비스 정상화",
    reqAssigned:(a)=>`접수됨 · 담당 ${a} 배정`,
    reqResolved:"처리 완료",
    convEmpty:"왼쪽에서 티켓을 선택하세요.",
    composerPh:"요청을 입력하세요 (예: SAP 로그인이 안됩니다)", send:"보내기",
    composerSys:"대상 시스템", whatif:"입력 시 헬프데스크 분류 규칙을 미리보기로 보여줍니다 (재생 데이터에는 반영되지 않음)",
    guessInc:"인시던트", guessSR:"서비스요청",
    feedTitle:"운영자 액션 피드", preventive:"예방", reactive:"대응",
    vs:(g,a)=>`진단 ${g} · 실제 ${a}`,
    manualTitle:"사람 개입 (수동 조치)", manualSub:"사람 운영자가 직접 조치를 큐에 넣습니다. 재생 모드에서는 예시(what-if)입니다.",
    mSystem:"시스템", mAction:"조치", mQueue:"조치 큐에 추가", noPending:"대기 중 조치 없음",
    subTitle:"KPI 세부 (최종)", weightsNote:"EHS는 10개 KPI의 가중 합",
    subs:{availability:"가용성",sla:"SLA",mttr:"MTTR",recovery:"복구율",rca:"원인분석",automation:"자동화",
      user:"사용자만족",cost:"비용효율",token:"토큰효율",preventive:"예방정비"},
    footer:["결정론적 · 시드 7 · 순수 파이썬 하네스","브라우저는 파이썬 실행 기록을 재생만 함 (로직 재구현 없음)",
      "python docs/build_harness.py 로 재생성"],
    openTickets:"열림", incidents:"인시던트",
  },
  en:{
    title:"EOS — Harness Inspector", tag:"Operator-evaluation harness for a virtual enterprise · Phase 1",
    ehs:"Enterprise Health Score", operNote:(op)=>`Operator: <b>${op}</b> (rule-based AI baseline) · a human can also step in`,
    tabs:{systems:"Systems", desk:"Help Desk", oper:"Operator"},
    play:"Play", pause:"Pause", tick:"tick", load:"load",
    state:{up:"UP",degraded:"DEGRADED",down:"DOWN"},
    layer:{web:"Web",application:"Application",database:"Database",integration:"Integration",
      infrastructure:"Infra",observability:"Observability",security:"Security"},
    metric:{cpu:"CPU",mem:"Memory",disk:"Disk",latency_ms:"Latency",error_rate:"Error rate",queue:"Queue"},
    activeIncident:"Active incident", noIncident:"No incident",
    screenOf:(n)=>`${n} — virtual screen`, clickHint:"Click a card to open its live virtual screen",
    bannerUp:"Service healthy — all functions available",
    bannerDeg:"Service degraded — slow responses or unstable features",
    bannerDown:"Service down — access/processing currently unavailable",
    downMsg:"⚠ Cannot reach the system. The operator is recovering it.",
    ticketTypes:{incident:"Incident",service_request:"Service req.",change_request:"Change req."},
    symptom:{cannot_connect:"I can't connect",backlog:"requests keep backing up",save_fails:"saves are failing",
      crashes:"it keeps freezing",slow:"it's very slow"},
    request:{access_request:"requesting access",report_request:"requesting a new report",
      password_reset:"requesting a password reset",data_extract:"requesting a data extract",
      account_unlock:"requesting an account unlock",schedule_change:"requesting a batch schedule change",
      config_change:"requesting a config change",new_user:"requesting a new user account",
      capacity_upgrade:"requesting a capacity upgrade"},
    action:{restart:"Restart",rolling_restart:"Rolling restart",scale_out:"Scale out",increase_heap:"Increase heap",
      increase_connection_pool:"Increase pool",clear_cache:"Clear cache",flush_queue:"Flush queue",
      renew_certificate:"Renew cert",kill_slow_query:"Kill slow query",reindex:"Reindex",
      cleanup_logs:"Cleanup logs",add_disk:"Add disk",restart_worker:"Restart worker",failover:"Failover",patch:"Patch"},
    fault:{memory_leak:"Memory leak",jvm_oom:"JVM OOM",queue_overflow:"Queue overflow",ssl_expired:"SSL expired",
      worker_down:"Worker down",slow_query:"Slow query",network_delay:"Network delay",ec2_failure:"EC2 failure",
      disk_full:"Disk full",api_timeout:"API timeout",db_lock:"DB lock",index_fragmentation:"Index fragmentation"},
    phase:{night:"Night",morning:"Morning",business:"Business",lunch:"Lunch",evening:"Evening"},
    role:{}, // fall back to raw English role
    helpdesk:"Help Desk", you:"You (user)", operator:"Operator",
    classified:(t,p,a)=>`Classified · ${t} · Priority P${p} · Assigned to ${a}`,
    diagnosing:(d)=>`Root-cause analysis: diagnosed as ${d}`,
    acting:(a)=>`Executing action: ${a}`,
    rcaOk:"RCA correct", rcaNo:"RCA wrong", recOk:"Recovered", recNo:"Recovery failed",
    resolvedMsg:"Resolved — service restored",
    reqAssigned:(a)=>`Received · assigned to ${a}`,
    reqResolved:"Completed",
    convEmpty:"Select a ticket on the left.",
    composerPh:"Type a request (e.g. I can't log in to SAP)", send:"Send",
    composerSys:"Target system", whatif:"Previews the help-desk classification rules; not written back to the replay data",
    guessInc:"Incident", guessSR:"Service req.",
    feedTitle:"Operator action feed", preventive:"Preventive", reactive:"Reactive",
    vs:(g,a)=>`diagnosed ${g} · actual ${a}`,
    manualTitle:"Human intervention (manual action)", manualSub:"A human operator queues an action directly. In replay this is a what-if.",
    mSystem:"System", mAction:"Action", mQueue:"Add to action queue", noPending:"No pending actions",
    subTitle:"KPI breakdown (final)", weightsNote:"EHS is the weighted sum of 10 KPIs",
    subs:{availability:"Availability",sla:"SLA",mttr:"MTTR",recovery:"Recovery",rca:"RCA",automation:"Automation",
      user:"User sat.",cost:"Cost",token:"Token",preventive:"Preventive"},
    footer:["Deterministic · seed 7 · pure-Python harness","The browser only replays the Python run (no logic re-implemented)",
      "Regenerate with python docs/build_harness.py"],
    openTickets:"open", incidents:"incidents",
  }
};

/* ---------------- state ---------------- */
let L="ko", T=0, playing=false, speed=6, timer=null, view="systems", selTicket=null;
const TMAX=DATA.metrics.length-1;
const playBtn=document.getElementById("playBtn");
const screenBox=document.getElementById("screenBox");
const pending=[];
const sysById={}; DATA.systems.forEach((s,i)=>sysById[s.id]={...s,i});
const opsByTick={}; DATA.ops.forEach(e=>{(opsByTick[e.t]=opsByTick[e.t]||[]).push(e)});
function tr(){return STR[L];}
function roleT(r){return (tr().role[r])||r;}
function stName(code){return tr().state[["up","degraded","down"][code]];}
function stColor(code){return ["var(--good)","var(--warn)","var(--crit)"][code];}

/* clock ported from time_engine (pure fn of tick) */
function clock(t){
  const TPD=48, m=(t%TPD)*30, day=Math.floor(t/TPD), hour=Math.floor(m/60);
  const dom=(day%30)+1;
  let phase = (hour<7||hour>=20)?"night":(hour<9)?"morning":(hour>=12&&hour<13)?"lunch":(hour>=17)?"evening":"business";
  let base={night:.15,morning:.8,business:1,lunch:.5,evening:.7}[phase];
  const monthEnd=dom>=28;
  if(monthEnd && phase!=="night" && phase!=="lunch") base*=1.6;
  return {day:day+1,hour,min:m%60,phase,load:Math.round(base*100)/100,monthEnd};
}
function incidentAt(sys,t){
  return DATA.incidents.find(x=>x.sys===sys && x.start<=t && t<x.end) || null;
}

/* ---------------- rendering ---------------- */
function setLang(l){L=l;ko.setAttribute("aria-pressed",l==="ko");en.setAttribute("aria-pressed",l==="en");renderAll();}
function renderAll(){
  const s=tr();
  ttl.textContent=s.title; tag.textContent=s.tag; ehsL.textContent=s.ehs;
  operNote.innerHTML=s.operNote(DATA.meta.operator);
  e0.textContent=`${s.tick} 0`; e1.textContent=`${s.tick} ${TMAX}`;
  renderTabs(); renderSpeeds(); renderTransport();
  drawView();
  foot.innerHTML=s.footer.map(x=>`<span>${x}</span>`).join('<span style="opacity:.4">•</span>');
}
function renderTabs(){
  const s=tr();
  const openT=DATA.tickets.filter(t=>t.open<=T && !(t.resolved!==null&&t.resolved<T)).length;
  const cfg=[["systems",s.tabs.systems,DATA.systems.length],["desk",s.tabs.desk,openT],
    ["oper",s.tabs.oper,(opsByTick[T]||[]).length?"●":""]];
  tabs.innerHTML=cfg.map(([k,label,cnt])=>
    `<button data-tab="${k}" aria-pressed="${view===k}">${label}<span class="cnt">${cnt}</span></button>`).join("");
  tabs.querySelectorAll("button").forEach(b=>b.onclick=()=>{view=b.dataset.tab;syncViews();drawView();renderTabs();});
}
function renderSpeeds(){
  speeds.innerHTML=[1,3,6,12].map(x=>`<button data-sp="${x}" aria-pressed="${speed===x}">${x}×</button>`).join("");
  speeds.querySelectorAll("button").forEach(b=>b.onclick=()=>{speed=+b.dataset.sp;if(playing){pause();play();}renderSpeeds();});
}
function renderTransport(){
  const c=clock(T),s=tr();
  clockT.textContent=`D${c.day} ${String(c.hour).padStart(2,"0")}:${String(c.min).padStart(2,"0")}`;
  clockP.textContent=s.phase[c.phase]+(c.monthEnd?" · "+(L==="ko"?"월말":"month-end"):"");
  loadpill.innerHTML=`${s.load} <b>${c.load.toFixed(2)}×</b>`;
  ehsN.textContent=(DATA.ehs[T]??DATA.meta.ehs).toFixed(1);
  ehsN.style.color=stColorForEhs(DATA.ehs[T]??DATA.meta.ehs);
  range.max=TMAX; range.value=T;
  playBtn.textContent=playing?"⏸":"▶"; playBtn.setAttribute("aria-label",playing?s.pause:s.play);
}
function stColorForEhs(v){return v>=75?"var(--good)":v>=55?"var(--warn)":v>=40?"var(--serious)":"var(--crit)";}

function syncViews(){
  document.getElementById("view-systems").classList.toggle("hidden",view!=="systems");
  document.getElementById("view-desk").classList.toggle("hidden",view!=="desk");
  document.getElementById("view-oper").classList.toggle("hidden",view!=="oper");
}
function drawView(){ syncViews(); if(view==="systems")drawSystems(); else if(view==="desk")drawDesk(); else drawOper(); }

/* ----- systems view ----- */
function metBar(code,label,val,pct,color){
  return `<div class="met"><div class="k">${label}<b>${val}</b></div>
    <div class="bar"><i style="width:${Math.min(100,pct)}%;background:${color}"></i></div></div>`;
}
function drawSystems(){
  const s=tr(), rows=DATA.metrics[T];
  const cards=DATA.systems.map((sy,i)=>{
    const m=rows[i]; const [st,cpu,mem,disk,lat,err,q]=m;
    const inc=incidentAt(sy.id,T);
    const col=stColor(st);
    const mets=
      metBar("cpu",s.metric.cpu,cpu+"%",cpu,cpu>80?"var(--crit)":"var(--accent)")+
      metBar("mem",s.metric.mem,mem+"%",mem,mem>85?"var(--crit)":"var(--accent)")+
      metBar("disk",s.metric.disk,disk+"%",disk,disk>88?"var(--crit)":"var(--accent)")+
      metBar("lat",s.metric.latency_ms,lat+"ms",Math.min(100,lat/12),lat>800?"var(--warn)":"var(--accent)");
    return `<button class="sys" data-i="${i}">
      <span class="stripe" style="background:${col}"></span>
      <div class="row1"><div><div class="nm">${sy.name}</div><div class="sid">${sy.id}</div></div>
        <span class="statepill" style="color:${col};background:color-mix(in oklab,${col} 15%,transparent)">${stName(st)}</span></div>
      <span class="lchip">${s.layer[sy.layer]}</span>
      <div class="metrics">${mets}</div>
      ${inc?`<div class="inc"><span class="d"></span>${s.activeIncident}</div>`:""}
    </button>`;
  }).join("");
  document.getElementById("view-systems").innerHTML=
    `<p class="eyebrow">${s.clickHint}</p><div class="sysgrid">${cards}</div>`;
  document.querySelectorAll(".sys").forEach(b=>b.onclick=()=>openScreen(+b.dataset.i));
}
function openScreen(i){
  const s=tr(), sy=DATA.systems[i], m=DATA.metrics[T][i];
  const [st,cpu,mem,disk,lat,err,q]=m; const inc=incidentAt(sy.id,T);
  const col=stColor(st);
  const bannerTxt=st===0?s.bannerUp:st===1?s.bannerDeg:s.bannerDown;
  const dots=["#ff5f57","#febc2e","#28c840"].map(c=>`<i style="background:${c}"></i>`).join("");
  let body;
  if(st===2){
    body=`<div class="down-msg">${s.downMsg}</div>`;
  }else{
    const tiles=[[s.metric.cpu,cpu+" %"],[s.metric.mem,mem+" %"],[s.metric.disk,disk+" %"],
      [s.metric.latency_ms,lat+" ms"],[s.metric.error_rate,(err*100).toFixed(1)+" %"],[s.metric.queue,q]]
      .map(([k,v])=>`<div class="tile"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
    body=`<div class="app-toolbar">
        <span class="tb">${sy.stack||sy.layer}</span><span class="tb">${s.layer[sy.layer]}</span>
        <span class="tb">${L==="ko"?"인스턴스":"instances"} ×${2}</span></div>
      ${st===1?`<div class="skeleton"></div><div class="skeleton" style="width:70%"></div>`:""}
      <div class="app-grid">${tiles}</div>`;
  }
  screenBox.innerHTML=`
    <div class="screen-top"><div class="dots">${dots}</div>
      <span class="title">${s.screenOf(sy.name)}</span>
      <span class="url">https://${sy.id}.corp.local</span>
      <button class="x" id="closeScreen">✕</button></div>
    <div class="banner" style="background:color-mix(in oklab,${col} 14%,transparent);color:${col}">
      <span style="width:9px;height:9px;border-radius:50%;background:${col};display:inline-block"></span>${bannerTxt}
      ${inc?` · <span style="color:var(--ink-2)">${s.activeIncident}</span>`:""}</div>
    <div class="app-body">${body}</div>`;
  scrim.classList.add("on");
  document.getElementById("closeScreen").onclick=closeScreen;
}
function closeScreen(){scrim.classList.remove("on");}

/* ----- help desk view ----- */
function visibleTickets(){
  return DATA.tickets.filter(t=>t.open<=T).sort((a,b)=>b.open-a.open);
}
function drawDesk(){
  const s=tr(), list=visibleTickets();
  const items=list.map(t=>{
    const resolved=t.resolved!==null && t.resolved<=T;
    const tc=typeChip(t.type);
    const sysName=sysById[t.sys].name;
    const line=t.type==="incident"?`${roleT(t.role)}: ${sysName} ${s.symptom[t.symptom]}`
      :`${roleT(t.role)}: ${sysName} — ${s.request[t.request]}`;
    return `<button class="tk" data-id="${t.id}" aria-pressed="${selTicket===t.id}">
      <div class="r1">${tc}<span class="prio">P${t.prio}</span>
        <span style="margin-left:auto;font-size:10px;color:${resolved?"var(--good)":"var(--warn)"};font-weight:700">
        ${resolved?"●":"○"}</span></div>
      <div class="sm">${line}</div>
      <div class="mtline"><span>${t.id}</span><span>D${clock(t.open).day} ${String(clock(t.open).hour).padStart(2,"0")}:${String(clock(t.open).min).padStart(2,"0")}</span></div>
    </button>`;
  }).join("") || `<div style="padding:20px;color:var(--muted);font-size:12px">${s.convEmpty}</div>`;

  if(!selTicket && list.length) selTicket=list[0].id;
  document.getElementById("view-desk").innerHTML=`
    <div class="desk">
      <div class="ticketlist">${items}</div>
      <div class="card conv" id="conv"></div>
    </div>`;
  document.querySelectorAll(".tk").forEach(b=>b.onclick=()=>{selTicket=b.dataset.id;drawDesk();});
  drawConv();
}
function typeChip(type){
  const s=tr();
  const c={incident:"var(--crit)",service_request:"var(--accent)",change_request:"var(--serious)"}[type];
  return `<span class="typechip" style="color:${c};background:color-mix(in oklab,${c} 15%,transparent)">${s.ticketTypes[type]}</span>`;
}
function drawConv(){
  const s=tr(), conv=document.getElementById("conv");
  const t=DATA.tickets.find(x=>x.id===selTicket);
  if(!t){conv.innerHTML=`<div class="stream"><div style="margin:auto;color:var(--muted)">${s.convEmpty}</div></div>`;composer(conv);return;}
  const sysName=sysById[t.sys].name;
  const userMsg=t.type==="incident"?`${sysName} ${s.symptom[t.symptom]}`:`${sysName} — ${s.request[t.request]}`;
  const msgs=[];
  msgs.push(bubble("user",roleT(t.role),userMsg,"var(--serious)"));
  // helpdesk classification
  if(t.type==="incident"){
    msgs.push(bubbleSys(s.classified(s.ticketTypes[t.type],t.prio,t.assignee||DATA.meta.operator)));
    // operator work for this system between open and resolved
    const evs=DATA.ops.filter(e=>e.sys===t.sys && e.t>=t.open && e.t<=T && (t.resolved===null||e.t<=t.resolved) && !e.preventive);
    evs.forEach(e=>{
      msgs.push(bubble("op",s.operator,`${s.diagnosing(s.fault[e.diag]||e.diag)} → ${s.acting(s.action[e.action])}`,"var(--ink)"));
    });
    if(t.resolved!==null && t.resolved<=T) msgs.push(bubbleResolved(s.resolvedMsg));
  }else{
    if(t.assignee) msgs.push(bubbleSys(s.reqAssigned(t.assignee)));
    if(t.resolved!==null && t.resolved<=T) msgs.push(bubbleResolved(s.reqResolved));
  }
  conv.innerHTML=`
    <div class="conv-head">${typeChip(t.type)}<span class="cid mono">${t.id}</span>
      <span style="font-size:12px;color:var(--ink-2)">${sysName}</span></div>
    <div class="stream">${msgs.join("")}</div>`;
  composer(conv);
  const st=conv.querySelector(".stream"); if(st) st.scrollTop=st.scrollHeight;
}
function bubble(kind,who,text,color){
  const init=who.slice(0,1);
  return `<div class="msg ${kind}"><div class="av" style="background:${color}">${init}</div>
    <div><div class="who">${who}</div><div class="bub">${text}</div></div></div>`;
}
function bubbleSys(text){return `<div class="msg sys"><div class="bub">🛈 ${text}</div></div>`;}
function bubbleResolved(text){return `<div class="msg resolved" style="align-self:center"><div class="bub">✓ ${text}</div></div>`;}
function composer(conv){
  const s=tr();
  const opts=DATA.systems.map(sy=>`<option value="${sy.id}">${sy.name}</option>`).join("");
  const el=document.createElement("div");
  el.className="composer";
  el.innerHTML=`
    <div class="row"><select id="cSys">${opts}</select>
      <input id="cText" placeholder="${s.composerPh}"></div>
    <div class="row"><button class="send" id="cSend">${s.send}</button>
      <span class="whatif">🛈 ${s.whatif}</span></div>
    <div id="cResult"></div>`;
  conv.appendChild(el);
  document.getElementById("cSend").onclick=()=>{
    const txt=document.getElementById("cText").value.trim(); if(!txt)return;
    const sysId=document.getElementById("cSys").value;
    const cls=classify(txt);
    document.getElementById("cResult").innerHTML=
      `<div class="msg sys" style="margin-top:8px"><div class="bub">🛈 ${s.classified(cls.type,cls.prio,DATA.meta.operator)}</div></div>`;
  };
}
function classify(txt){
  const s=tr(); const low=txt.toLowerCase();
  const incidentWords=["안","안됨","안돼","느","오류","장애","실패","멈","죽","error","slow","down","fail","can't","cannot","crash"];
  const urgentWords=["긴급","장애","안됩니","down","urgent","critical"];
  const isInc=incidentWords.some(w=>low.includes(w));
  const prio=urgentWords.some(w=>low.includes(w))?1:isInc?2:3;
  return {type:isInc?s.guessInc:s.guessSR,prio};
}

/* ----- operator view ----- */
function drawOper(){
  const s=tr();
  const evs=DATA.ops.filter(e=>e.t<=T).sort((a,b)=>b.t-a.t);
  const feed=evs.map(e=>{
    const c=clock(e.t);
    const actual=e.actual?(s.fault[e.actual]||e.actual):"—";
    let out,outc;
    if(e.preventive){out=s.preventive;outc="var(--accent)";}
    else if(e.resolved){out=s.recOk;outc="var(--good)";}
    else if(e.recovery===false){out=s.recNo;outc="var(--crit)";}
    else {out=s.reactive;outc="var(--muted)";}
    const diag=e.preventive?"":`<div class="diag">${s.vs(s.fault[e.diag]||e.diag,actual)} · ${e.rca_correct?s.rcaOk:e.rca_correct===false?s.rcaNo:""}</div>`;
    return `<div class="ev ${e.preventive?'prev':''}">
      <div class="tt">D${c.day}<br>${String(c.hour).padStart(2,"0")}:${String(c.min).padStart(2,"0")}</div>
      <div class="act"><b>${sysById[e.sys].name}</b> · ${s.action[e.action]||e.action}${diag}</div>
      <div class="out" style="color:${outc};background:color-mix(in oklab,${outc} 14%,transparent)">${out}</div>
    </div>`;
  }).join("") || `<div style="padding:20px;color:var(--muted);font-size:12px">${L==="ko"?"아직 액션이 없습니다.":"No actions yet."}</div>`;

  const sysOpts=DATA.systems.map(sy=>`<option value="${sy.id}">${sy.name}</option>`).join("");
  const actOpts=Object.keys(s.action).map(a=>`<option value="${a}">${s.action[a]}</option>`).join("");
  const pend=pending.length?pending.map((p,i)=>
    `<div class="pi"><span>${sysById[p.sys].name} · ${s.action[p.act]}</span><span style="color:var(--muted)">what-if</span></div>`).join("")
    :`<div class="pi" style="justify-content:center;color:var(--muted)">${s.noPending}</div>`;

  const subs=DATA.subscores;
  const subTiles=Object.keys(s.subs).map(k=>{
    const v=subs[k]; const col=v>=75?"var(--good)":v>=55?"var(--warn)":v>=40?"var(--serious)":"var(--crit)";
    return `<div class="subtile"><div class="k">${s.subs[k]}</div><div class="v" style="color:${col}">${v.toFixed(1)}</div>
      <div class="mb"><i style="width:${v}%;background:${col}"></i></div></div>`;
  }).join("");

  document.getElementById("view-oper").innerHTML=`
    <div class="oper">
      <div>
        <p class="eyebrow">${s.feedTitle}</p>
        <div class="feed">${feed}</div>
      </div>
      <div class="card actionpanel"><div class="body">
        <h3>${s.manualTitle}</h3><p class="sub">${s.manualSub}</p>
        <label>${s.mSystem}</label><select id="mSys">${sysOpts}</select>
        <label>${s.mAction}</label><select id="mAct">${actOpts}</select>
        <button class="queue" id="mQueue">${s.mQueue}</button>
        <div class="pending">${pend}</div>
      </div></div>
    </div>
    <p class="eyebrow" style="margin-top:18px">${s.subTitle} · ${s.weightsNote}</p>
    <div class="subgrid">${subTiles}</div>`;
  document.getElementById("mQueue").onclick=()=>{
    pending.unshift({sys:document.getElementById("mSys").value,act:document.getElementById("mAct").value});
    drawOper();
  };
}

/* ---------------- transport control ---------------- */
function play(){playing=true;const ms=Math.max(60,700/speed);
  timer=setInterval(()=>{if(T>=TMAX){pause();return;}T++;onTick();},ms);renderTransport();}
function pause(){playing=false;if(timer)clearInterval(timer);timer=null;renderTransport();}
function onTick(){renderTransport();renderTabs();
  if(view==="systems")drawSystems(); else if(view==="desk")drawDesk(); else drawOper();}

playBtn.onclick=()=>playing?pause():play();
range.oninput=e=>{T=+e.target.value;if(playing)pause();onTick();};
ko.onclick=()=>setLang("ko"); en.onclick=()=>setLang("en");
scrim.onclick=e=>{if(e.target===scrim)closeScreen();};
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeScreen();
  if(e.key===" "){e.preventDefault();playing?pause():play();}});

renderAll();
</script>
"""

out = HTML.replace("/*__DATA__*/", json.dumps(DATA, separators=(",", ":")))
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness.html")
with open(path, "w") as f:
    f.write(out)
print("wrote", path, len(out), "bytes | EHS", DATA["meta"]["ehs"],
      "| tickets", len(DATA["tickets"]), "| ops", len(DATA["ops"]))
