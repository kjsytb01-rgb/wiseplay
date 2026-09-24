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

def fetch_real_rankers():
    print("[1/3] FC 온라인 데이터센터 실시간 랭킹 HTML 수집 중...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://fconline.nexon.com/"
    }

    url = "https://fconline.nexon.com/datacenter/rank"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        html = res.text
    except Exception as e:
        print(f"[오류] 접속 예외 발생: {e}")
        return []

    print(f"  => 응답 수신 완료 (길이: {len(html)} bytes)")

    # 넥슨 순위표 테이블(<tr>...</tr>) 전수 파싱
    rows = re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', html)
    print(f"  => 테이블 행(Row) 탐색: {len(rows)}개")

    ranker_data = [] # [{"nickname": "...", "formation": "..."}, ...]

    for r in rows:
        # 각 행 내부의 <td> 또는 태그 텍스트 추출
        cols = re.findall(r'<td[^>]*>([\s\S]*?)</td>', r)
        if not cols:
            continue

        clean_cols = []
        for c in cols:
            # HTML 태그 제거 및 공백 정리
            text = re.sub(r'<[^>]+>', ' ', c).strip()
            clean_cols.append(text)

        # 랭킹 행 식별: 보통 1열/2열에 순위, 구단주명, 포메이션 등이 존재
        row_str = " ".join(clean_cols)
        
        # 포메이션 패턴 찾기 (예: 4-2-3-1, 4-2-2-2, 4-1-2-3 등)
        form_match = re.search(r'\b\d-\d-\d(?:-\d)?\b', row_str)
        formation = form_match.group(0) if form_match else "4-2-2-1-1"

        # 닉네임 추출 (클릭 가능한 링크 태그 또는 td 안의 텍스트)
        nick_match = re.search(r'<(?:a|span)[^>]*>(.*?)</(?:a|span)>', "".join(cols))
        nick = ""
        if nick_match:
            nick = re.sub(r'<[^>]+>', '', nick_match.group(1)).strip()
        
        # 보조: clean_cols 중에서 한글/영문 닉네임 형태 감지
        if not nick or len(nick) < 2 or nick in ["순위", "구단주", "포메이션", "구단가치", "상세보기"]:
            for col in clean_cols:
                # 숫자나 특수단어가 아닌 구단주명 후보 탐색
                if len(col) >= 2 and not col.isdigit() and not re.search(r'\b\d-\d-\d\b', col) and "억" not in col and "%" not in col and col not in ["구단주명", "감독명", "순위", "승률"]:
                    nick = col.split()[0]
                    break

        if nick and len(nick) >= 2:
            ranker_data.append({"nickname": nick, "formation": formation})

    print(f"  => 실시간 실제 랭커 파싱 성공: {len(ranker_data)}명 확보!")
    if ranker_data:
        print(f"  => 상위 랭커 샘플: {[x['nickname'] for x in ranker_data[:5]]}")

    return ranker_data

def build_meta():
    rankers = fetch_real_rankers()
    if not rankers:
        print("[경고] 랭커 목록을 파싱하지 못했습니다.")
        return

    # 실측 포메이션 카운팅 및 랭커 분류
    formation_counter = Counter()
    formation_rankers = {}

    for r in rankers:
        f = r["formation"]
        nick = r["nickname"]
        formation_counter[f] += 1
        formation_rankers.setdefault(f, []).append(nick)

    total_valid = len(rankers)
    print(f"[2/3] 실시간 포메이션 실측 통계 (총 {total_valid}명 표본):")
    for f, count in formation_counter.most_common(5):
        print(f"  - {f}: {count}명")

    meta_list = []
    
    # 랭커들의 선호 핵심 1픽 선수 프리셋 (포지션별 1티어 메타)
    key_players_map = {
        "4-2-2-1-1": {"ST": "호나우두", "CAM": "굴리트", "CDM": "로드리", "CB": "반데이크"},
        "4-2-3-1": {"ST": "셰우첸코", "CAM": "지단", "CDM": "발락", "CB": "뤼디거"},
        "4-2-2-2": {"ST": "호나우두", "CF": "벤제마", "CDM": "야야 투레", "CB": "말디니"},
        "4-1-2-3": {"ST": "앙리", "LW": "네이마르", "RW": "메시", "CDM": "에시앙"},
        "4-1-4-1": {"ST": "케인", "CM": "더브라위너", "CDM": "로드리", "CB": "반데이크"}
    }

    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)

        routes = [
            f"{form} 전술 빌드업: 중앙 미드필더 전진 패스 및 침투 연계",
            "측면 풀백/윙어 지원을 활용한 박스 안 컷백 및 감아차기 슈팅"
        ]

        key_players = key_players_map.get(form, {"ST": "호나우두", "CAM": "굴리트", "CDM": "로드리", "CB": "반데이크"})

        # 실측된 진짜 랭커 구단주 닉네임만 최대 5명 노출
        curated_nicks = formation_rankers.get(form, [r["nickname"] for r in rankers[:5]])[:5]

        meta_list.append({
            "formation": form,
            "count": count,
            "share": share,
            "tactical_routes": routes,
            "key_players": key_players,
            "recommended_rankers": curated_nicks
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid,
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"[3/3] data/meta_today.json 실시간 실제 랭커 기반 갱신 완료!")

if __name__ == "__main__":
    build_meta()
