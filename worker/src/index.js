/**
 * pantau — Worker Cloudflare: cron tiap 2 menit + D1 + Telegram.
 *
 * Deploy:
 *   cd worker
 *   npx wrangler login                 # buka browser, klik Allow
 *   npx wrangler d1 create pantau      # salin database_id ke wrangler.toml
 *   npx wrangler d1 execute pantau --file=schema.sql --remote
 *   npx wrangler secret put TELEGRAM_TOKEN
 *   npx wrangler secret put TELEGRAM_CHAT
 *   npx wrangler deploy
 */

const QUERIES = [
  "kode promo ai gratis",
  "claude gratis",
  "chatgpt gratis",
  "gemini gratis",
  "bansos ai",
  "free ai credits",
];

const ENGINES = ["gnews", "bing"];
const MAX_AGE_H = 24;
const MIN_NOTIFY = 45;
const MIN_NOTIFY_CODED = 28;

const PROMO = [
  "gratis", "free", "promo", "voucher", "kode", "code", "redeem", "diskon",
  "discount", "coupon", "klaim", "claim", "bonus", "credit", "kredit",
  "kuota", "quota", "giveaway", "hadiah", "trial",
];

const PROMO_TITLE = [
  "gratis", "free", "promo", "voucher", "trial", "diskon", "discount",
  "klaim", "claim", "giveaway", "coupon", "bonus", "murah", "credit", "kredit", "kuota",
];

const DEAD = [
  "expired", "kedaluwarsa", "kadaluarsa", "sudah berakhir", "ended",
  "no longer valid", "tidak berlaku lagi", "habis", "sold out", "invalid code",
];

const AI = [
  "ai", "llm", "claude", "anthropic", "chatgpt", "openai", "gpt", "gemini",
  "copilot", "cursor", "perplexity", "deepseek", "midjourney", "elevenlabs",
  "windsurf", "codeium", "kiro", "grok", "mistral", "poe", "v0", "vercel",
  "groq", "huggingface", "kuota api", "model bahasa", "bansos ai", "token ai",
  "api ai", "ai gratis", "kredit api", "kredit ai",
];

const JUNK = [
  "kode pos", "kode wilayah", "kode bank", "kode negara", "kode plat",
  "kode kbli", "kode kbbi", "arti kata", "kamus", "apkmirror",
  "mobile legends", "free fire", "ff max", "codm", "valorant", "roblox",
  "pubg", "genshin", "diamond", "kode otp",
];

const NOT_OFFER = [
  "promo video", "video promo", "promosi", "iklan", "show hn", "showoff",
  "i made", "i built", "i created", "we built", "we made", "my app",
  "looking for feedback", "roast my", "rate my",
];

const BRANDS = {
  claude: ["claude", "anthropic"],
  chatgpt: ["chatgpt", "openai", "gpt-4", "gpt-5", "gpt"],
  gemini: ["gemini", "google ai", "bard"],
  copilot: ["copilot"],
  cursor: ["cursor"],
  perplexity: ["perplexity", "pplx"],
  deepseek: ["deepseek"],
  midjourney: ["midjourney"],
  elevenlabs: ["elevenlabs"],
  windsurf: ["windsurf", "codeium"],
  vercel: ["v0", "vercel"],
  grok: ["grok", "x.ai"],
  mistral: ["mistral"],
};

const STOP = new Set([
  "HTTP", "HTTPS", "HTML", "WWW", "JSON", "API", "SDK", "URL", "GPU", "CPU",
  "OPENAI", "CLAUDE", "GEMINI", "CHATGPT", "ANTHROPIC", "COPILOT", "CURSOR",
  "PERPLEXITY", "DEEPSEEK", "MIDJOURNEY", "ELEVENLABS", "WINDSURF", "FREE",
  "PRO", "PLUS", "TEAM", "TRIAL", "USER", "UPDATE", "LOGIN", "SIGNUP",
  "TERMS", "PRIVACY", "CONTACT", "ABOUT", "SUPPORT",
]);

const STRONG = [
  "kode promo", "kode voucher", "kode redeem", "promo code", "voucher code",
  "coupon code", "redeem code", "invite code", "referral code",
];

const PATTERNS = [
  /["'`\u201c\u201d]([A-Z0-9][A-Z0-9_-]{3,23})["'`\u201c\u201d]/g,
  /(?:kode|code|voucher|promo|redeem|pakai|use|with)\s*(?:promo|voucher|kode)?\s*[:=]?\s*([A-Z0-9][A-Z0-9_-]{3,23})\b/gi,
  /\b([A-Z][A-Z0-9]{3,19}(?:[-_][A-Z0-9]{2,12}){0,3})\b/g,
];

function clean(s) {
  return (s || "")
    .replace(/<!\[CDATA\[/g, " ")
    .replace(/\]\]>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseDate(raw) {
  if (!raw) return null;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? null : Math.floor(ms / 1000);
}

function plausible(code, ctx, quoted) {
  if (STOP.has(code)) return false;
  if (code !== code.toUpperCase()) return false;
  if (code.length < 4 || code.length > 24) return false;
  if (/^G-[A-Z0-9]{8,}$/.test(code)) return false;
  if (/^UA-\d+-\d+$/.test(code)) return false;
  if (!/[a-z]/i.test(code)) return false;

  const low = ctx.toLowerCase();
  if (!PROMO.some((w) => low.includes(w))) return false;

  if (!/\d/.test(code)) {
    if (!quoted) return false;
    if (!STRONG.some((w) => low.includes(w))) return false;
  }
  if (code.length >= 10 && !code.includes("-") && !code.includes("_") &&
      (code.match(/\d/g) || []).length < 2) {
    return false;
  }
  return true;
}

function extractCodes(text, limit = 8) {
  const out = [];
  const seen = new Set();
  for (const pat of PATTERNS) {
    pat.lastIndex = 0;
    let m;
    while ((m = pat.exec(text)) !== null) {
      const code = m[1].replace(/^[-_]+|[-_]+$/g, "");
      const start = Math.max(0, m.index - 80);
      const ctx = text.slice(start, Math.min(text.length, m.index + m[0].length + 80));
      const head = text.charAt(m.index - 1);
      const quoted = ['"', "'", "`", "\u201c", "\u201d", "*"].includes(head);
      if (!seen.has(code) && plausible(code, ctx, quoted)) {
        seen.add(code);
        out.push(code);
        if (out.length >= limit) return out;
      }
    }
  }
  return out;
}

function relevant(title, snippet, url) {
  const t = `${title} ${snippet} ${url}`.toLowerCase();
  if (JUNK.some((j) => t.includes(j))) return false;
  return AI.some((a) => (a === "ai" ? /\bai\b|\/ai|ai-/.test(t) : t.includes(a)));
}

function isOffer(title, snippet, codes) {
  if (codes.length) return true;
  const low = title.toLowerCase();
  if (NOT_OFFER.some((p) => low.includes(p))) return false;
  const brand = Object.values(BRANDS).flat().some((b) => low.includes(b));
  const promo = PROMO_TITLE.some((w) => low.includes(w));
  if (brand && promo) return true;
  const generic = ["ai", "kecerdasan buatan", "chatbot", "asisten ai", "model bahasa"];
  return promo && generic.some((g) => low.includes(g));
}

function brandOf(text) {
  const t = text.toLowerCase();
  for (const [brand, keys] of Object.entries(BRANDS)) {
    if (keys.some((k) => t.includes(k))) return brand;
  }
  return "";
}

function scoreOf(title, snippet, url, source, codes) {
  const t = `${title} ${snippet}`.toLowerCase();
  let s = Math.min(40, codes.length * 18);
  s += Math.min(20, PROMO.filter((w) => t.includes(w)).length * 5);
  if (PROMO_TITLE.some((w) => title.toLowerCase().includes(w))) s += 10;
  if (t.includes("2026") || url.includes("2026")) s += 8;
  if (DEAD.some((d) => t.includes(d))) s -= 35;
  if (/login|signin|cart|checkout/.test(url.toLowerCase())) s -= 25;
  if (title.trim().length < 12) s -= 15;
  if (source === "github" && codes.length === 0) s -= 22;
  if (!relevant(title, snippet, url)) s -= 40;
  return Math.max(0, Math.min(100, s));
}

function parseFeed(xml) {
  const out = [];
  const blocks = [...(xml.match(/<item[\s\S]*?<\/item>/g) || []),
                  ...(xml.match(/<entry[\s\S]*?<\/entry>/g) || [])];
  for (const block of blocks) {
    const pick = (tag) => {
      const m = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`));
      return m ? clean(m[1]) : "";
    };
    let link = pick("link");
    if (!link) {
      const m = block.match(/<link[^>]*href="([^"]+)"/);
      link = m ? m[1] : "";
    }
    if (!link) continue;
    out.push({
      title: pick("title"),
      url: link,
      snippet: (pick("description") || pick("content") || pick("summary")).slice(0, 600),
      published: parseDate(pick("pubDate") || pick("published") || pick("updated")),
    });
  }
  return out;
}

async function searchBing(q) {
  const filters = encodeURIComponent('ex1:"ez1"');
  const u = `https://www.bing.com/search?q=${encodeURIComponent(q)}&format=rss&setlang=id&cc=ID&filters=${filters}`;
  const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0 (compatible; pantau/1.0)" } });
  if (!r.ok) throw new Error(`bing ${r.status}`);
  return parseFeed(await r.text());
}

async function searchGNews(q) {
  const u = `https://news.google.com/rss/search?q=${encodeURIComponent(q + " when:1d")}&hl=id&gl=ID&ceid=ID:id`;
  const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0 (compatible; pantau/1.0)" } });
  if (!r.ok) throw new Error(`gnews ${r.status}`);
  return parseFeed(await r.text());
}

const ENGINES_FN = { bing: searchBing, gnews: searchGNews };

async function sha1(str) {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(str));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const normUrl = (u) => u.split("#")[0].split("&utm_")[0].split("?utm_")[0].replace(/\/$/, "").toLowerCase();

async function collect() {
  const rows = [];
  const seen = new Set();
  const cutoff = Math.floor(Date.now() / 1000) - MAX_AGE_H * 3600;

  for (const q of QUERIES) {
    for (const name of ENGINES) {
      try {
        const items = await ENGINES_FN[name](q);
        for (const it of items) {
          if (!it.url) continue;
          if (!it.published || it.published < cutoff) continue;   // 24 jam saja
          if (!relevant(it.title, it.snippet, it.url)) continue;
          const text = `${it.title} ${it.snippet}`;
          const codes = extractCodes(text);
          if (!isOffer(it.title, it.snippet, codes)) continue;
          const key = normUrl(it.url) + "|" + it.title.toLowerCase();
          if (seen.has(key)) continue;
          seen.add(key);
          const score = scoreOf(it.title, it.snippet, it.url, name, codes);
          if (score < 12) continue;
          let domain = "";
          try { domain = new URL(it.url).hostname.replace(/^www\./, ""); } catch { /* biarkan kosong */ }
          rows.push({
            uid: await sha1(key), url: it.url, domain, title: it.title,
            snippet: it.snippet, source: name, brand: brandOf(text + " " + it.url),
            codes: JSON.stringify(codes), score, expiry: null,
          });
        }
      } catch (e) {
        console.log(`${name} gagal: ${e.message}`);
      }
    }
  }
  return rows;
}

async function store(env, rows) {
  const fresh = [];
  for (const r of rows) {
    const res = await env.DB.prepare(
      `INSERT OR IGNORE INTO findings
       (uid,url,domain,title,snippet,source,brand,codes,score,expiry,first_seen,last_seen,notified)
       VALUES (?,?,?,?,?,?,?,?,?,?,unixepoch(),unixepoch(),0)`
    ).bind(r.uid, r.url, r.domain, r.title, r.snippet, r.source, r.brand,
           r.codes, r.score, r.expiry).run();
    if (res.meta.changes > 0) {
      fresh.push(r);
      for (const code of JSON.parse(r.codes)) {
        await env.DB.prepare(
          "INSERT OR IGNORE INTO codes (code,brand,uid,first_seen) VALUES (?,?,?,unixepoch())"
        ).bind(code, r.brand, r.uid).run();
      }
    }
  }
  return fresh;
}

async function notify(env, items) {
  const ready = items
    .filter((i) => i.score >= MIN_NOTIFY ||
                   (JSON.parse(i.codes).length > 0 && i.score >= MIN_NOTIFY_CODED))
    .slice(0, 10);
  if (!ready.length || !env.TELEGRAM_TOKEN || !env.TELEGRAM_CHAT) return 0;
  const lines = ready.map((i) => {
    const codes = JSON.parse(i.codes);
    return `[${i.score}] ${i.title.slice(0, 80)}\nkode: ${codes.join(", ") || "-"}\n${i.url}`;
  });
  const text = `${ready.length} temuan baru\n\n` + lines.join("\n\n");
  const res = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: env.TELEGRAM_CHAT,
        text: text.slice(0, 4000),
        disable_web_page_preview: true,
      }),
    }
  );
  return res.ok ? ready.length : 0;
}

export { extractCodes, plausible, scoreOf, parseFeed, relevant, isOffer, brandOf };

export default {
  async scheduled(event, env, ctx) {
    const rows = await collect();
    const fresh = await store(env, rows);
    const sent = await notify(env, fresh);
    console.log(`kueri=${QUERIES.length} hasil=${rows.length} baru=${fresh.length} terkirim=${sent}`);
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/scan") {
      const rows = await collect();
      const fresh = await store(env, rows);
      const sent = await notify(env, fresh);
      return Response.json({ hasil: rows.length, baru: fresh.length, terkirim: sent });
    }
    if (url.pathname === "/top") {
      const { results } = await env.DB.prepare(
        `SELECT title, url, score, codes, brand, first_seen FROM findings
         ORDER BY score DESC, first_seen DESC LIMIT 30`
      ).all();
      return Response.json(results);
    }
    const { results } = await env.DB.prepare(
      "SELECT COUNT(*) AS findings, COUNT(DISTINCT brand) AS brands FROM codes"
    ).all();
    return Response.json({ ok: true, stats: results[0] });
  },
};