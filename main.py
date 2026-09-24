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

# 1. 넥슨 공식 도메인(fconline.nexon.com)에서 실시간 1~100위 구단주 닉네임 수집
def get_official_top100():
    print("[1/4] FC 온라인 공식 순위표(실시간 1~100위) 수집 시작...")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://fconline.nexon.com/datacenter/rank"
    })

    real_rankers = []
    
    # 넥슨 공식 데이터센터 순위표 URL (fconline.nexon.com)
    for page in range(1, 6):
        urls = [
            f"https://fconline.nexon.com/datacenter/Rank/GetRankList?matchtype=50&page={page}",
            f"https://fconline.nexon.com/datacenter/rank?matchtype=50&page={page}"
        ]
        
        success = False
        for url in urls:
            try:
                res = session.get(url, timeout=12)
                if res.status_code == 200 and len(res.text) > 500:
                    html = res.text
                    # 넥슨 구단주명 파싱 (다양한 클래스 패턴 대응)
                    names = re.findall(r'class="name[^"]*"[^>]*>([^<]+)</span>', html)
                    if not names:
                        names = re.findall(r'<span class="profile_pointer"[^>]*>([^<]+)</span>', html)
                    if not names:
                        names = re.findall(r'data-nickname="([^"]+)"', html)
                    
                    for n in names:
                        clean_name = n.strip()
                        if clean_name and clean_name not in real_rankers:
                            real_rankers.append(clean_name)
                    
                    if names:
                        print(f"  -> {page}페이지 수집 성공 ({url}): 누적 {len(real_rankers)}명")
                        success = True
                        break
            except Exception as e:
                pass
        
        if not success:
            print(f"  -> {page}페이지 응답 지연/누락 (다음 페이지 진행)")
        time.sleep(0.4)

    # 만약 해외 IP 차단 등으로 수집이 누락되었을 때의 방어 로직 (기존 랭커 유지)
    if len(real_rankers) == 0:
        print("  => 공식 순위표 HTML 응답이 비어있음, API 백업 경로 탐색 중...")
        # 넥슨 공식경기 최근 탑 매치에서 고랭커 닉네임 직접 추출
        try:
            m_res = requests.get(f"{BASE_URL}/match?matchtype=50&offset=0&limit=50", headers=HEADERS, timeout=10).json()
            if m_res and isinstance(m_res, list):
                for mid in m_res[:30]:
                    d_res = requests.get(f"{BASE_URL}/matches/{mid}", headers=HEADERS, timeout=10).json()
                    for u in d_res.get("matchInfo", []):
                        nick = u.get("nickname")
                        if nick and nick not in real_rankers:
                            real_rankers.append(nick)
                    if len(real_rankers) >= 50:
                        break
        except Exception:
            pass

    print(f"  => 최종 확보된 실시간 랭커 구단주: {len(real_rankers)}명")
    return real_rankers[:100]

# 2. 넥슨 공식 API 호출
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
                time.sleep(1.2)
            else:
                time.sleep(0.3)
        except Exception:
            time.sleep(0.3)
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

# 3. 랭커 실제 경기 데이터 분석
def analyze_real_rankers(ranker_names):
    print("[2/4] 수집된 실시간 랭커 인게임 경기 데이터 분석 시작...")

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

    for nick in ranker_names:
        user_res = api_get("id", {"nickname": nick})
        if not user_res or "ouid" not in user_res:
            continue
        ouid = user_res["ouid"]

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

        time.sleep(0.1)

    total_valid = sum(formation_counter.values())
    print(f"[3/4] 실측 유효 표본: {total_valid}명")

    if total_valid == 0:
        print("[경고] 전술 파싱 표본이 없습니다.")
        return

    meta_list = []
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)

        routes = [
            f"{form} 전술: 중앙 미드필더 전진 패스 및 침투 연계",
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

    print(f"[4/4] data/meta_today.json 정상 저장 완료!")

if __name__ == "__main__":
    rankers = get_official_top100()
    if rankers:
        analyze_real_rankers(rankers)
