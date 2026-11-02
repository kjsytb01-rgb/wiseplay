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

function generateTacticsHTML(tactics) {
  return tactics.map(t => {
    const name = escapeHtml(t.playerName || '');
    const team = escapeHtml(t.team || '');
    const formation = escapeHtml(t.formation || '');
    const score = escapeHtml(t.score || t.wiseScore || '85');
    const summary = escapeHtml(t.summary || t.oneLineReview || t.oneLine || '');
    const review = escapeHtml(t.reviewText || '');

    return `
    <article class="static-tactic-card" style="background:#14171c; border:1px solid #262b33; border-radius:12px; padding:20px; margin-bottom:16px;">
      <header style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span style="background:#00e67622; color:#00e676; padding:4px 8px; border-radius:4px; font-weight:700; font-size:13px;">${formation}</span>
        <span style="background:#00e676; color:#000; font-weight:800; padding:4px 8px; border-radius:6px;">WISE SCORE ${score}</span>
      </header>
      <h3 style="margin:0 0 8px 0; font-size:18px; color:#fff;">${name} ${team ? `(${team})` : ''} - ${formation} 실전 전술 분석</h3>
      <p style="color:#b0b8c1; font-size:14px; line-height:1.6; margin-bottom:12px;"><strong>핵심 요약:</strong> ${summary}</p>
      <div class="tactic-full-review" style="color:#9aa4b0; font-size:13px; line-height:1.7; white-space:pre-line; border-top:1px solid #262b33; padding-top:12px;">${review}</div>
    </article>`;
  }).join('\n');
}

function generatePadsHTML(pads) {
  return pads.map(p => {
    const padName = escapeHtml(p.padName || '');
    const score = escapeHtml(p.score || p.metaScore || '');
    const summary = escapeHtml(p.summary || p.padIntro || p.pros || '');
    const polling = escapeHtml(p.pollingRate || p.wPoll || '-');
    const sensor = escapeHtml(p.stickSensor || p.stickMech || '-');

    return `
    <article class="static-pad-card" style="background:#14171c; border:1px solid #262b33; border-radius:12px; padding:20px; margin-bottom:16px;">
      <h3 style="margin:0 0 8px 0; font-size:18px; color:#fff;">${padName} (벤치마크 점수: ${score})</h3>
      <ul style="color:#b0b8c1; font-size:13px; line-height:1.6; margin:0 0 10px 0; padding-left:18px;">
        <li>스틱 센서: ${sensor}</li>
        <li>폴링레이트 및 입력지연 스펙: ${polling}</li>
      </ul>
      <p style="color:#9aa4b0; font-size:13px; line-height:1.7; white-space:pre-line;">${summary}</p>
    </article>`;
  }).join('\n');
}

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

    pageHtml = pageHtml.replace(
      /<title>[\s\S]*?<\/title>/,
      `<title>${name} ${formation} 전술 분석 및 세팅 가이드 | WISEPLAY</title>`
    );
    pageHtml = pageHtml.replace(
      /<meta name="description" id="metaDesc" content="[\s\S]*?">/,
      `<meta name="description" id="metaDesc" content="${name} 선수의 ${formation} 포메이션 배치도, 개인 전술, 팀 전술 및 인게임 운영 심층 분석 - WISEPLAY">`
    );

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

async function runBuild() {
  console.log('1. 구글 시트에서 CSV 데이터를 가져오는 중...');
  const [tacticsRes, padsRes] = await Promise.all([
    fetch(TACTICS_CSV_URL),
    fetch(PADS_CSV_URL)
  ]);

  const tacticsText = await tacticsRes.text();
  const padsText = await padsRes.text();

  const tactics = parseCSV(tacticsText);
  const pads = parseCSV(padsText);

  console.log(`파싱 완료: 전술 ${tactics.length}개, 패드 ${pads.length}개`);

  let html = fs.readFileSync('index.html', 'utf8');

  // 1) HTML 정적 카드 주입
  const tStart = '<!-- SSG_TACTICS_START -->';
  const tEnd = '<!-- SSG_TACTICS_END -->';
  if (html.includes(tStart) && html.includes(tEnd)) {
    const b = html.substring(0, html.indexOf(tStart) + tStart.length);
    const a = html.substring(html.indexOf(tEnd));
    html = b + '\n' + generateTacticsHTML(tactics) + '\n' + a;
  }

  const pStart = '<!-- SSG_PADS_START -->';
  const pEnd = '<!-- SSG_PADS_END -->';
  if (html.includes(pStart) && html.includes(pEnd)) {
    const b = html.substring(0, html.indexOf(pStart) + pStart.length);
    const a = html.substring(html.indexOf(pEnd));
    html = b + '\n' + generatePadsHTML(pads) + '\n' + a;
  }

  // 2) JavaScript 프리로드 데이터 주입
  const dStart = '/* SSG_DATA_START */';
  const dEnd = '/* SSG_DATA_END */';
  if (html.includes(dStart) && html.includes(dEnd)) {
    const b = html.substring(0, html.indexOf(dStart) + dStart.length);
    const a = html.substring(html.indexOf(dEnd));
    const dataContent = `\n    window.__PRELOADED_TACTICS__ = ${JSON.stringify(tactics)};\n    window.__PRELOADED_PADS__ = ${JSON.stringify(pads)};\n    `;
    html = b + dataContent + a;
    console.log('JavaScript 프리로드 데이터 주입 완료!');
  } else {
    console.error('SSG_DATA 마커를 찾지 못했습니다.');
  }

  fs.writeFileSync('index.html', html, 'utf8');
  console.log('메인 index.html 업데이트 완료!');

  buildIndividualTacticPages(html, tactics);
}

runBuild().catch(err => {
  console.error('빌드 중 오류 발생:', err);
  process.exit(1);
});
