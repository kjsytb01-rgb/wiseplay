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

def api_get(endpoint, params=None):
    if not API_KEY:
        print("[오류] NEXON_API_KEY 환경변수가 설정되지 않았습니다.")
        return None
    url = f"{BASE_URL}/{endpoint}"
    for _ in range(3):
        try:
            res = requests.get(url, headers=HEADERS, params=params, timeout=10)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 429:
                time.sleep(1.2)
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
        if sp_id == 0: 
            continue
        elif sp_id in [1, 2, 3, 4, 5, 6, 7, 8]: 
            pos_types.append("DF")
        elif sp_id in [9, 10, 11, 12, 13, 14, 15, 16, 17, 18]: 
            pos_types.append("MF")
        elif sp_id in [19, 20, 21, 22, 23, 24, 25, 26, 27]: 
            pos_types.append("FW")

    counts = Counter(pos_types)
    df = counts.get("DF", 4)
    mf = counts.get("MF", 2)
    fw = counts.get("FW", 3)
    return f"{df}-{mf}-{fw}"

def collect_and_analyze():
    print("[1/3] 넥슨 공식경기(1on1) 실시간 매치 데이터 수집 시작...")
    
    # 공식경기 1on1(matchtype 50) 최근 매치 식별자 목록 조회
    match_ids = []
    for offset in [0, 50, 100]:
        res = api_get("match", {"matchtype": 50, "offset": offset, "limit": 50})
        if res and isinstance(res, list):
            match_ids.extend(res)
        time.sleep(0.2)

    print(f"  => 조회된 공식경기 매치 수: {len(match_ids)}건")
    if not match_ids:
        print("[경고] 매치 식별자를 불러오지 못했습니다. API 키 권한을 확인하세요.")
        return

    # 선수 이름 매핑 메타데이터 로드
    spid_meta = {}
    try:
        spid_res = requests.get("https://open.api.nexon.com/static/fconline/meta/spid.json", timeout=10).json()
        for item in spid_res:
            spid_meta[item["id"]] = item["name"]
    except Exception:
        pass

    pos_map = {
        25: "ST", 26: "CF", 27: "LW", 23: "RW",
        18: "CAM", 14: "CM", 12: "LM", 16: "RM", 10: "CDM",
        3: "CB", 4: "CB", 7: "LB", 8: "RB", 0: "GK"
    }

    formation_counter = Counter()
    formation_rankers = {}
    formation_players = {}
    processed_users = set()

    print("[2/3] 실시간 유저 전술 및 기용 선수 전수 분석 중...")
    for mid in match_ids:
        detail = api_get(f"matches/{mid}")
        if not detail or "matchInfo" not in detail:
            continue

        for user_info in detail["matchInfo"]:
            ouid = user_info.get("ouid")
            nickname = user_info.get("nickname")

            if not nickname or ouid in processed_users:
                continue
            processed_users.add(ouid)

            players = user_info.get("player", [])
            desc = user_info.get("matchDetail", {}).get("formation", "")
            formation = infer_formation(desc, players)

            formation_counter[formation] += 1
            formation_rankers.setdefault(formation, []).append(nickname)

            formation_players.setdefault(formation, {})
            for p in players:
                sp_pos = p.get("spPosition", -1)
                sp_id = p.get("spId", 0)
                p_name = spid_meta.get(sp_id, f"선수({sp_id})")
                role = pos_map.get(sp_pos, "SUB")
                if role in ["ST", "CF", "CAM", "CDM", "CB"]:
                    formation_players[formation].setdefault(role, Counter())[p_name] += 1

            if len(processed_users) >= 100:
                break

        if len(processed_users) >= 100:
            break
        time.sleep(0.1)

    total_valid = sum(formation_counter.values())
    print(f"  => 최종 집계 완료 (실제 표본: {total_valid}명)")

    if total_valid == 0:
        print("[경고] 유효한 전술 데이터가 없습니다.")
        return

    meta_list = []
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)
        
        routes = [
            f"{form} 기반: 2선과 전방 연계를 통한 중앙 집중 빌드업",
            "측면 전환 후 빠른 컷백 및 박스 침투 마무리"
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

    print("[3/3] data/meta_today.json 갱신 완료!")

if __name__ == "__main__":
    collect_and_analyze()
