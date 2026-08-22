/* Extrator de metadados do Avantgarde College — para colar no console do DevTools.
 *
 * COMO USAR
 *   1. Faça login em https://ead.avantgardecollege.com.br e vá para
 *      /area/vitrine/home
 *   2. Abra o DevTools (F12) → aba Console
 *   3. Cole este arquivo inteiro e dê Enter
 *   4. Espere (~1 min para 35 cursos). Ao final o browser baixa
 *      snapshot_<timestamp>.json
 *   5. Mova o arquivo para data/snapshots/ e rode:
 *        python scripts/load_snapshot.py data/snapshots/<arquivo>.json
 *
 * Só lê páginas usando a sessão que já está aberta. Não envia nada para
 * lugar nenhum: o JSON é montado na memória do browser e salvo no seu disco.
 *
 * Duas particularidades do site que este código trata:
 *   - A sidebar de aulas é renderizada DUAS vezes (mobile + desktop), então os
 *     grupos vêm duplicados. Deduplica por data-acesso-secao-id.
 *   - A URL /area/conteudo/produto/<id> redireciona para a primeira aula; é a
 *     página de aula que carrega a sidebar com o índice completo do curso.
 */

(async () => {
  const BASE = "https://ead.avantgardecollege.com.br";
  const DELAY_MS = 220; // respiro entre requisições

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || "").trim().replace(/\s+/g, " ");
  const stripPos = (s) => clean(s).replace(/^\d+\.\s*/, "");        // "1. Aula 01" -> "Aula 01"
  const stripCount = (s) => clean(s).replace(/\s*[—-]\s*\d+\s+aulas?$/, ""); // "Oncologia — 5 aulas"

  // --- 1. cursos da vitrine, na ordem em que aparecem -----------------------
  const cards = [...document.querySelectorAll('a[href*="/area/conteudo/"]')]
    .map((a) => {
      const m = a.getAttribute("href").match(/\/area\/conteudo\/(produto|aula)\/(\d+)/);
      return m && { kind: m[1], id: m[2], title: clean(a.innerText) };
    })
    .filter(Boolean);

  if (!cards.length) {
    console.error("Nenhum curso encontrado. Você está logado e em /area/vitrine/home?");
    return;
  }
  console.log(`${cards.length} cursos na vitrine. Extraindo...`);

  // --- 2. índice de aulas de cada curso ------------------------------------
  const parseCourse = (html) => {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const seen = new Set();
    const groups = [];
    for (const g of doc.querySelectorAll(".section-group")) {
      const sid = g.getAttribute("data-acesso-secao-id");
      if (!sid || seen.has(sid)) continue; // sidebar duplicada mobile/desktop
      seen.add(sid);
      const head = g.querySelector(".section-group-titulo");
      const lessons = [...g.querySelectorAll(".section-item[data-acesso-item-id]")].map(
        (it, i) => ({
          site_lesson_id: it.getAttribute("data-acesso-item-id"),
          lesson_title: stripPos(it.querySelector(".item-titulo")?.innerText),
          lesson_url: `${BASE}/area/conteudo/aula/${it.getAttribute("data-acesso-item-id")}`,
          position_in_group: i + 1,
        })
      );
      groups.push({
        site_group_id: sid,
        group_title: stripCount(head?.getAttribute("aria-label") || head?.innerText) || null,
        group_index: groups.length + 1,
        lessons,
      });
    }
    return groups;
  };

  const courses = [];
  const failures = [];
  for (const [i, card] of cards.entries()) {
    const url = `/area/conteudo/${card.kind}/${card.id}`;
    try {
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      courses.push({
        site_course_id: card.id,
        course_title: card.title,
        course_url: BASE + url,
        course_kind: card.kind,
        position_in_vitrine: i + 1,
        groups: parseCourse(await res.text()),
      });
    } catch (e) {
      failures.push({ id: card.id, title: card.title, error: String(e) });
      console.warn(`falhou: ${card.title}`, e);
    }
    console.log(`  ${i + 1}/${cards.length}  ${card.title}`);
    await sleep(DELAY_MS);
  }

  // --- 3. monta e baixa o snapshot -----------------------------------------
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `T${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

  const snapshot = {
    scraped_at: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
      `T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
    source: `${BASE}/area/vitrine/home`,
    courses,
    ...(failures.length ? { failures } : {}),
  };

  const nLessons = courses.reduce(
    (a, c) => a + c.groups.reduce((b, g) => b + g.lessons.length, 0), 0
  );

  const blob = new Blob([JSON.stringify(snapshot, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `snapshot_${stamp}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);

  console.log(
    `\n✓ ${courses.length} cursos, ${nLessons} aulas -> snapshot_${stamp}.json` +
    (failures.length ? `\n⚠ ${failures.length} curso(s) falharam (registrados no JSON)` : "") +
    `\n\nAgora: mova para data/snapshots/ e rode` +
    `\n  python scripts/load_snapshot.py data/snapshots/snapshot_${stamp}.json`
  );
  window.__snapshot = snapshot; // caso o download seja bloqueado
})();
