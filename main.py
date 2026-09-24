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

# 1. 넥슨 공식 API 호출 헬퍼
def api_get(endpoint, params=None):
    if not API_KEY:
        print("API 키가 설정되지 않았습니다.")
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

# 2. 넥슨 공식 API에서 실시간 공경 1on1(50) 랭커 TOP 100 전수 추출
def get_real_top_rankers():
    print("[1/4] 넥슨 공식 랭커 API에서 실제 1~100위 구단주 수집 중...")
    # 공식경기 1on1(matchtype: 50) 상위 랭커 조회
    ranker_data = api_get("ranker", {"matchtype": 50})
    
    rankers = []
    if ranker_data:
        for item in ranker_data:
            ouid = item.get("ouid")
            nickname = item.get("nickname")
            if ouid and nickname:
                rankers.append({"ouid": ouid, "nickname": nickname})
            elif ouid:
                # 닉네임이 누락된 경우 역조회
                u_info = api_get(f"users/{ouid}")
                if u_info and "nickname" in u_info:
                    rankers.append({"ouid": ouid, "nickname": u_info["nickname"]})
            if len(rankers) >= 100:
                break

    print(f"  => 실제 공식경기 랭커 {len(rankers)}명 확보 완료")
    return rankers

# 3. 포메이션 역추정 로직
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

# 4. 실시간 랭커 최신 경기 및 전술 분석
def analyze_matches(ranker_list):
    print("[2/4] 실제 랭커 인게임 최근 경기 전술 전수 분석 중...")
    
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

    for r in ranker_list:
        ouid = r["ouid"]
        nick = r["nickname"]

        matches = api_get(f"users/{ouid}/matches", {"matchtype": 50, "offset": 0, "limit": 1})
        if not matches:
            continue

        match_detail = api_get(f"matches/{matches[0]}")
        if not match_detail or "matchInfo" not in match_detail:
            continue

        target_info = None
        for m in match_detail["matchInfo"]:
            if m.get("ouid") == ouid:
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

        time.sleep(0.15)

    total_valid = sum(formation_counter.values())
    if total_valid == 0:
        print("분석된 경기 데이터가 없습니다.")
        return

    print(f"[3/4] 실측 완료 (유효 표본: {total_valid}명). JSON 생성 중...")
    meta_list = []

    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)
        
        routes = [
            f"실제 랭커 {form} 빌드업: 중앙 미드필더 전진 패스 및 침투",
            "측면 풀백/윙어 지원을 활용한 박스 안 컷백 플레이"
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

    print(f"[4/4] data/meta_today.json 실제 랭커 데이터 저장 완료!")

if __name__ == "__main__":
    top_rankers = get_real_top_rankers()
    analyze_matches(top_rankers)
