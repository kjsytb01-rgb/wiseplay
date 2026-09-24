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
        print("[경고] NEXON_API_KEY 환경변수가 비어 있습니다.")
        return None
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(3):
        try:
            res = requests.get(url, headers=HEADERS, params=params, timeout=12)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 429:
                time.sleep(1.5)
            else:
                time.sleep(0.5)
        except Exception as e:
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

def run_pipeline():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 메타 데이터 수집 파이프라인 시작")
    
    # 선수 ID 메타데이터 로드
    spid_meta = {}
    try:
        spid_res = requests.get("https://open.api.nexon.com/static/fconline/meta/spid.json", timeout=10).json()
        for item in spid_res:
            spid_meta[item["id"]] = item["name"]
        print(f"  선수 메타데이터 로드 완료 ({len(spid_meta)}명)")
    except Exception as e:
        print("  선수 메타 로드 실패 (기본값 사용)")

    pos_map = {
        25: "ST", 26: "CF", 27: "LW", 23: "RW",
        18: "CAM", 14: "CM", 12: "LM", 16: "RM", 10: "CDM",
        3: "CB", 4: "CB", 7: "LB", 8: "RB", 0: "GK"
    }

    formation_counter = Counter()
    formation_rankers = {}
    formation_players = {}
    processed_users = set()

    # 1. 실시간 1on1 공식경기(50) 최신 매치 ID 추출
    match_ids = []
    for offset in [0, 50, 100]:
        res = api_get("match", {"matchtype": 50, "offset": offset, "limit": 50})
        if res and isinstance(res, list):
            match_ids.extend(res)
        time.sleep(0.15)

    print(f"  실시간 공식경기 매치 ID 확보: {len(match_ids)}건")

    # 2. 매치 상세 데이터에서 실시간 구단주 및 포메이션 전수 분석
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
    print(f"  분석 완료 유효 표본: {total_valid}명")

    # 만약 수집된 표본이 0명이면 기존 정상 파일을 날리지 않도록 보호
    if total_valid == 0:
        print("[경고] 이번 회차 수집된 표본이 0명입니다. JSON 파일을 갱신하지 않고 종료합니다.")
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

    print("  => data/meta_today.json 갱신 완료!")

if __name__ == "__main__":
    run_pipeline()
