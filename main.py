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

        for page_num in range(1, 6):
            if page_num > 1:
                print(f"  -> {page_num}페이지 전환 시도...")
                prev_first_nick = ranker_data[0]["nickname"] if ranker_data else ""
                
                # 페이징 클릭
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

                # 데이터가 새 페이지로 바뀔 때까지 충분히 대기
                time.sleep(3.5)

            # 브라우저 DOM 안에서 직접 파싱 (행 단위 1:1 완벽 매칭)
            extracted_items = page.evaluate("""() => {
                const results = [];
                // 순위표 행 탐색
                const rows = document.querySelectorAll('tbody tr, .rank_list .tr, .tbody .tr, tr');
                
                rows.forEach(row => {
                    const text = row.innerText || '';
                    // 포메이션 정규식 매칭 (예: 4-2-2-2, 4-2-3-1, 4-1-2-3 등)
                    const formMatch = text.match(/\\b(\\d-\\d(?:-\\d){1,2})\\b/);
                    if (!formMatch) return;
                    
                    // 닉네임 탐색: 링크 태그 또는 특정 클래스 우선 추출
                    let nickname = '';
                    const linkElem = row.querySelector('a[href*="profile"], a[onclick*="Profile"], .coach_name, .name, .profile_pointer');
                    if (linkElem) {
                        nickname = linkElem.innerText.trim();
                    } else {
                        // 텍스트 블록에서 숫자나 일반 UI 단어가 아닌 첫 번째 문자열 추적
                        const tokens = text.split(/\\s+/);
                        for (let t of tokens) {
                            if (t.length >= 2 && !t.match(/^\\d+$/) && !['슈퍼챔피언스','챔피언스','상세보기','포메이션','승률'].includes(t) && !t.includes('%')) {
                                nickname = t;
                                break;
                            }
                        }
                    }
                    
                    if (nickname && nickname.length >= 2) {
                        results.push({
                            nickname: nickname,
                            formation: formMatch[1]
                        });
                    }
                });
                return results;
            }""")

            # 수집된 항목 중복 배제하며 누적
            new_added = 0
            for item in extracted_items:
                nick = item["nickname"]
                form = item["formation"]
                if not any(r["nickname"] == nick for r in ranker_data):
                    ranker_data.append({"nickname": nick, "formation": form})
                    new_added += 1

            print(f"  => {page_num}페이지 처리 완료: 이번 페이지 +{new_added}명 추가 (총 누적: {len(ranker_data)}명)")

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

    # 1. 수집된 랭커들의 포메이션 실측 카운팅
    formation_counter = Counter([r["formation"] for r in rankers])
    formation_rankers = {}
    for r in rankers:
        formation_rankers.setdefault(r["formation"], []).append(r["nickname"])

    # 2. 포지션별 대표 메타 선수 매핑
    key_players_map = {
        "4-2-2-2": {"ST": "호나우두", "CF": "굴리트", "CDM": "로드리", "CB": "반데이크"},
        "4-2-2-1-1": {"ST": "셰우첸코", "CAM": "굴리트", "CDM": "발락", "CB": "뤼디거"},
        "4-2-3-1": {"ST": "호나우두", "CAM": "지단", "CDM": "야야 투레", "CB": "말디니"},
        "4-1-2-3": {"ST": "앙리", "LW": "네이마르", "RW": "메시", "CDM": "에시앙"},
        "4-1-4-1": {"ST": "케인", "CM": "더브라위너", "CDM": "로드리", "CB": "반데이크"}
    }

    meta_list = []
    # 최다 사용 포메이션 순으로 정렬
    for form, count in formation_counter.most_common(5):
        share = round((count / total_valid) * 100, 1)

        routes = [
            f"{form} 실측 메타: 중앙 미드필더 전진 패스 및 침투 연계",
            "측면 풀백/윙어 지원을 활용한 박스 안 컷백 및 감아차기 득점"
        ]

        actual_rankers = formation_rankers.get(form, [])[:5]

        meta_list.append({
            "formation": form,
            "count": count,       # 실측된 실제 인원수
            "share": share,       # 실측된 실제 점유율 (%)
            "tactical_routes": routes,
            "key_players": key_players_map.get(form, {"ST": "호나우두", "CAM": "굴리트", "CDM": "로드리", "CB": "반데이크"}),
            "recommended_rankers": actual_rankers
        })

    result_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rankers": total_valid, # 실측된 총원 (100)
        "meta_list": meta_list
    }

    os.makedirs("data", exist_ok=True)
    with open("data/meta_today.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"  => data/meta_today.json 실측 데이터 저장 완료! (총 {total_valid}명)")

if __name__ == "__main__":
    process_and_save()
