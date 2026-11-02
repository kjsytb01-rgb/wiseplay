const fs = require('fs');

// index.html에서 사용 중인 구글 시트 CSV URL을 여기에 똑같이 입력합니다.
const TACTICS_CSV_URL = '여기에_Tactics_구글시트_CSV_링크_입력';
const PADS_CSV_URL = '여기에_Pads_구글시트_CSV_링크_입력';

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

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// 크롤러와 초기 화면을 위한 정적 전술 카드 및 본문 HTML 생성
function generateTacticsHTML(tactics) {
  return tactics.map(t => {
    const name = escapeHtml(t.playerName || '');
    const team = escapeHtml(t.team || '');
    const formation = escapeHtml(t.formation || '');
    const score = escapeHtml(t.score || '85');
    const summary = escapeHtml(t.summary || t.oneLineReview || '');
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

// 크롤러와 초기 화면을 위한 정적 패드 벤치마크 HTML 생성
function generatePadsHTML(pads) {
  return pads.map(p => {
    const padName = escapeHtml(p.padName || '');
    const score = escapeHtml(p.score || '');
    const summary = escapeHtml(p.summary || p.reviewText || '');
    const polling = escapeHtml(p.pollingRate || '-');
    const sensor = escapeHtml(p.stickSensor || p.sensor || '-');

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

  // 1) 정적 HTML 카드 주입 (애드센스 봇 & 검색엔진 크롤러용 100% 정적 본문)
  const tacticsStaticHTML = generateTacticsHTML(tactics);
  const padsStaticHTML = generatePadsHTML(pads);

  html = html.replace(
    /<!-- SSG_TACTICS_START -->[\s\S]*?<!-- SSG_TACTICS_END -->/,
    `<!-- SSG_TACTICS_START -->\n${tacticsStaticHTML}\n<!-- SSG_TACTICS_END -->`
  );

  html = html.replace(
    /<!-- SSG_PADS_START -->[\s\S]*?<!-- SSG_PADS_END -->/,
    `<!-- SSG_PADS_START -->\n${padsStaticHTML}\n<!-- SSG_PADS_END -->`
  );

  // 2) 프리로드 JSON 데이터 주입 (브라우저 0.1초 즉시 렌더링용)
  const dataScript = `/* SSG_DATA_START */\n  window.__PRELOADED_TACTICS__ = ${JSON.stringify(tactics)};\n  window.__PRELOADED_PADS__ = ${JSON.stringify(pads)};\n  /* SSG_DATA_END */`;
  html = html.replace(
    /\/\* SSG_DATA_START \*\/[\s\S]*?\/\* SSG_DATA_END \*\//,
    dataScript
  );

  fs.writeFileSync('index.html', html, 'utf8');
  console.log('index.html 정적 빌드(SSG) 업데이트 완료!');
}

runBuild().catch(err => {
  console.error('빌드 중 오류 발생:', err);
  process.exit(1);
});
