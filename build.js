const fs = require('fs');
const path = require('path');

const SHEET_ID = '1LbMwTdfLRB45dqH1pLbk2vrTXPf6vu7DvqAWCgLMeDM';
const TACTICS_CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Tactics`;
const PADS_CSV_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Pads`;

function parseCSV(text) {
  if (!text || !text.trim()) return [];
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    const next = text[i + 1];

    if (c === '"') {
      if (inQuotes && next === '"') {
        cell += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (c === ',' && !inQuotes) {
      row.push(cell.trim());
      cell = '';
    } else if ((c === '\r' || c === '\n') && !inQuotes) {
      if (c === '\r' && next === '\n') i++;
      row.push(cell.trim());
      if (row.length > 0 && row.some(v => v !== '')) rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += c;
    }
  }
  if (cell !== '' || row.length > 0) {
    row.push(cell.trim());
    if (row.some(v => v !== '')) rows.push(row);
  }
  if (rows.length <= 1) return [];

  const headers = rows[0].map(h => h.replace(/^\uFEFF/, '').replace(/^"|"$/g, '').trim());
  const data = [];

  for (let r = 1; r < rows.length; r++) {
    const rowData = rows[r];
    if (!rowData || !rowData.some(v => v !== '')) continue;
    const obj = {};
    headers.forEach((h, idx) => {
      let val = rowData[idx] || '';
      obj[h] = val.replace(/^"|"$/g, '').trim();
    });
    if (obj.playerName || obj.padName) data.push(obj);
  }
  return data;
}

function cleanSlug(val, fallback) {
  if (val && val.trim()) {
    const s = val.trim().toLowerCase().replace(/[^a-z0-9-_]/g, '-');
    if (s) return s;
  }
  return (fallback || 'item').trim().toLowerCase().replace(/[^a-z0-9-_]/g, '-');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// 시작 지점부터 종료 경계 키워드 직전까지를 통째로 잘라내는 확실한 함수
function cutBlock(html, startPattern, endPattern) {
  const startMatch = html.match(startPattern);
  if (!startMatch) return html;
  
  const startIndex = startMatch.index;
  const rest = html.slice(startIndex);
  const endMatch = rest.match(endPattern);
  
  if (!endMatch) return html;
  const endIndex = startIndex + endMatch.index;
  
  return html.slice(0, startIndex) + html.slice(endIndex);
}

// 1. 개별 전술 상세 정적 페이지 생성
function buildIndividualTacticPages(cleanTemplateHtml, tactics) {
  tactics.forEach(t => {
    const slug = cleanSlug(t.slug, t.playerName);
    const dir = path.join('tactics', slug);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    let pageHtml = cleanTemplateHtml;

    const name = escapeHtml(t.playerName || 'Player');
    const formation = escapeHtml(t.formation || 'FORMATION');
    const country = escapeHtml(t.country || 'GLOBAL');
    const version = escapeHtml(t.versionName || '-');
    const review = escapeHtml(t.reviewText || '');
    const currentUrl = `https://wiseplay.co.kr/tactics/${slug}/`;

    pageHtml = pageHtml.replace(
      /<link rel="canonical" href="[^"]*">/,
      `<link rel="canonical" href="${currentUrl}">`
    );

    pageHtml = pageHtml.replace(
      /<title>[\s\S]*?<\/title>/,
      `<title>${name} ${formation} 전술 분석 및 세팅 가이드 | WISEPLAY</title>`
    );
    pageHtml = pageHtml.replace(
      /<meta\s+name="description"[^>]*>/i,
      `<meta name="description" id="metaDesc" content="${name} 선수의 ${formation} 포메이션 배치도, 개인 전술, 팀 전술 및 인게임 운영 심층 분석 - WISEPLAY">`
    );

    pageHtml = pageHtml.replace(
      /<span[^>]*id="viewFormation"[^>]*>[\s\S]*?<\/span>/,
      `<span class="card-badge" id="viewFormation">${formation}</span>`
    );
    pageHtml = pageHtml.replace(
      /<h2[^>]*id="viewPlayerName"[^>]*>[\s\S]*?<\/h2>/,
      `<h2 id="viewPlayerName">${name}</h2>`
    );
    pageHtml = pageHtml.replace(
      /<p[^>]*id="viewSubInfo"[^>]*>[\s\S]*?<\/p>/,
      `<p id="viewSubInfo">${country} | ${version}</p>`
    );
    pageHtml = pageHtml.replace(
      /<img[^>]*id="viewImgDisplay"[^>]*>/,
      `<img id="viewImgDisplay" class="view-display-img" src="${t.imgFormation || '/logo.png'}" alt="${name} 전술">`
    );
    pageHtml = pageHtml.replace(
      /<p[^>]*id="viewReviewText"[^>]*>[\s\S]*?<\/p>/,
      `<p id="viewReviewText" style="white-space:pre-line;">${review}</p>`
    );

    if (t.padName && t.padName.trim() !== '' && t.padName.trim() !== '-') {
      const pName = escapeHtml(t.padName);
      pageHtml = pageHtml.replace(
        /<span id="viewPadNameText">[\s\S]*?<\/span>/,
        `<span id="viewPadNameText">${pName}</span>`
      );
    } else {
      pageHtml = pageHtml.replace(/<div class="detail-section" id="viewPadSection"[\s\S]*?<\/div>\s*<\/div>/, '');
    }

    pageHtml = pageHtml.replace(
      'id="detail-view-tactics" class="detail-view-container"',
      'id="detail-view-tactics" class="detail-view-container" style="display:block;"'
    );

    // [전술 상세 핵심]
    // detail-view-pads(패드 빈 템플릿)의 시작점부터 <footer> 태그 시작점 바로 앞까지의 모든 영역을 통째로 도려냅니다.
    pageHtml = cutBlock(
      pageHtml,
      /<div[^>]*id=["']detail-view-pads["'][^>]*>/i,
      /<footer/i
    );

    fs.writeFileSync(path.join(dir, 'index.html'), pageHtml, 'utf8');
  });
  console.log(`개별 전술 정적 페이지 ${tactics.length}개 정밀 생성 완료!`);
}

// 2. 개별 컨트롤러 상세 정적 페이지 생성
function buildIndividualPadPages(cleanTemplateHtml, pads) {
  pads.forEach(p => {
    const slug = cleanSlug(p.slug, p.padName);
    const dir = path.join('controllers', slug);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    let pageHtml = cleanTemplateHtml;

    const name = escapeHtml(p.padName || 'Gamepad');
    const mech = escapeHtml(p.stickMech || '-');
    const score = escapeHtml(p.metaScore || '80');
    const intro = escapeHtml(p.padIntro || p.pros || '실측 데이터 기반 정밀 벤치마크 리뷰');
    const pros = escapeHtml(p.pros || '-');
    const cons = escapeHtml(p.cons || '-');
    const currentUrl = `https://wiseplay.co.kr/controllers/${slug}/`;

    pageHtml = pageHtml.replace(
      /<link rel="canonical" href="[^"]*">/,
      `<link rel="canonical" href="${currentUrl}">`
    );

    pageHtml = pageHtml.replace(
      /<title>[\s\S]*?<\/title>/,
      `<title>${name} 레이턴시·폴링레이트 실측 벤치마크 스펙 | WISEPLAY</title>`
    );
    pageHtml = pageHtml.replace(
      /<meta\s+name="description"[^>]*>/i,
      `<meta name="description" id="metaDesc" content="${name} (${mech}) 유선·무선 폴링레이트, 스틱 및 버튼 인풋랙 정밀 계측 벤치마크 분석 - WISEPLAY">`
    );

    pageHtml = pageHtml.replace(
      /<h2[^>]*id="viewPadName"[^>]*>[\s\S]*?<\/h2>/,
      `<h2 id="viewPadName">${name}</h2>`
    );
    pageHtml = pageHtml.replace(
      /<p[^>]*id="viewPadSub"[^>]*>[\s\S]*?<\/p>/,
      `<p id="viewPadSub">스틱 방식: ${mech} | 키매핑: ${escapeHtml(p.keyMap || '-')} | 매크로: ${escapeHtml(p.macro || '-')}</p>`
    );
    pageHtml = pageHtml.replace(
      /<span[^>]*id="viewPadScoreVal"[^>]*>[\s\S]*?<\/span>/,
      `<span class="dash-big-num lj" id="viewPadScoreVal">${score}</span>`
    );
    pageHtml = pageHtml.replace(
      /<p[^>]*id="viewPadIntroText"[^>]*>[\s\S]*?<\/p>/,
      `<p id="viewPadIntroText" style="white-space:pre-line;">${intro}</p>`
    );
    pageHtml = pageHtml.replace(
      /<span[^>]*id="viewPadPros"[^>]*>[\s\S]*?<\/span>/,
      `<span id="viewPadPros">${pros}</span>`
    );
    pageHtml = pageHtml.replace(
      /<span[^>]*id="viewPadCons"[^>]*>[\s\S]*?<\/span>/,
      `<span id="viewPadCons">${cons}</span>`
    );

    pageHtml = pageHtml.replace(
      'id="detail-view-pads" class="detail-view-container"',
      'id="detail-view-pads" class="detail-view-container" style="display:block;"'
    );

    // [패드 상세 핵심]
    // 1) 앞쪽에 위치한 detail-view-tactics(전술 템플릿)의 시작부터 detail-view-pads 바로 앞까지 도려냅니다.
    pageHtml = cutBlock(
      pageHtml,
      /<div[^>]*id=["']detail-view-tactics["'][^>]*>/i,
      /<div[^>]*id=["']detail-view-pads["'][^>]*>/i
    );

    // 2) 패드 상세 뒤에 나오는 메인 목록 영역부터 <footer> 직전까지 도려냅니다.
    pageHtml = cutBlock(
      pageHtml,
      /<section[^>]*id=["']section-tactics["'][^>]*>|<section[^>]*class=["'][^"']*tactic/i,
      /<footer/i
    );

    fs.writeFileSync(path.join(dir, 'index.html'), pageHtml, 'utf8');
  });
  console.log(`개별 컨트롤러 정적 페이지 ${pads.length}개 정밀 생성 완료!`);
}

async function runBuild() {
  console.log('1. 구글 시트에서 CSV 데이터를 가져오는 중...');
  const [tacticsRes, padsRes] = await Promise.all([
    fetch(TACTICS_CSV_URL),
    fetch(PADS_CSV_URL)
  ]);

  if (!tacticsRes.ok) throw new Error(`Tactics 시트 로드 실패: ${tacticsRes.status}`);
  if (!padsRes.ok) throw new Error(`Pads 시트 로드 실패: ${padsRes.status}`);

  const tacticsText = await tacticsRes.text();
  const padsText = await padsRes.text();

  const tactics = parseCSV(tacticsText);
  const pads = parseCSV(padsText);

  console.log(`파싱 완료: 전술 ${tactics.length}개, 패드 ${pads.length}개`);

  const rawTemplate = fs.readFileSync('index.html', 'utf8');

  // 이전 빌드 잔재 클린업
  ['tactics', 'controllers'].forEach(baseDir => {
    if (fs.existsSync(baseDir)) {
      fs.readdirSync(baseDir).forEach(sub => {
        const subPath = path.join(baseDir, sub);
        try {
          if (fs.statSync(subPath).isDirectory()) {
            fs.rmSync(subPath, { recursive: true, force: true });
          }
        } catch (e) {}
      });
    }
  });
  console.log('기존 개별 상세 폴더 클린업 완료!');

  // 1) 개별 상세 정적 페이지 생성
  buildIndividualTacticPages(rawTemplate, tactics);
  buildIndividualPadPages(rawTemplate, pads);

  // 2) 메인 홈 index.html: 데이터 프리로드 주입
  let homeHtml = rawTemplate;

  const dStart = '/* SSG_DATA_START */';
  const dEnd = '/* SSG_DATA_END */';
  if (homeHtml.includes(dStart) && homeHtml.includes(dEnd)) {
    const b = homeHtml.substring(0, homeHtml.indexOf(dStart) + dStart.length);
    const a = homeHtml.substring(homeHtml.indexOf(dEnd));
    const dataContent = `\n    window.__PRELOADED_TACTICS__ = ${JSON.stringify(tactics)};\n    window.__PRELOADED_PADS__ = ${JSON.stringify(pads)};\n    `;
    homeHtml = b + dataContent + a;
  }

  fs.writeFileSync('index.html', homeHtml, 'utf8');
  console.log('메인 index.html 정상 업데이트 완료!');
}

runBuild().catch(err => {
  console.error('빌드 중 오류 발생:', err);
  process.exit(1);
});
