import os
import re
import time
import json
import asyncio
from datetime import datetime
from collections import Counter
import requests
from playwright.async_api import async_playwright

API_KEY = os.environ.get("NEXON_API_KEY", "").strip()
HEADERS = {"x-nxopen-api-key": API_KEY}
BASE_URL = "https://open.api.nexon.com/fconline/v1"

# 1. 넥슨 데이터센터 공식 순위표 1~100위 구단주 추출
async def scrape_top_100():
    rankers = []
    print("[1/4] Playwright로 넥슨 데이터센터 순위표 TOP 100명 수집 시작...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        
        await page.goto("https://datacenter.fconline.nexon.com/Rank/RankList?matchtype=50", wait_until="networkidle")
        await page.wait_for_selector(".coach_wrap .name.profile_pointer", timeout=15000)

        for p_idx in range(1, 6):
            if p_idx > 1:
                # SPA 내부 자바스크립트 호출로 씹힘 없는 즉각 페이징
                await page.evaluate(f"window.ChangePage ? window.ChangePage({p_idx}) : window.goPage({p_idx})")
                await asyncio.sleep(2)
                await page.wait_for_selector(".coach_wrap .name.profile_pointer", timeout=10000)

            elements = await page.query_selector_all(".coach_wrap .name.profile_pointer")
            for el in elements:
                name = (await el.inner_text()).strip()
                if name and name not in rankers:
                    rankers.append(name)
            print(f"  -> {p_idx}페이지 수집 완료 (현재 누적 {len(rankers)}명)")

        await browser.close()

    pure_top_100 = rankers[:100]
    print(f"  => 최종 TOP 100명 추출 완료: {len(pure_top_100)}명")
    return pure_top_100

# 2. 넥슨 API 429 방어 호출 헬퍼
def api_get(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"
    for _ in range(3):
        res = requests.get(url, headers=HEADERS, params=params)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 429:
            time.sleep(1.5)
        else:
            time.sleep(0.5)
    return None

# 포메이션 역추정 (좌표 기반 표준 포메이션 매핑)
def infer_formation(desc_title, players):
    if desc_title and any(c.isdigit() for c in desc_title):
        match = re.search(r'\d+-\d+(-\d+)+', desc_title)
        if match:
            return match.group(0)

    # 포지션 포지션 ID 기준 매핑
    pos_types = []
    for p in players:
        sp_id = p.get("spPosition", 0)
        if sp_id == 0: continue
        elif sp_id in [1, 2, 3, 4, 5, 6, 7, 8]: pos_types.append("DF")
        elif sp_id in [9, 10, 11, 12, 13, 14, 15, 16, 17, 18]: pos_types.append("MF")
        elif sp_id in [19, 20, 21, 22, 23, 24, 25, 26, 27]: pos_types.append("FW")

    counts = Counter(pos_types)
    df = counts.get("DF", 4)
    mf = counts.get("MF", 3)
    fw = counts.get("FW", 3)
    return f"{df}-{mf}-{fw}"

# 3. 전수 매치 분석
def analyze_matches(rankers):
    print("[2/4] 랭커 OUID 조회 및 최근 공식경기 매치 데이터 파싱 시작...")
    
    # spPosition 코드 -> 역할명
    pos_map = {
        25: "ST", 26: "CF", 27: "LW", 23: "RW",
        18: "CAM", 14: "CM", 12: "LM", 16: "RM", 10: "CDM",
        3: "CB", 4: "CB", 7: "LB", 8: "RB", 0: "GK"
    }

    # 선수 메타데이터 (고유 spId 캐시 매핑)
    spid_meta = {}
    try:
        spid_res = requests.get("https://open.api.nexon.com/static/fconline/meta/spid.json").json()
        for item in spid_res:
            spid_meta[item["id"]] = item["name"]
    except Exception:
        pass

    formation_counter = Counter()
    formation_rankers = {}
    formation_routes = {}
    formation_players = {}

    processed = 0
    for nick in rankers:
        processed += 1
        ouid_data = api_get("id", {"nickname": nick})
        if not ouid_data or "ouid" not in ouid_data:
            continue
        ouid = ouid_data["ouid"]

        # 최근 1vs1 공식경기(matchtype=50) 1경기 추출
        matches = api_get(f"users/{ouid}/matches", {"matchtype": 50, "offset": 0, "limit": 1})
        if not matches:
            continue

        match_detail = api_get(f"matches/{matches[0]}")
        if not match_detail or "matchInfo" not in match_detail:
            continue

        target_info = None
        for m in match_detail["matchInfo"]:
            if m.get("ouid") == ouid or m.get("nickname") == nick:
                target_info = m
                break
        if not target_info:
            continue

        # 포메이션 및 선수
        players = target_info.get("player", [])
        desc = target_info.get("matchDetail", {}).get("formation", "")
        formation = infer_formation(desc, players)

        formation_counter[formation] += 1
        formation_rankers.setdefault(formation, []).append(nick)
        formation_routes.setdefault(formation, []).append(target_info.get("pass", {}))
        
        # 포지션별 픽 선수 누적
        formation_players.setdefault(formation, {})
        for p in players:
            sp_pos = p.get("spPosition", -1)
            sp_id = p.get("spId", 0)
            p_name = spid_meta.get(sp_id, f"ID:{sp_id}")
            role = pos_map.get(sp_pos, "SUB")
            if role in ["ST", "CF", "CAM", "CDM", "CB"]:
                formation_players[formation].setdefault(role, Counter())[p_name] += 1

        if processed % 20 == 0:
            print(f"  -> {processed}/{len(rankers)}명 매치 분석 완료...")
        time.sleep(0.3)  # 안전 딜레이

    # 4. 종합 집계 및 JSON 구성
    print("[3/4] 통계 요약 및 프론트엔드용 JSON 직렬화...")
    total_valid = sum(formation_counter.values()) or 1
    meta_list = []

    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)

        # 주요 득점/패스 루트 추정
        routes = []
        pass_datas = formation_routes.get(form, [])
        through_ratios = []
        for pd in pass_datas:
            total_p = pd.get("passTry", 0)
            through_p = pd.get("throughPassTry", 0)
            if total_p > 0:
                through_ratios.append((through_p / total_p) * 100)
        
        avg_through = round(sum(through_ratios) / len(through_ratios), 1) if through_ratios else 15.0
        routes.append(f"스루패스({avg_through}%) 기반 중앙 2:1 연계 침투")
        routes.append(f"측면 오버래핑 엔드라인 컷백 마무리")

        # 포지션별 최다 픽 1위 선수
        key_players = {}
        for role, p_cnt in formation_players.get(form, {}).items():
            if p_cnt:
                top_player = p_cnt.most_common(1)[0][0]
                key_players[role] = top_player

        meta_list.append({
            "formation": form,
            "count": count,
            "share": share,
            "tactical_routes": routes,
            "key_players": key_players,
            "recommended_rankers": formation_rankers.get(form, [])[:4]
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid,
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"[4/4] 완료! data/meta_today.json 생성 성공 (유효 표본 {total_valid}명)")

if __name__ == "__main__":
    if not API_KEY:
        print("경고: NEXON_API_KEY 환경변수가 설정되지 않았습니다.")
    top_rankers = asyncio.run(scrape_top_100())
    analyze_matches(top_rankers)
