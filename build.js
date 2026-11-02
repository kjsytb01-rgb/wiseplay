// 각 선수 전술별 개별 정적 HTML 파일 생성 함수 (확실한 타겟팅 주입)
function buildIndividualTacticPages(baseHtml, tactics) {
  tactics.forEach(t => {
    const slug = cleanSlug(t.slug, t.playerName);
    const dir = path.join('tactics', slug);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    let pageHtml = baseHtml;

    const name = escapeHtml(t.playerName || 'Player');
    const formation = escapeHtml(t.formation || 'FORMATION');
    const country = escapeHtml(t.country || 'GLOBAL');
    const version = escapeHtml(t.versionName || '-');
    const review = escapeHtml(t.reviewText || '');

    // 1. 타이틀 및 메타 태그 교체
    pageHtml = pageHtml.replace(
      /<title>[\s\S]*?<\/title>/,
      `<title>${name} ${formation} 전술 분석 및 세팅 가이드 | WISEPLAY</title>`
    );
    pageHtml = pageHtml.replace(
      /<meta name="description" id="metaDesc" content="[\s\S]*?">/,
      `<meta name="description" id="metaDesc" content="${name} 선수의 ${formation} 포메이션 배치도, 개인 전술, 팀 전술 및 인게임 운영 심층 분석 - WISEPLAY">`
    );

    // 2. 상단 상세 뷰(detail-view-tactics) 내부의 값들을 해당 선수(DIKE 등)의 고유 데이터로 정확히 교체
    pageHtml = pageHtml.replace(
      /<span class="card-badge" id="viewFormation">[\s\S]*?<\/span>/,
      `<span class="card-badge" id="viewFormation">${formation}</span>`
    );
    pageHtml = pageHtml.replace(
      /<h2 id="viewPlayerName">[\s\S]*?<\/h2>/,
      `<h2 id="viewPlayerName">${name}</h2>`
    );
    pageHtml = pageHtml.replace(
      /<p id="viewSubInfo">[\s\S]*?<\/p>/,
      `<p id="viewSubInfo">${country} | ${version}</p>`
    );
    pageHtml = pageHtml.replace(
      /<p id="viewReviewText">[\s\S]*?<\/p>/,
      `<p id="viewReviewText" style="white-space:pre-line;">${review}</p>`
    );

    // 3. 상세 페이지에서는 목록 섹션을 끄고 상세 뷰만 바로 표시
    pageHtml = pageHtml.replace(
      'id="detail-view-tactics" class="detail-view-container"',
      'id="detail-view-tactics" class="detail-view-container" style="display:block;"'
    );
    pageHtml = pageHtml.replace('id="section-tactics"', 'id="section-tactics" style="display:none;"');
    pageHtml = pageHtml.replace('id="section-latest-videos"', 'id="section-latest-videos" style="display:none;"');
    pageHtml = pageHtml.replace('id="section-tactics-ranking"', 'id="section-tactics-ranking" style="display:none;"');
    pageHtml = pageHtml.replace('id="section-editorial-guide"', 'id="section-editorial-guide" style="display:none;"');

    fs.writeFileSync(path.join(dir, 'index.html'), pageHtml, 'utf8');
  });
  console.log(`개별 전술 정적 페이지 ${tactics.length}개 정밀 생성 완료!`);
}
