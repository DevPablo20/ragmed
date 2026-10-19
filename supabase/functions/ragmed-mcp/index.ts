// Conector MCP do RAG de aulas, para usar como "conector personalizado" no claude.ai.
//
// O endereco e  https://<ref>.supabase.co/functions/v1/ragmed-mcp/<MCP_TOKEN>.
// O token no caminho e a unica protecao: as transcricoes sao material pago dos
// cursos, entao sem o token a funcao responde 404 como se nao existisse. Por
// isso o deploy e feito com --no-verify-jwt (o claude.ai nao manda JWT do
// Supabase) e a verificacao acontece aqui.
//
// Protocolo: MCP sobre Streamable HTTP, sem estado e so com respostas JSON — o
// minimo que um cliente MCP aceita. Tres ferramentas, e a busca em si e a funcao
// SQL buscar_trechos (BM25 sobre indice invertido, supabase/migrations/).

import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const TOKEN = Deno.env.get("MCP_TOKEN") ?? "";
const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);

const PROTOCOLOS = ["2025-06-18", "2025-03-26", "2024-11-05"];

// As mesmas regras validadas em scripts/ask.py (Etapa 4), adaptadas para o
// Claude do chat, que agora e quem escreve a resposta.
const REGRAS = `\
Regras para responder com estes trechos:
- Responda SOMENTE com o que está nos trechos. Não complete com conhecimento próprio; \
se quiser acrescentar algo de fora, separe claramente como "fora das aulas".
- Se os trechos não cobrem a pergunta, diga isso claramente. Antes de desistir, tente \
outra busca com outras palavras (sinônimos, nome do fármaco, termo técnico ou popular).
- Cite a fonte de cada afirmação como [n]. Se fizer mais de uma busca, renumere as \
citações na resposta final para que cada [n] seja único.
- Termine com um bloco FONTES agrupado por aula, listando TODOS os [n] de cada aula, \
com curso e link: "[3] [7] Aula X — Curso Y — link".
- Os trechos são transcrição automática de fala: termos médicos grafados errado e \
números possivelmente corrompidos. Se um valor ou termo parecer inconsistente, \
sinalize em vez de repeti-lo como certo.
- Quando os trechos discordam entre si, mostre a divergência em vez de escolher um lado.
- Se a resposta parecer continuar antes ou depois de um trecho, use ler_contexto.
- Feche lembrando que é conteúdo de aula transcrito automaticamente, a conferir na \
aula original antes de uso clínico.`;

const INSTRUCOES = `\
Acesso às transcrições das aulas dos cursos de medicina metabólica (206 aulas, 33 \
cursos). Use buscar_trechos_das_aulas sempre que a pergunta for sobre o que as aulas \
ensinam: doses, condutas, protocolos, exames, mecanismos.\n\n${REGRAS}`;

const TOOLS = [
  {
    name: "buscar_trechos_das_aulas",
    title: "Buscar nas aulas",
    description:
      "Busca nas transcrições das aulas os trechos mais relevantes para uma pergunta " +
      "médica e devolve cada trecho com curso, aula e link. A busca é por palavras: " +
      "inclua os termos que o professor usaria (nome do fármaco, exame, doença). " +
      "Se o resultado for fraco, busque de novo com outras palavras.\n\n" + REGRAS,
    inputSchema: {
      type: "object",
      properties: {
        pergunta: { type: "string", description: "A pergunta ou os termos de busca, em português." },
        curso: {
          type: "string",
          description: "Opcional: parte do nome de um curso para restringir a busca (ex.: 'Saúde do homem'). Veja listar_cursos.",
        },
        quantidade: { type: "integer", minimum: 1, maximum: 30, default: 15, description: "Quantos trechos devolver." },
      },
      required: ["pergunta"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "ler_contexto",
    title: "Ler trechos vizinhos",
    description:
      "Devolve o trecho indicado junto com os trechos imediatamente antes e depois na " +
      "mesma aula. Use quando a resposta parece começar antes ou continuar depois de " +
      "um trecho recuperado.",
    inputSchema: {
      type: "object",
      properties: {
        id_trecho: { type: "string", description: "O id do trecho, como aparece no resultado da busca." },
        janela: { type: "integer", minimum: 1, maximum: 3, default: 1, description: "Quantos trechos de cada lado." },
      },
      required: ["id_trecho"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "listar_cursos",
    title: "Listar cursos",
    description: "Lista os cursos disponíveis e quantas aulas cada um tem. Útil para restringir uma busca por curso.",
    inputSchema: { type: "object", properties: {} },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

type Hit = {
  rank: number; chunk_uid: string; lesson_title: string; course_title: string;
  lesson_url: string | null; instructor: string | null; text: string;
};

async function buscar(args: Record<string, unknown>): Promise<string> {
  const pergunta = String(args.pergunta ?? "").trim();
  if (!pergunta) throw new Error("informe a pergunta");
  const k = Math.min(30, Math.max(1, Number(args.quantidade ?? 15) || 15));
  const curso = args.curso ? String(args.curso) : null;
  const { data, error } = await db.rpc("buscar_trechos", { pergunta, k, curso });
  if (error) throw new Error(error.message);
  const hits = (data ?? []) as Hit[];
  if (!hits.length) {
    return `Nenhum trecho encontrado para "${pergunta}"${curso ? ` no curso "${curso}"` : ""}. ` +
      "Tente outras palavras ou sem o filtro de curso. Se continuar vazio, as aulas não cobrem o assunto.";
  }
  const blocos = hits.map((h) =>
    `[${h.rank}] Curso: ${h.course_title} | Aula: ${h.lesson_title}` +
    (h.instructor ? ` | Instrutor: ${h.instructor}` : "") +
    `\nLink: ${h.lesson_url ?? "(sem link)"} | id: ${h.chunk_uid}\n${h.text.trim()}`
  );
  return `Trechos recuperados para: "${pergunta}"${curso ? ` (curso: ${curso})` : ""}\n\n` +
    blocos.join("\n\n---\n\n") + `\n\n===\n${REGRAS}`;
}

async function contexto(args: Record<string, unknown>): Promise<string> {
  const id = String(args.id_trecho ?? "").trim();
  const janela = Math.min(3, Math.max(1, Number(args.janela ?? 1) || 1));
  const { data, error } = await db.rpc("ler_contexto", { p_chunk_uid: id, janela });
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as { chunk_uid: string; chunk_index: number; lesson_title: string; lesson_url: string | null; text: string }[];
  if (!rows.length) return `Trecho "${id}" não encontrado.`;
  return `Aula: ${rows[0].lesson_title}\nLink: ${rows[0].lesson_url ?? "(sem link)"}\n\n` +
    rows.map((r) => `(${r.chunk_uid}${r.chunk_uid === id ? " — o trecho pedido" : ""})\n${r.text.trim()}`)
      .join("\n\n---\n\n");
}

async function cursos(): Promise<string> {
  const { data, error } = await db.from("rag_lessons").select("rag_courses(course_title)");
  if (error) throw new Error(error.message);
  const n = new Map<string, number>();
  for (const r of (data ?? []) as { rag_courses: { course_title: string } }[]) {
    const t = r.rag_courses.course_title;
    n.set(t, (n.get(t) ?? 0) + 1);
  }
  return [...n.entries()].sort((a, b) => a[0].localeCompare(b[0], "pt"))
    .map(([t, c]) => `- ${t} (${c} aulas)`).join("\n");
}

async function handle(msg: { id?: unknown; method?: string; params?: Record<string, unknown> }) {
  const { method, params = {} } = msg;
  switch (method) {
    case "initialize": {
      const pedido = String(params.protocolVersion ?? "");
      return {
        protocolVersion: PROTOCOLOS.includes(pedido) ? pedido : PROTOCOLOS[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "ragmed-aulas", title: "Aulas de medicina metabólica", version: "1.0.0" },
        instructions: INSTRUCOES,
      };
    }
    case "ping":
      return {};
    case "tools/list":
      return { tools: TOOLS };
    case "tools/call": {
      const nome = String(params.name ?? "");
      const args = (params.arguments ?? {}) as Record<string, unknown>;
      try {
        const texto = nome === "buscar_trechos_das_aulas" ? await buscar(args)
          : nome === "ler_contexto" ? await contexto(args)
          : nome === "listar_cursos" ? await cursos()
          : null;
        if (texto === null) throw { rpc: -32602, message: `ferramenta desconhecida: ${nome}` };
        return { content: [{ type: "text", text: texto }] };
      } catch (e) {
        if (e && typeof e === "object" && "rpc" in e) throw e;
        return { content: [{ type: "text", text: `Erro: ${(e as Error).message}` }], isError: true };
      }
    }
    default:
      throw { rpc: -32601, message: `método não suportado: ${method}` };
  }
}

function tokenOk(url: URL): boolean {
  const ultimo = url.pathname.split("/").filter(Boolean).pop() ?? "";
  if (!TOKEN || ultimo.length !== TOKEN.length) return false;
  let diff = 0;
  for (let i = 0; i < TOKEN.length; i++) diff |= TOKEN.charCodeAt(i) ^ ultimo.charCodeAt(i);
  return diff === 0;
}

Deno.serve(async (req) => {
  if (!tokenOk(new URL(req.url))) return new Response("Not found", { status: 404 });
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405, headers: { Allow: "POST" } });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "JSON inválido" } }, { status: 400 });
  }

  const msgs = Array.isArray(body) ? body : [body];
  const respostas = [];
  for (const m of msgs as { id?: unknown; method?: string; params?: Record<string, unknown> }[]) {
    if (m.id === undefined || m.id === null) continue; // notificacao: sem resposta
    try {
      respostas.push({ jsonrpc: "2.0", id: m.id, result: await handle(m) });
    } catch (e) {
      const err = e as { rpc?: number; message?: string };
      respostas.push({ jsonrpc: "2.0", id: m.id, error: { code: err.rpc ?? -32603, message: err.message ?? "erro interno" } });
    }
  }
  if (!respostas.length) return new Response(null, { status: 202 });
  return Response.json(Array.isArray(body) ? respostas : respostas[0]);
});
