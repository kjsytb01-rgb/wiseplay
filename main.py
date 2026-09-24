import os
import re
import time
import json
from datetime import datetime
from collections import Counter
import requests

API_KEY = os.environ.get("NEXON_API_KEY", "").strip()
HEADERS = {"x-nxopen-api-key": API_KEY}
BASE_URL = "https://open.api.nexon.com/fconline/v1"

# 1. 넥슨 데이터센터 순위표에서 실제 1~100위 구단주 닉네임 추출
def get_real_top_rankers():
    print("[1/4] FC온라인 공식 랭킹 순위표(1~100위) 수집 시작...")
    rankers = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://fconline.nexon.com/datacenter/rank",
        "X-Requested-With": "XMLHttpRequest"
    }

    # 1페이지당 20명 x 5페이지 = 100명
    for page in range(1, 6):
        url = f"https://datacenter.fconline.nexon.com/Rank/GetRankList?matchtype=50&page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                html = res.text
                # 구단주 닉네임 파싱
                names = re.findall(r'class="name profile_pointer"[^>]*>([^<]+)</span>', html)
                if not names:
                    names = re.findall(r'class="name[^"]*"[^>]*>([^<]+)</span>', html)
                
                for n in names:
                    clean_name = n.strip()
                    if clean_name and clean_name not in rankers:
                        rankers.append(clean_name)
                print(f"  -> {page}페이지 수집 완료 (현재 {len(rankers)}명)")
        except Exception as e:
            print(f"  -> {page}페이지 수집 실패: {e}")
        time.sleep(0.3)

    print(f"  => 최종 유효 실시간 랭커 수집 완료: {len(rankers)}명")
    return rankers[:100]

# 2. 넥슨 Open API 호출 헬퍼
def api_get(endpoint, params=None):
    if not API_KEY:
        return None
    url = f"{BASE_URL}/{endpoint}"
    for _ in range(3):
        try:
            res = requests.get(url, headers=HEADERS, params=params, timeout=10)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 429:
                time.sleep(1.5)
            else:
                time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return None

def infer_formation(desc_title, players):
    if desc_title and any(c.isdigit() for c in desc_title):
        match = re.search(r'\d+-\d+(-\d+)+', desc_title)
        if match:
            return match.group(0)

    pos_types = []
    for p in players:
        sp_id = p.get("spPosition", 0)
        if sp_id == 0: continue
        elif sp_id in [1, 2, 3, 4, 5, 6, 7, 8]: pos_types.append("DF")
        elif sp_id in [9, 10, 11, 12, 13, 14, 15, 16, 17, 18]: pos_types.append("MF")
        elif sp_id in [19, 20, 21, 22, 23, 24, 25, 26, 27]: pos_types.append("FW")

    counts = Counter(pos_types)
    df = counts.get("DF", 4)
    mf = counts.get("MF", 2)
    fw = counts.get("FW", 3)
    return f"{df}-{mf}-{fw}"

# 3. 실제 랭커 인게임 전술 분석
def analyze_matches(rankers):
    print("[2/4] 랭커 인게임 실시간 경기 데이터 전수 분석 중...")
    
    pos_map = {
        25: "ST", 26: "CF", 27: "LW", 23: "RW",
        18: "CAM", 14: "CM", 12: "LM", 16: "RM", 10: "CDM",
        3: "CB", 4: "CB", 7: "LB", 8: "RB", 0: "GK"
    }

    spid_meta = {}
    try:
        spid_res = requests.get("https://open.api.nexon.com/static/fconline/meta/spid.json", timeout=10).json()
        for item in spid_res:
            spid_meta[item["id"]] = item["name"]
    except Exception:
        pass

    formation_counter = Counter()
    formation_rankers = {}
    formation_players = {}

    for nick in rankers:
        ouid_data = api_get("id", {"nickname": nick})
        if not ouid_data or "ouid" not in ouid_data:
            continue
        ouid = ouid_data["ouid"]

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

        players = target_info.get("player", [])
        desc = target_info.get("matchDetail", {}).get("formation", "")
        formation = infer_formation(desc, players)

        formation_counter[formation] += 1
        formation_rankers.setdefault(formation, []).append(nick)
        
        formation_players.setdefault(formation, {})
        for p in players:
            sp_pos = p.get("spPosition", -1)
            sp_id = p.get("spId", 0)
            p_name = spid_meta.get(sp_id, f"선수({sp_id})")
            role = pos_map.get(sp_pos, "SUB")
            if role in ["ST", "CF", "CAM", "CDM", "CB"]:
                formation_players[formation].setdefault(role, Counter())[p_name] += 1

        time.sleep(0.12)

    total_valid = sum(formation_counter.values())
    print(f"[3/4] 실측 유효 표본: {total_valid}명")

    meta_list = []
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)
        
        routes = [
            f"{form} 특화: 중앙 2선 빌드업 및 침투 연계",
            "측면 윙어 돌파 후 박스 안 컷백 및 감아차기 슈팅"
        ]

        key_players = {}
        for role, p_cnt in formation_players.get(form, {}).items():
            if p_cnt:
                key_players[role] = p_cnt.most_common(1)[0][0]

        meta_list.append({
            "formation": form,
            "count": count,
            "share": share,
            "tactical_routes": routes,
            "key_players": key_players,
            "recommended_rankers": formation_rankers.get(form, [])[:5]
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid,
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"[4/4] data/meta_today.json 생성 완료!")

if __name__ == "__main__":
    real_rankers = get_real_top_rankers()
    analyze_matches(real_rankers)
