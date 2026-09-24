import os
import re
import json
import time
from datetime import datetime
from collections import Counter
from playwright.sync_api import sync_playwright

def collect_real_top100_playwright():
    print("[1/2] 헤드리스 크롬 가동 및 넥슨 공식 순위표 실시간 1~100위 전수 수집 시작...")
    
    ranker_data = [] # 실측 수집 리스트: [{"rank": 1, "nickname": "...", "formation": "..."}, ...]

    with sync_playwright() as p:
        # 브라우저 실행 (실제 크롬 환경과 동일)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        print("  -> 넥슨 데이터센터 랭킹 페이지 접속 중...")
        page.goto("https://fconline.nexon.com/datacenter/rank", wait_until="networkidle", timeout=60000)
        time.sleep(2)

        # 1페이지부터 5페이지까지 실제 클릭하면서 20명씩 수집 (총 100명)
        for page_num in range(1, 6):
            if page_num > 1:
                print(f"  -> {page_num}페이지 버튼 클릭 및 전환 대기...")
                # 페이지 번호 링크 클릭 (페이지네이션 엘리먼트 클릭)
                try:
                    page.click(f"a:has-text('{page_num}')", timeout=5000)
                    page.wait_for_timeout(2000) # 비동기 렌더링 완료 대기
                except Exception as e:
                    print(f"  [경고] {page_num}페이지 클릭 재시도 중: {e}")
                    # 페이지 스크립트 실행으로 전환
                    page.evaluate(f"window.GetRankList && window.GetRankList(50, {page_num})")
                    page.wait_for_timeout(2000)

            # 현재 페이지 화면의 전체 텍스트 및 HTML 파싱
            content = page.content()
            
            # 행 단위 구단주 및 포메이션 파싱
            # 넥슨 데이터센터 순위표 아이템 셀 추출
            # 정규식 패턴: 순위(1~100) + 닉네임 + 포메이션(예: 4-2-2-2)
            # DOM 셀 셀렉터로 직접 추출
            rows = page.query_selector_all(".tr, tr, .rank_list li")
            page_extracted = 0

            for r in rows:
                txt = r.inner_text().strip()
                if not txt:
                    continue
                
                # 포메이션 감지 (4-2-3-1, 4-2-2-2, 4-1-2-3 등)
                form_match = re.search(r'\b(\d-\d(?:-\d){1,2})\b', txt)
                if not form_match:
                    continue
                formation = form_match.group(1)

                # 구단주명 추출 (링크 또는 텍스트 내에서 추출)
                lines = [line.strip() for line in txt.split('\n') if line.strip()]
                nick = None
                for line in lines:
                    # 순위 숫자나 레벨, 경기수, 승률이 아닌 순수 닉네임 라인 탐색
                    if len(line) >= 2 and not line.isdigit() and line not in ["슈퍼챔피언스", "챔피언스", "포메이션", "상세보기", "승률"] and not re.search(r'\d-\d', line) and "%" not in line:
                        nick = line.split()[0]
                        break

                if nick and not any(x["nickname"] == nick for x in ranker_data):
                    ranker_data.append({"nickname": nick, "formation": formation})
                    page_extracted += 1

            # 만약 개별 셀렉터가 어긋난 경우 텍스트 전체 블록에서 정규식 보정
            if page_extracted == 0:
                text_all = page.inner_text("body")
                matches = re.findall(r'(\d{1,3})\s+(?:\d+\s+)?([A-Za-z0-9가-힣_]+)[\s\S]{1,150}?(\d-\d(?:-\d){1,2})', text_all)
                for r_num, n_cand, f_cand in matches:
                    if int(r_num) <= 100 and n_cand not in ["슈퍼챔피언스", "포메이션"] and len(n_cand) >= 2:
                        if not any(x["nickname"] == n_cand for x in ranker_data):
                            ranker_data.append({"nickname": n_cand, "formation": f_cand})

            print(f"  => {page_num}페이지 수집 완료: 현재 누적 {len(ranker_data)}명 확보")

        browser.close()

    print(f"  => 최종 실측 수집된 실시간 랭커 총원: {len(ranker_data)}명")
    return ranker_data

def process_and_save():
    rankers = collect_real_top100_playwright()

    if not rankers:
        print("[오류] 실제 랭커 데이터를 수집하지 못했습니다. 기존 파일을 유지합니다.")
        return

    total_valid = len(rankers)
    print(f"[2/2] 실측 데이터 집계 중 (실제 표본: {total_valid}명)")

    # 1. 실제 수집된 랭커들의 포메이션 사용 횟수 실측 카운팅
    formation_counter = Counter([r["formation"] for r in rankers])
    formation_rankers = {}
    for r in rankers:
        formation_rankers.setdefault(r["formation"], []).append(r["nickname"])

    # 2. 포지션별 1티어 기준 선수 매핑 (프리셋)
    key_players_map = {
        "4-2-2-2": {"ST": "호나우두", "CF": "굴리트", "CDM": "로드리", "CB": "반데이크"},
        "4-2-2-1-1": {"ST": "셰우첸코", "CAM": "굴리트", "CDM": "발락", "CB": "뤼디거"},
        "4-2-3-1": {"ST": "호나우두", "CAM": "지단", "CDM": "야야 투레", "CB": "말디니"},
        "4-1-2-3": {"ST": "앙리", "LW": "네이마르", "RW": "메시", "CDM": "에시앙"},
        "4-1-4-1": {"ST": "케인", "CM": "더브라위너", "CDM": "로드리", "CB": "반데이크"}
    }

    meta_list = []
    # 가장 많이 사용된 상위 포메이션 순으로 정렬
    for form, count in formation_counter.most_common(5):
        # 실측된 수치 그대로 % 계산
        share = round((count / total_valid) * 100, 1)

        routes = [
            f"{form} 실측 메타: 중앙 미드필더와 전방 침투 연계",
            "측면 전환 후 빠른 컷백 및 박스 침투 마무리"
        ]

        # 해당 포메이션을 '실제로 사용하고 있는' 수집된 랭커 닉네임만 상위 5명 노출
        actual_rankers_for_this_form = formation_rankers.get(form, [])[:5]

        meta_list.append({
            "formation": form,
            "count": count,       # 실측된 실제 인원수
            "share": share,       # 실측된 실제 점유율 (%)
            "tactical_routes": routes,
            "key_players": key_players_map.get(form, {"ST": "호나우두", "CAM": "굴리트", "CDM": "로드리", "CB": "반데이크"}),
            "recommended_rankers": actual_rankers_for_this_form # 100% 실측된 닉네임
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid, # 실측된 총 인원수
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"  => data/meta_today.json 실측 데이터 저장 완료! (총 {total_valid}명 전수 집계)")

if __name__ == "__main__":
    process_and_save()
