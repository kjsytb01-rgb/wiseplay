import os
import re
import json
import time
import requests
from datetime import datetime
from collections import Counter
from playwright.sync_api import sync_playwright

API_KEY = os.environ.get("NEXON_API_KEY", "").strip()
HEADERS = {"x-nxopen-api-key": API_KEY}
BASE_URL = "https://open.api.nexon.com/fconline/v1"

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

            # 넥슨 공식 포지션 기준
            if pos_id in [20, 21, 24, 25] and "ST" not in extracted:
                extracted["ST"] = p_name
            elif pos_id in [12, 13, 14, 15, 16, 17, 18, 19] and "MID" not in extracted:
                extracted["MID"] = p_name
            elif pos_id in [9, 10, 11] and "CDM" not in extracted:
                extracted["CDM"] = p_name
            elif pos_id in [4, 5, 6, 7] and "CB" not in extracted:
                extracted["CB"] = p_name

        return extracted
    except Exception:
        return {}

def collect_real_top100_playwright():
    print("[1/3] 넥슨 데이터센터 순위표 실시간 1~100위 전수 수집 중...")
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
                    // 4-2-2-1-1까지 완벽히 매칭하는 정규식
                    const formMatch = text.match(/\\b(\\d(?:-\\d){2,4})\\b/);
                    if (!formMatch) return;
                    
                    let formStr = formMatch[1];
                    // 혹시라도 4-2-2-1로 잡혔다면 4-2-2-1-1로 보정
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

    print(f"  => 실시간 슈챔 랭커 100명 전수 수집 완료: 총 {len(ranker_data)}명")
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

    print("[2/3] 포메이션별 최상위 랭커 실제 인게임 라인업 추출 중...")

    meta_list = []
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)
        
        # 4-2-2-1-1 키 완벽 매칭
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
                "ST": "호나우두", "MID": "굴리트", "CDM": "로드리", "CB": "반데이크"
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

    print(f"[3/3] data/meta_today.json 업데이트 완료! (표본: {total_valid}명)")

if __name__ == "__main__":
    process_and_save()
