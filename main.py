import os
import re
import json
import time
import csv
import io
from datetime import datetime, timezone, timedelta
from collections import Counter
import requests
import urllib.request
from playwright.sync_api import sync_playwright

API_KEY = os.environ.get("NEXON_API_KEY", "").strip()
HEADERS = {"x-nxopen-api-key": API_KEY}
BASE_URL = "https://open.api.nexon.com/fconline/v1"
SHEET_ID = "1LbMwTdfLRB45dqH1pLbk2vrTXPf6vu7DvqAWCgLMeDM"
BASE_DOMAIN = "https://wiseplay.kr"

KST = timezone(timedelta(hours=9))
TODAY_STR = datetime.now(KST).strftime("%Y-%m-%d")

# [전문가 직접 검증] 포메이션별 고유 실전 빌드업 메커니즘
TACTICAL_BLUEPRINTS = {
    "4-2-2-1-1": [
        "롱패스를 통한 사이드 전환 및 하프스페이스 뒷공간 공략",
        "풀백과 윙어의 유기적인 지원을 통한 크로스, 컷백 연계 및 박스 안 마무리"
    ],
    "4-2-3-1": [
        "CAM 중심의 빠른 역습 전개 및 LAM·RAM의 침투를 통한 박스 타격",
        "2선 윙포워드가 창출한 측면 공간으로 풀백이 오버래핑하여 크로스 및 컷백 연계"
    ],
    "4-2-2-2": [
        "투톱 연계를 활용한 빠른 템포의 카운터 어택 및 상대 센터백 라인 붕괴",
        "측면 배치에 따른 분기: LM·RM의 다이렉트 사이드 전환, LAM·RAM의 풀백 연계 컷백 플레이"
    ],
    "4-1-4-1": [
        "촘촘한 미드필더 라인을 바탕으로 한 안정적인 수비 밸런스 및 지공 빌드업",
        "2선 미드필더 전진을 통해 상대 4백을 상대로 공격 5명을 형성하는 수적 우위 전개"
    ],
    "4-1-2-3": [
        "4-1-4-1 대비 안정감은 다소 낮으나, 3톱을 활용해 훨씬 빠르고 파괴적인 직선 역습 전개",
        "중앙 미드필더의 침투를 더해 상대 4백을 무너뜨리는 최전방 5인 수적 우위 공략"
    ]
}

SPID_META = {}
def get_spid_metadata():
    global SPID_META
    try:
        res = requests.get("https://open.api.nexon.com/static/fconline/meta/spid.json", timeout=10)
        if res.status_code == 200:
            for item in res.json():
                SPID_META[item["id"]] = item["name"]
    except Exception:
        pass

# 주요 인기 랭커 선수 영문/현지명 즉시 매핑 사전
KNOWN_PLAYER_NAMES = {
    "주앙 네베스": {"en": "João Neves", "vi": "João Neves", "th": "โชเอา เนเวส"},
    "우스만 뎀벨레": {"en": "O. Dembélé", "vi": "O. Dembélé", "th": "อุสมาน เดมเบเล่"},
    "크바라츠헬리아": {"en": "Kvaratskhelia", "vi": "Kvaratskhelia", "th": "ควารัตสเคเลีย"},
    "누누 멘데스": {"en": "Nuno Mendes", "vi": "Nuno Mendes", "th": "นูโน เมนเดส"},
    "사뮈엘 에토": {"en": "Samuel Eto'o", "vi": "Samuel Eto'o", "th": "ซามูเอล เอโต้"},
    "마르틴 카세레스": {"en": "Martín Cáceres", "vi": "Martín Cáceres", "th": "มาร์ติน กาเซเรส"},
    "호나우두": {"en": "Ronaldo", "vi": "Ronaldo", "th": "โรนัลโด้"},
    "굴리트": {"en": "R. Gullit", "vi": "R. Gullit", "th": "รุด กุลลิท"},
    "호나우지뉴": {"en": "Ronaldinho", "vi": "Ronaldinho", "th": "โรนัลดินโญ่"},
    "로드리": {"en": "Rodri", "vi": "Rodri", "th": "โรดรี้"},
    "반데이크": {"en": "V. van Dijk", "vi": "V. van Dijk", "th": "เฟอร์จิล ฟาน ไดจ์ค"},
    "손흥민": {"en": "Son Heung-min", "vi": "Son Heung-min", "th": "ซน ฮึง-มิน"}
}

def translate_player_server_side(kor_name):
    """서버 사이드에서 4개국어 선수명 객체 생성"""
    if kor_name in KNOWN_PLAYER_NAMES:
        item = KNOWN_PLAYER_NAMES[kor_name]
        return {"ko": kor_name, "en": item["en"], "vi": item["vi"], "th": item["th"]}

    res_dict = {"ko": kor_name, "en": kor_name, "vi": kor_name, "th": kor_name}
    for lang in ["en", "vi", "th"]:
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl={lang}&dt=t&q={kor_name}"
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                res_dict[lang] = r.json()[0][0][0]
        except Exception:
            res_dict[lang] = kor_name
    return res_dict

def fetch_real_squad_players(nickname):
    if not API_KEY:
        return {}

    try:
        id_res = requests.get(f"{BASE_URL}/id?nickname={nickname}", headers=HEADERS, timeout=5)
        if id_res.status_code != 200:
            return {}
        ouid = id_res.json().get("ouid")
        if not ouid:
            return {}

        matches_res = requests.get(f"{BASE_URL}/user/match?ouid={ouid}&matchtype=50&offset=0&limit=1", headers=HEADERS, timeout=5)
        if matches_res.status_code != 200:
            return {}
        match_ids = matches_res.json()
        if not match_ids:
            return {}

        detail_res = requests.get(f"{BASE_URL}/match-detail?matchid={match_ids[0]}", headers=HEADERS, timeout=5)
        if detail_res.status_code != 200:
            return {}
        
        detail_data = detail_res.json()
        match_info = detail_data.get("matchInfo", [])
        target_info = next((m for m in match_info if m.get("ouid") == ouid), match_info[0] if match_info else None)
        if not target_info:
            return {}

        players = target_info.get("player", [])
        starting_players = [p for p in players if p.get("spPosition") != 28]

        extracted = {}
        for p in starting_players:
            pos_id = p.get("spPosition")
            sp_id = p.get("spId")
            p_name = SPID_META.get(sp_id, f"ID:{sp_id}")

            if pos_id in [20, 21, 24, 25] and "ST" not in extracted:
                extracted["ST"] = translate_player_server_side(p_name)
            elif pos_id in [12, 13, 14, 15, 16, 17, 18, 19] and "MID" not in extracted:
                extracted["MID"] = translate_player_server_side(p_name)
            elif pos_id in [9, 10, 11] and "CDM" not in extracted:
                extracted["CDM"] = translate_player_server_side(p_name)
            elif pos_id in [4, 5, 6, 7] and "CB" not in extracted:
                extracted["CB"] = translate_player_server_side(p_name)

        return extracted
    except Exception:
        return {}

def collect_real_top100_playwright():
    print("[1/3] 넥슨 데이터센터 순위표 실시간 1~100위 수집 중...")
    ranker_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        page.goto("https://fconline.nexon.com/datacenter/rank", wait_until="networkidle", timeout=60000)
        time.sleep(3)

        for page_num in range(1, 6):
            if page_num > 1:
                clicked = False
                selectors = [
                    f".pagination a:has-text('{page_num}')",
                    f".paginate a:has-text('{page_num}')",
                    f".paging a:has-text('{page_num}')"
                ]
                for sel in selectors:
                    try:
                        elem = page.query_selector(sel)
                        if elem and elem.is_visible():
                            elem.click()
                            clicked = True
                            break
                    except Exception:
                        pass
                if not clicked:
                    page.evaluate(f"window.GetRankList && window.GetRankList(50, {page_num})")
                time.sleep(3.5)

            extracted_items = page.evaluate("""() => {
                const results = [];
                const rows = document.querySelectorAll('tbody tr, .rank_list .tr, .tbody .tr, tr');
                rows.forEach(row => {
                    const text = row.innerText || '';
                    const formMatch = text.match(/\\b(\\d(?:-\\d){2,4})\\b/);
                    if (!formMatch) return;
                    
                    let formStr = formMatch[1];
                    if (formStr === '4-2-2-1') formStr = '4-2-2-1-1';

                    let nickname = '';
                    const linkElem = row.querySelector('a[href*="profile"], a[onclick*="Profile"], .coach_name, .name, .profile_pointer');
                    if (linkElem) {
                        nickname = linkElem.innerText.trim();
                    } else {
                        const tokens = text.split(/\\s+/);
                        for (let t of tokens) {
                            if (t.length >= 2 && !t.match(/^\\d+$/) && !['슈퍼챔피언스','챔피언스','상세보기','포메이션','승률'].includes(t) && !t.includes('%')) {
                                nickname = t;
                                break;
                            }
                        }
                    }
                    if (nickname && nickname.length >= 2) {
                        results.push({ nickname: nickname, formation: formStr });
                    }
                });
                return results;
            }""")

            for item in extracted_items:
                nick = item["nickname"]
                form = item["formation"]
                if not any(r["nickname"] == nick for r in ranker_data):
                    ranker_data.append({"nickname": nick, "formation": form})

        browser.close()

    print(f"  => 랭커 100명 전수 수집 완료: 총 {len(ranker_data)}명")
    return ranker_data

def process_and_save():
    get_spid_metadata()

    rankers = collect_real_top100_playwright()
    if not rankers:
        print("[오류] 랭커 수집 실패")
        return

    total_valid = len(rankers)
    formation_counter = Counter([r["formation"] for r in rankers])
    formation_rankers = {}
    for r in rankers:
        formation_rankers.setdefault(r["formation"], []).append(r["nickname"])

    print("[2/3] 포메이션별 최상위 랭커 실제 라인업 및 다국어 이름 파싱 중...")

    meta_list = []
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)
        routes = TACTICAL_BLUEPRINTS.get(form, TACTICAL_BLUEPRINTS.get(form.replace('4-2-2-1', '4-2-2-1-1'), []))

        actual_rankers = formation_rankers.get(form, [])
        top_rankers_for_chip = actual_rankers[:5]

        real_squad_players = {}
        if actual_rankers:
            top_nick = actual_rankers[0]
            print(f"  -> '{form}' 최상위 랭커 [{top_nick}] 라인업 조회...")
            real_squad_players = fetch_real_squad_players(top_nick)
            time.sleep(0.5)

        if not real_squad_players:
            real_squad_players = {
                "ST": translate_player_server_side("호나우두"),
                "MID": translate_player_server_side("굴리트"),
                "CDM": translate_player_server_side("로드리"),
                "CB": translate_player_server_side("반데이크")
            }

        meta_list.append({
            "formation": form,
            "count": count,
            "share": share,
            "tactical_routes": routes,
            "key_players": real_squad_players,
            "recommended_rankers": top_rankers_for_chip
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid,
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"[3/3] data/meta_today.json 4개국어 선수 데이터 매핑 완료!")


# =====================================================================
# 구글 시트 기반 정적 HTML 페이지 자동 생성 및 sitemap.xml 갱신
# =====================================================================

def clean_slug(val, fallback):
    if val and val.strip():
        s = re.sub(r'[^a-zA-Z0-9-_]', '', val.strip().lower().replace(' ', '-'))
        if s:
            return s
    fallback_s = re.sub(r'[^a-zA-Z0-9-_]', '', fallback.strip().lower().replace(' ', '-'))
    return fallback_s if fallback_s else "item"

def fetch_sheet_csv(gid_name):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={gid_name}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            content = res.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(content))
            return [row for row in reader]
    except Exception as e:
        print(f"Error fetching sheet {gid_name}: {e}")
        return []

TACTIC_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{player_name} {formation} 전술 및 분석 | FC온라인 프로 전술 - WISEPLAY</title>
  <meta name="description" content="FC온라인 {player_name} 선수의 {formation} 포메이션 전술 설정, 개인 전술, 팀 전술 및 실전 해설 분석 가이드입니다.">
  <link rel="canonical" href="{canonical_url}">
  <style>
    :root {{
      --bg-dark: #0f1115;
      --card-bg: #1a1d24;
      --card-border: #2a2e39;
      --accent-color: #00ff88;
      --accent-blue: #00b4d8;
      --accent-gold: #ffbb00;
      --text-main: #f0f2f5;
      --text-muted: #8b949e;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg-dark); color: var(--text-main); font-family: var(--font-family); line-height: 1.6; padding: 24px 16px 80px; }}
    .container {{ max-width: 880px; margin: 0 auto; }}
    .nav-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--card-border); }}
    .home-link {{ color: var(--accent-color); text-decoration: none; font-weight: 700; font-size: 0.95rem; }}
    .card-badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 800; background: rgba(0, 255, 136, 0.15); color: var(--accent-color); margin-bottom: 8px; }}
    h1 {{ font-size: 1.85rem; font-weight: 900; color: #fff; margin-bottom: 6px; }}
    .sub-info {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 20px; }}
    .img-box {{ background: #12151c; border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; margin-bottom: 20px; text-align: center; padding: 12px; }}
    .img-box img {{ max-width: 100%; max-height: 480px; object-fit: contain; border-radius: 8px; }}
    .section-box {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; margin-bottom: 18px; }}
    .section-title {{ font-size: 1.05rem; font-weight: 800; color: var(--accent-blue); margin-bottom: 10px; }}
    .text-content {{ font-size: 0.95rem; color: #d1d5db; line-height: 1.7; white-space: pre-wrap; }}
    .yt-btn {{ display: inline-flex; align-items: center; justify-content: center; width: 100%; padding: 14px; background: #ff0000; color: #fff; text-decoration: none; font-weight: 800; border-radius: 8px; font-size: 0.95rem; margin-top: 10px; }}
    footer {{ text-align: center; margin-top: 40px; font-size: 0.82rem; color: var(--text-muted); border-top: 1px solid var(--card-border); padding-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="nav-bar">
      <a href="/" class="home-link">&larr; WISEPLAY 메인으로 돌아가기</a>
      <span style="font-size: 0.85rem; color: var(--text-muted);">즐인권(FIFA CAMPER) X LJ Lee</span>
    </div>

    <span class="card-badge">{formation}</span>
    <h1>{player_name} 실전 전술 설정</h1>
    <div class="sub-info">{country} | {version_name}</div>

    <div class="img-box">
      <img src="{img_formation}" alt="{player_name} 포메이션 배치도" onerror="this.src='/logo.png'">
    </div>

    <div class="section-box">
      <div class="section-title">📋 전술 상세 분석 및 실전 코멘트</div>
      <div class="text-content">{review_text}</div>
    </div>

    {pad_section}
    {yt_section}

    <footer>
      <p>WISEPLAY &copy; 2026 즐인권(FIFA CAMPER) X LJ Lee. All rights reserved.</p>
      <p style="margin-top: 8px;">
        <a href="/about.html" style="color: var(--text-muted); text-decoration: none; margin-right: 12px;">About & Contact</a>
        <a href="/privacy.html" style="color: var(--accent-color); text-decoration: none;">Privacy Policy</a>
      </p>
    </footer>
  </div>
</body>
</html>
"""

PAD_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{pad_name} 레이턴시·폴링레이트 실측 벤치마크 | WISEPLAY</title>
  <meta name="description" content="{pad_name} 실측 게임패드 벤치마크. 유선, 동글, 블루투스 모드별 실제 폴링레이트와 버튼/스틱 인풋렉 정밀 측정 데이터(LJ Lee 실측)를 제공합니다.">
  <link rel="canonical" href="{canonical_url}">
  <style>
    :root {{
      --bg-dark: #0f1115;
      --card-bg: #1a1d24;
      --card-border: #2a2e39;
      --accent-color: #00ff88;
      --accent-blue: #00b4d8;
      --accent-gold: #ffbb00;
      --text-main: #f0f2f5;
      --text-muted: #8b949e;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg-dark); color: var(--text-main); font-family: var(--font-family); line-height: 1.6; padding: 24px 16px 80px; }}
    .container {{ max-width: 880px; margin: 0 auto; }}
    .nav-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--card-border); }}
    .home-link {{ color: var(--accent-color); text-decoration: none; font-weight: 700; font-size: 0.95rem; }}
    .card-badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 800; background: rgba(0, 180, 216, 0.2); color: var(--accent-blue); margin-bottom: 8px; }}
    h1 {{ font-size: 1.85rem; font-weight: 900; color: #fff; margin-bottom: 6px; }}
    .sub-info {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 20px; }}
    .score-banner {{ background: linear-gradient(135deg, #131722 0%, #1c2230 100%); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px; }}
    .score-label {{ font-size: 0.85rem; font-weight: 800; color: var(--accent-blue); text-transform: uppercase; margin-right: 12px; }}
    .score-num {{ font-size: 2.2rem; font-weight: 900; color: var(--accent-color); }}
    .img-box {{ background: #12151c; border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; margin-bottom: 20px; text-align: center; padding: 12px; }}
    .img-box img {{ max-width: 100%; max-height: 400px; object-fit: contain; border-radius: 8px; }}
    .section-box {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; margin-bottom: 18px; }}
    .section-title {{ font-size: 1.05rem; font-weight: 800; color: var(--accent-blue); margin-bottom: 12px; }}
    .bench-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 6px; }}
    .bench-table th, .bench-table td {{ padding: 10px 12px; border: 1px solid #2d3342; text-align: left; }}
    .bench-table th {{ background: #232834; color: var(--text-muted); font-size: 0.82rem; }}
    .bench-table td {{ background: #181c25; }}
    .yt-btn {{ display: inline-flex; align-items: center; justify-content: center; width: 100%; padding: 14px; background: #ff0000; color: #fff; text-decoration: none; font-weight: 800; border-radius: 8px; font-size: 0.95rem; margin-top: 10px; }}
    footer {{ text-align: center; margin-top: 40px; font-size: 0.82rem; color: var(--text-muted); border-top: 1px solid var(--card-border); padding-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="nav-bar">
      <a href="/" class="home-link">&larr; WISEPLAY 메인으로 돌아가기</a>
      <span style="font-size: 0.85rem; color: var(--text-muted);">LJ Lee 정밀 벤치마크</span>
    </div>

    <span class="card-badge">GAMEPAD BENCHMARK</span>
    <h1>{pad_name} 정밀 측정 데이터</h1>
    <div class="sub-info">스틱 방식: {stick_mech} | 키매핑: {key_map} | 매크로: {macro}</div>

    <div class="score-banner">
      <span class="score-label">LJ's META SCORE</span>
      <span class="score-num">{meta_score}</span>
      <span style="color: #717b88; font-weight: 700;">/ 100</span>
    </div>

    <div class="img-box">
      <img src="{img_url}" alt="{pad_name}" onerror="this.src='/logo.png'">
    </div>

    <div class="section-box">
      <div class="section-title">📊 3대 연결 모드 정밀 벤치마크 (LJ Lee 실측)</div>
      <table class="bench-table">
        <thead>
          <tr>
            <th>연결 방식</th>
            <th>폴링레이트 (Hz)</th>
            <th>스틱 레이턴시 (ms)</th>
            <th>버튼 레이턴시 (ms)</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><b>유선 (Wired)</b></td>
            <td>{w_poll} Hz</td>
            <td>{w_stick_lat} ms</td>
            <td>{w_btn_lat} ms</td>
          </tr>
          <tr>
            <td><b>동글 (Dongle 2.4G)</b></td>
            <td>{d_poll} Hz</td>
            <td>{d_stick_lat} ms</td>
            <td>{d_btn_lat} ms</td>
          </tr>
          <tr>
            <td><b>블루투스 (BT)</b></td>
            <td>{b_poll} Hz</td>
            <td>{b_stick_lat} ms</td>
            <td>{b_btn_lat} ms</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="section-box">
      <div class="section-title">⚖️ 장점 및 아쉬운 점 (Pros & Cons)</div>
      <p style="margin-bottom: 8px;"><b style="color: var(--accent-color);">[장점]</b> {pros}</p>
      <p><b style="color: #ff6b6b;">[단점]</b> {cons}</p>
    </div>

    {yt_section}

    <footer>
      <p>WISEPLAY &copy; 2026 즐인권(FIFA CAMPER) X LJ Lee. All rights reserved.</p>
      <p style="margin-top: 8px;">
        <a href="/about.html" style="color: var(--text-muted); text-decoration: none; margin-right: 12px;">About & Contact</a>
        <a href="/privacy.html" style="color: var(--accent-color); text-decoration: none;">Privacy Policy</a>
      </p>
    </footer>
  </div>
</body>
</html>
"""

def generate_static_pages_and_sitemap():
    print("[4/4] 구글 시트 데이터 기반 정적 상세 HTML 및 sitemap.xml 생성 시작...")
    tactics = fetch_sheet_csv("tactics")
    pads = fetch_sheet_csv("pads")

    sitemap_urls = [
        f"{BASE_DOMAIN}/",
        f"{BASE_DOMAIN}/meta",
        f"{BASE_DOMAIN}/about.html",
        f"{BASE_DOMAIN}/privacy.html"
    ]

    # 1. Tactics 개별 페이지 생성
    for item in tactics:
        player_name = item.get("playerName", "").strip()
        if not player_name:
            continue
        slug = clean_slug(item.get("slug"), player_name)
        folder = os.path.join("tactics", slug)
        os.makedirs(folder, exist_ok=True)

        canonical_url = f"{BASE_DOMAIN}/tactics/{slug}/"
        sitemap_urls.append(canonical_url)

        pad_name = item.get("padName", "").strip()
        pad_section = ""
        if pad_name:
            pad_section = f"""
            <div class="section-box">
              <div class="section-title">🎮 선수가 사용하는 패드</div>
              <p><b>{pad_name}</b></p>
            </div>
            """

        yt_url = item.get("ytUrl", "").strip()
        yt_section = ""
        if yt_url:
            yt_section = f'<a href="{yt_url}" target="_blank" rel="noopener" class="yt-btn">▶ 즐인권의 실전 전술 해설 유튜브 영상 보기</a>'

        html_content = TACTIC_PAGE_TEMPLATE.format(
            player_name=player_name,
            formation=item.get("formation", "4-2-2-1-1"),
            country=item.get("country", "GLOBAL"),
            version_name=item.get("versionName", "-"),
            canonical_url=canonical_url,
            img_formation=item.get("imgFormation", "/logo.png"),
            review_text=item.get("reviewText", "상세 분석 내용이 업데이트될 예정입니다."),
            pad_section=pad_section,
            yt_section=yt_section
        )

        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

    # 2. Pads 개별 페이지 생성
    for item in pads:
        pad_name = item.get("padName", "").strip()
        if not pad_name:
            continue
        slug = clean_slug(item.get("slug"), pad_name)
        folder = os.path.join("controllers", slug)
        os.makedirs(folder, exist_ok=True)

        canonical_url = f"{BASE_DOMAIN}/controllers/{slug}/"
        sitemap_urls.append(canonical_url)

        yt_url = item.get("ytUrl", "").strip()
        yt_section = ""
        if yt_url:
            yt_section = f'<a href="{yt_url}" target="_blank" rel="noopener" class="yt-btn">▶ LJ Lee 정밀 벤치마크 영상 보기</a>'

        html_content = PAD_PAGE_TEMPLATE.format(
            pad_name=pad_name,
            stick_mech=item.get("stickMech", "-"),
            key_map=item.get("keyMap", "-"),
            macro=item.get("macro", "-"),
            meta_score=item.get("metaScore", "0"),
            canonical_url=canonical_url,
            img_url=item.get("imgUrl", "/logo.png"),
            w_poll=item.get("wPoll", "-"),
            w_stick_lat=item.get("wStickLat", "-"),
            w_btn_lat=item.get("wBtnLat", "-"),
            d_poll=item.get("dPoll", "-"),
            d_stick_lat=item.get("dStickLat", "-"),
            d_btn_lat=item.get("dBtnLat", "-"),
            b_poll=item.get("bPoll", "-"),
            b_stick_lat=item.get("bStickLat", "-"),
            b_btn_lat=item.get("bBtnLat", "-"),
            pros=item.get("pros", "-"),
            cons=item.get("cons", "-"),
            yt_section=yt_section
        )

        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

    # 3. sitemap.xml 자동 생성
    sitemap_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for u in sitemap_urls:
        sitemap_lines.append(f"  <url><loc>{u}</loc><lastmod>{TODAY_STR}</lastmod><changefreq>daily</changefreq></url>")
    sitemap_lines.append('</urlset>')

    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap_lines))
    print(f"  => 총 {len(sitemap_urls)}개 URL sitemap.xml 생성 완료!")


if __name__ == "__main__":
    process_and_save()
    generate_static_pages_and_sitemap()
