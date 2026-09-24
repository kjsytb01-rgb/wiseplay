import os
import re
import json
import time
from datetime import datetime
from collections import Counter
from playwright.sync_api import sync_playwright

def collect_real_top100_playwright():
    print("[1/2] 헤드리스 크롬 가동 및 넥슨 공식 순위표 실시간 1~100위 전수 수집 시작...")
    
    ranker_data = [] # [{"nickname": "...", "formation": "..."}, ...]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        print("  -> 넥슨 데이터센터 랭킹 페이지 접속 중...")
        page.goto("https://fconline.nexon.com/datacenter/rank", wait_until="networkidle", timeout=60000)
        time.sleep(3)

        # 1페이지부터 5페이지까지 순차 수집 (한 페이지당 20명 = 총 100명)
        for page_num in range(1, 6):
            if page_num > 1:
                print(f"  -> {page_num}페이지 전환 시도...")
                clicked = False
                
                # 정밀 타겟팅: 하단 페이징 영역 안의 a 태그만 클릭
                selectors = [
                    f".paginate a:has-text('{page_num}')",
                    f".paging a:has-text('{page_num}')",
                    f".pagination a:has-text('{page_num}')",
                    f"div[class*='page'] a:has-text('{page_num}')"
                ]
                
                for sel in selectors:
                    try:
                        elem = page.query_selector(sel)
                        if elem and elem.is_visible():
                            elem.click()
                            page.wait_for_timeout(2500)
                            clicked = True
                            print(f"  -> 셀렉터 ({sel}) 클릭 성공")
                            break
                    except Exception:
                        pass

                # 셀렉터 클릭이 안 먹힐 경우 넥슨 내부 페이징 자바스크립트 직접 실행
                if not clicked:
                    try:
                        page.evaluate(f"""() => {{
                            if (typeof window.GetRankList === 'function') {{
                                window.GetRankList(50, {page_num});
                            }} else if (typeof window.ChangePage === 'function') {{
                                window.ChangePage({page_num});
                            }} else {{
                                const links = Array.from(document.querySelectorAll('a'));
                                const target = links.find(a => a.textContent.trim() === '{page_num}');
                                if (target) target.click();
                            }}
                        }}""")
                        page.wait_for_timeout(2500)
                    except Exception as e:
                        print(f"  [경고] {page_num}페이지 자바스크립트 호출 실패: {e}")

            # 현재 페이지 화면에서 순위표 행 파싱
            text_all = page.inner_text("body")
            
            # 패턴: 순위(1~100) + 공백 + 레벨(선택) + 구단주명 + 포메이션(4-X-X)
            # 텍스트 라인 기반 정밀 추출
            lines = [l.strip() for l in text_all.split('\n') if l.strip()]
            for i, line in enumerate(lines):
                # 포메이션이 적힌 라인을 발견했을 때
                form_match = re.search(r'\b(\d-\d(?:-\d){1,2})\b', line)
                if form_match:
                    formation = form_match.group(1)
                    # 바로 위 몇 줄 중에서 닉네임 찾기
                    nick = None
                    for offset in range(1, 6):
                        if i - offset >= 0:
                            cand = lines[i - offset]
                            if len(cand) >= 2 and not cand.isdigit() and cand not in ["슈퍼챔피언스", "챔피언스", "포메이션", "상세보기", "승률"] and not re.search(r'\b\d-\d\b', cand) and "%" not in cand:
                                nick = cand.split()[0]
                                break
                    if nick and not any(r["nickname"] == nick for r in ranker_data):
                        ranker_data.append({"nickname": nick, "formation": formation})

            print(f"  => {page_num}페이지 수집 후 누적: {len(ranker_data)}명")

        browser.close()

    print(f"  => 최종 실시간 실측 수집 랭커 총원: {len(ranker_data)}명")
    return ranker_data

def process_and_save():
    rankers = collect_real_top100_playwright()

    if not rankers:
        print("[오류] 실제 랭커 데이터를 수집하지 못했습니다.")
        return

    total_valid = len(rankers)
    print(f"[2/2] 실측 데이터 집계 중 (실제 표본: {total_valid}명)")

    # 실제 수집된 랭커들의 포메이션 사용 횟수 실측 카운팅
    formation_counter = Counter([r["formation"] for r in rankers])
    formation_rankers = {}
    for r in rankers:
        formation_rankers.setdefault(r["formation"], []).append(r["nickname"])

    # 포지션별 1티어 기준 선수 매핑
    key_players_map = {
        "4-2-2-2": {"ST": "호나우두", "CF": "굴리트", "CDM": "로드리", "CB": "반데이크"},
        "4-2-2-1-1": {"ST": "셰우첸코", "CAM": "굴리트", "CDM": "발락", "CB": "뤼디거"},
        "4-2-3-1": {"ST": "호나우두", "CAM": "지단", "CDM": "야야 투레", "CB": "말디니"},
        "4-1-2-3": {"ST": "앙리", "LW": "네이마르", "RW": "메시", "CDM": "에시앙"},
        "4-1-4-1": {"ST": "케인", "CM": "더브라위너", "CDM": "로드리", "CB": "반데이크"}
    }

    meta_list = []
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)

        routes = [
            f"{form} 실측 메타: 중앙 미드필더와 전방 침투 연계",
            "측면 전환 후 빠른 컷백 및 박스 침투 마무리"
        ]

        actual_rankers = formation_rankers.get(form, [])[:5]

        meta_list.append({
            "formation": form,
            "count": count,
            "share": share,
            "tactical_routes": routes,
            "key_players": key_players_map.get(form, {"ST": "호나우두", "CAM": "굴리트", "CDM": "로드리", "CB": "반데이크"}),
            "recommended_rankers": actual_rankers
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid,
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"  => data/meta_today.json 실측 데이터 저장 완료! (총 {total_valid}명)")

if __name__ == "__main__":
    process_and_save()
