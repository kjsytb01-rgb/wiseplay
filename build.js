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
      if (inQuotes && next === '"') { cell += '"'; i++; } else { inQuotes = !inQuotes; }
    } else if (c === ',' && !inQuotes) {
      row.push(cell.trim()); cell = '';
    } else if ((c === '\r' || c === '\n') && !inQuotes) {
      if (c === '\r' && next === '\n') i++;
      row.push(cell.trim());
      if (row.length > 0 && row.some(v => v !== '')) rows.push(row);
      row = []; cell = '';
    } else { cell += c; }
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
    headers.forEach((h, idx) => { obj[h] = (rowData[idx] || '').replace(/^"|"$/g, '').trim(); });
    if (obj.playerName || obj.padName) data.push(obj);
  }
  return data;
}

function cleanSlug(val, fallback) {
  if (val && val.trim()) return val.trim().toLowerCase().replace(/[^a-z0-9-_]/g, '-');
  return (fallback || 'item').trim().toLowerCase().replace(/[^a-z0-9-_]/g, '-');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getScoreTier(scoreVal) {
  const n = Number(scoreVal) || 85;
  if (n >= 90) return { cls: 'tier-purple', barCls: 'mc-bar-p', verdict: '강력 추천', g: 94, y: 5, r: 1 };
  if (n >= 80) return { cls: 'tier-green', barCls: 'mc-bar-g', verdict: '보편적 찬사', g: 88, y: 10, r: 2 };
  if (n >= 55) return { cls: 'tier-yellow', barCls: 'mc-bar-g', verdict: '전반적으로 긍정적', g: 55, y: 35, r: 10 };
  return { cls: 'tier-red', barCls: 'mc-bar-g', verdict: '혼합 또는 평균', g: 25, y: 45, r: 30 };
}

function extractYoutubeId(url) {
  if (!url || url === '-') return null;
  const regExp = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?|shorts)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/i;
  const match = url.match(regExp);
  return match ? match[1] : null;
}

// ==========================================
// 1. 상세 페이지 클린 생성 (드롭다운 삭제 방어 로직 추가)
// ==========================================
function buildIndividualTacticPages(baseHtml, uniqueTactics, tacticsBySlug) {
  const startSec = baseHtml.indexOf('<section id="detail-view-tactics"');
  const endSec = baseHtml.indexOf('</section>', startSec);
  if (startSec === -1 || endSec === -1) return;
  const tacticSectionTemplate = baseHtml.substring(startSec, endSec + 10).replace('class="detail-view-container"', 'class="detail-view-container" style="display:block;"');
  const headerPart = baseHtml.substring(0, baseHtml.indexOf('<main>') + 6);
  const footerPart = baseHtml.substring(baseHtml.indexOf('</main>'));

  uniqueTactics.forEach(t => {
    const slug = cleanSlug(t.slug, t.playerName);
    const versions = tacticsBySlug[slug];
    const dir = path.join('tactics', slug);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    let currentHeader = headerPart
      .replace(/<link rel="canonical" href="[^"]*">/, `<link rel="canonical" href="https://wiseplay.co.kr/tactics/${slug}/">`)
      .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(t.playerName)} ${escapeHtml(t.formation)} 전술 분석 | WISEPLAY</title>`)
      .replace(/<meta\s+name="description"[^>]*>/i, `<meta name="description" id="metaDesc" content="${escapeHtml(t.playerName)} 선수의 ${escapeHtml(t.formation)} 포메이션 배치도, 개인 전술, 팀 전술 심층 분석">`);

    let scriptHtml = '';
    if (versions.length > 1) {
      const safeSlug = slug.replace(/-/g, '_');
      scriptHtml = `
        <script>
          const versions_${safeSlug} = ${JSON.stringify(versions)};
          
          // 기존 사이트 JS가 렌더링을 끝낸 직후에 드롭다운을 안전하게 삽입하는 방어 코드
          window.addEventListener('DOMContentLoaded', () => {
            const injectDropdown = () => {
              if (document.getElementById('version-dropdown-container')) return; // 이미 있으면 통과
              
              const target = document.getElementById('viewPlayerName');
              if (target) {
                const div = document.createElement('div');
                div.id = 'version-dropdown-container';
                div.style.margin = '15px 0';
                div.innerHTML = \`
                  <label style="color:#8b949e; font-size:0.9rem; margin-right:8px;">🎯 버전 선택:</label>
                  <select onchange="changeVersion_${safeSlug}(this.value)" style="padding:8px; border-radius:5px; background:#222; color:#fff; border:1px solid #444; outline:none; cursor:pointer;">
                    ${versions.map((v, i) => `<option value="${i}">${escapeHtml(v.versionName)} (${escapeHtml(v.formation)})</option>`).join('')}
                  </select>
                \`;
                // 선수 이름(KWAK) 바로 밑에 드롭다운 강제 삽입
                target.parentNode.insertBefore(div, target.nextSibling);
              }
            };
            
            // 즉시 실행 및 0.5초 뒤 한 번 더 실행 (초기화 덮어쓰기 완벽 방어)
            injectDropdown();
            setTimeout(injectDropdown, 500);
          });

          // 드롭다운 변경 시 텍스트/이미지 교체 함수
          window.changeVersion_${safeSlug} = function(idx) {
            const data = versions_${safeSlug}[idx];
            
            const formEl = document.getElementById('viewFormation');
            if(formEl) formEl.textContent = data.formation;
            
            const subEl = document.getElementById('viewSubInfo');
            if(subEl) subEl.textContent = data.country + ' | ' + data.versionName;
            
            const imgEl = document.getElementById('viewImgDisplay');
            if(imgEl) imgEl.src = data.imgFormation || '/logo.png';
            
            const revEl = document.getElementById('viewReviewText');
            if(revEl) revEl.textContent = data.reviewText;
            
            const padEl = document.getElementById('viewPadNameText');
            if(padEl && data.padName) padEl.textContent = data.padName;
          };
        </script>
      `;
    }

    let currentBody = tacticSectionTemplate
      .replace(/<span[^>]*id="viewFormation"[^>]*>[\s\S]*?<\/span>/, `<span class="card-badge" id="viewFormation">${escapeHtml(t.formation)}</span>`)
      .replace(/<h2[^>]*id="viewPlayerName"[^>]*>[\s\S]*?<\/h2>/, `<h2 id="viewPlayerName">${escapeHtml(t.playerName)}</h2>`)
      .replace(/<p[^>]*id="viewSubInfo"[^>]*>[\s\S]*?<\/p>/, `<p id="viewSubInfo">${escapeHtml(t.country)} | ${escapeHtml(t.versionName)}</p>`)
      .replace(/<img[^>]*id="viewImgDisplay"[^>]*>/, `<img id="viewImgDisplay" class="view-display-img" src="${t.imgFormation || '/logo.png'}" alt="Tactics">`)
      .replace(/<p[^>]*id="viewReviewText"[^>]*>[\s\S]*?<\/p>/, `<p id="viewReviewText" style="white-space:pre-line;">${escapeHtml(t.reviewText)}</p>`);

    // 본문 맨 아래에 스크립트 블록 주입
    currentBody += '\n' + scriptHtml;
    fs.writeFileSync(path.join(dir, 'index.html'), currentHeader + '\n' + currentBody + '\n' + footerPart, 'utf8');
  });
}

function buildIndividualPadPages(baseHtml, pads) {
  const startSec = baseHtml.indexOf('<section id="detail-view-pads"');
  const endSec = baseHtml.indexOf('</section>', startSec);
  if (startSec === -1 || endSec === -1) return;
  const padSectionTemplate = baseHtml.substring(startSec, endSec + 10).replace('class="detail-view-container"', 'class="detail-view-container" style="display:block;"');
  const headerPart = baseHtml.substring(0, baseHtml.indexOf('<main>') + 6);
  const footerPart = baseHtml.substring(baseHtml.indexOf('</main>'));

  pads.forEach(p => {
    const slug = cleanSlug(p.slug, p.padName);
    const dir = path.join('controllers', slug);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    let currentHeader = headerPart
      .replace(/<link rel="canonical" href="[^"]*">/, `<link rel="canonical" href="https://wiseplay.co.kr/controllers/${slug}/">`)
      .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(p.padName)} 레이턴시 실측 벤치마크 | WISEPLAY</title>`)
      .replace(/<meta\s+name="description"[^>]*>/i, `<meta name="description" id="metaDesc" content="${escapeHtml(p.padName)} (${escapeHtml(p.stickMech)}) 유무선 폴링레이트 및 인풋랙 계측 벤치마크">`);

    let currentBody = padSectionTemplate
      .replace(/<h2[^>]*id="viewPadName"[^>]*>[\s\S]*?<\/h2>/, `<h2 id="viewPadName">${escapeHtml(p.padName)}</h2>`)
      .replace(/<p[^>]*id="viewPadSub"[^>]*>[\s\S]*?<\/p>/, `<p id="viewPadSub">스틱 방식: ${escapeHtml(p.stickMech)} | 키매핑: ${escapeHtml(p.keyMap)} | 매크로: ${escapeHtml(p.macro)}</p>`)
      .replace(/<span[^>]*id="viewPadScoreVal"[^>]*>[\s\S]*?<\/span>/, `<span class="dash-big-num lj" id="viewPadScoreVal">${escapeHtml(p.metaScore || '80')}</span>`)
      .replace(/<p[^>]*id="viewPadIntroText"[^>]*>[\s\S]*?<\/p>/, `<p id="viewPadIntroText" style="white-space:pre-line;">${escapeHtml(p.padIntro || p.pros)}</p>`);

    fs.writeFileSync(path.join(dir, 'index.html'), currentHeader + '\n' + currentBody + '\n' + footerPart, 'utf8');
  });
}

function generateStaticTacticsCards(uniqueTactics) {
  return uniqueTactics.map(item => {
    const slug = cleanSlug(item.slug, item.playerName);
    const pageUrl = `/tactics/${slug}/`;
    const wScore = item.wiseScore || '85';
    const tier = getScoreTier(wScore);
    
    return `
      <a href="${pageUrl}" class="card">
        <div class="mc-top-cap ${tier.cls}">
          <div class="card-img-wrapper">
            <img src="${item.imgFormation || '/logo.png'}" alt="Tactics">
          </div>
        </div>
        <div class="card-body">
          <span class="card-badge">${escapeHtml(item.formation)}</span>
          <h3 class="card-title">${escapeHtml(item.playerName)} <small style="color:#8b949e; font-size:0.8rem;">(${escapeHtml(item.country)})</small></h3>
          <div class="tactic-cta-box"><span>📋 개인·팀 전술 세팅 및 분석 보기 →</span></div>
          <div class="mc-score-row">
            <div class="mc-score-text">
              <span class="mc-score-label">WISE SCORE</span>
              <span class="mc-score-verdict">${tier.verdict}</span>
            </div>
            <div class="mc-score-box ${tier.cls}">${wScore}</div>
          </div>
        </div>
      </a>`;
  }).join('\n');
}

function generateStaticPadsCards(pads) {
  return pads.map(pad => {
    const slug = cleanSlug(pad.slug, pad.padName);
    const pageUrl = `/controllers/${slug}/`;
    const score = pad.metaScore || '80';
    const tier = getScoreTier(score);
    const ytId = extractYoutubeId(pad.ytUrl);
    const cardThumb = pad.imgUrl || (ytId ? `https://img.youtube.com/vi/${ytId}/hqdefault.jpg` : '/logo.png');

    return `
      <a href="${pageUrl}" class="card">
        <div class="mc-top-cap ${tier.cls}">
          <div class="card-img-wrapper"><img src="${cardThumb}" alt="Pad"></div>
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(pad.padName)}</h3>
          <div class="tactic-cta-box"><span>📊 정밀 벤치마크 및 상세 스펙 보기 →</span></div>
          <div class="mc-score-row">
            <div class="mc-score-text">
              <span class="mc-score-label">WISE META SCORE</span>
              <span class="mc-score-verdict">${tier.verdict}</span>
            </div>
            <div class="mc-score-box ${tier.cls}">${score}</div>
          </div>
        </div>
      </a>`;
  }).join('\n');
}

function generateSitemap(uniqueTactics, pads) {
  const baseUrl = 'https://wiseplay.co.kr';
  const urls = [{ loc: `${baseUrl}/`, priority: '1.0' }];
  uniqueTactics.forEach(t => urls.push({ loc: `${baseUrl}/tactics/${cleanSlug(t.slug, t.playerName)}/`, priority: '0.9' }));
  pads.forEach(p => urls.push({ loc: `${baseUrl}/controllers/${cleanSlug(p.slug, p.padName)}/`, priority: '0.9' }));
  
  const xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    .concat(urls.map(u => `  <url><loc>${u.loc}</loc><priority>${u.priority}</priority></url>`))
    .concat(['</urlset>']).join('\n');
  fs.writeFileSync('sitemap.xml', xml, 'utf8');
}

async function runBuild() {
  const [tacticsRes, padsRes] = await Promise.all([fetch(TACTICS_CSV_URL), fetch(PADS_CSV_URL)]);
  const tactics = parseCSV(await tacticsRes.text());
  const pads = parseCSV(await padsRes.text());

  const tacticsBySlug = {};
  const uniqueTactics = [];
  tactics.forEach(t => {
    const slug = cleanSlug(t.slug, t.playerName);
    if (!tacticsBySlug[slug]) {
      tacticsBySlug[slug] = [];
      uniqueTactics.push(t);
    }
    tacticsBySlug[slug].push(t);
  });

  const rawTemplate = fs.readFileSync('index.html', 'utf8');

  ['tactics', 'controllers'].forEach(dir => { if(fs.existsSync(dir)) fs.rmSync(dir, {recursive:true, force:true}); });
  
  buildIndividualTacticPages(rawTemplate, uniqueTactics, tacticsBySlug);
  buildIndividualPadPages(rawTemplate, pads);

  let homeHtml = rawTemplate;
  homeHtml = homeHtml.replace(
    /<!-- SSG_TACTICS_START -->[\s\S]*?<!-- SSG_TACTICS_END -->/, 
    `<!-- SSG_TACTICS_START -->\n${generateStaticTacticsCards(uniqueTactics)}\n<!-- SSG_TACTICS_END -->`
  );
  homeHtml = homeHtml.replace(
    /<!-- SSG_PADS_START -->[\s\S]*?<!-- SSG_PADS_END -->/, 
    `<!-- SSG_PADS_START -->\n${generateStaticPadsCards(pads)}\n<!-- SSG_PADS_END -->`
  );

  const dStart = '/* SSG_DATA_START */', dEnd = '/* SSG_DATA_END */';
  if (homeHtml.includes(dStart) && homeHtml.includes(dEnd)) {
    homeHtml = homeHtml.substring(0, homeHtml.indexOf(dStart) + dStart.length) + 
      `\n    window.__PRELOADED_TACTICS__ = ${JSON.stringify(uniqueTactics)};\n    window.__PRELOADED_PADS__ = ${JSON.stringify(pads)};\n    ` + 
      homeHtml.substring(homeHtml.indexOf(dEnd));
  }

  fs.writeFileSync('index.html', homeHtml, 'utf8');
  generateSitemap(uniqueTactics, pads);
}

runBuild();
