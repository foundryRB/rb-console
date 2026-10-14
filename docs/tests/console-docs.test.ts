/**
 * The Foundry Console's own documentation claims (INT-FC-DOCS-*), beside the STARLIGHT
 * bundle's generic suite: what this site must carry, and the mirrors of a source of truth
 * (the API export, the chart values, the decision log, the site's own links) held to it.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, sep } from "node:path";

import { describe, expect } from "vitest";
import { intent } from "@psa-department-of-engineering/vitest-intent";

const DOCS_DIR = join(process.cwd(), "src", "content", "docs");
const APP_ROOT = join(process.cwd(), "..");
const FRONTMATTER_RE = /^---\s*\n([\s\S]*?)\n---/;
const FENCE_RE = /```[\s\S]*?```/g;
const MDX_COMMENT_RE = /\{\/\*[\s\S]*?\*\/\}/g;
/** Link targets that are files served as they are, not pages. */
const ASSET_RE = /\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|json|txt|css|js|woff2?)$/i;

interface Doc {
  path: string;
  slug: string;
  frontmatter: Record<string, string>;
  body: string;
}

function* walk(dir: string, extensions: string[]): Generator<string> {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name !== "node_modules" && name !== "__pycache__") yield* walk(full, extensions);
    } else if (extensions.includes(extname(name))) yield full;
  }
}

function slugOf(path: string): string {
  const parts = path.split(sep).join("/").replace(/\.(md|mdx)$/, "").toLowerCase();
  return parts === "index" ? "" : parts.replace(/\/index$/, "");
}

function loadDocs(): Doc[] {
  const docs: Doc[] = [];
  for (const file of walk(DOCS_DIR, [".md", ".mdx"])) {
    const text = readFileSync(file, "utf-8");
    const match = FRONTMATTER_RE.exec(text);
    if (!match) continue;
    const frontmatter: Record<string, string> = {};
    for (const line of match[1].split("\n")) {
      const colon = line.indexOf(":");
      if (colon === -1 || line.trim().startsWith("#")) continue;
      frontmatter[line.slice(0, colon).trim()] = line
        .slice(colon + 1)
        .trim()
        .replace(/^["']|["']$/g, "");
    }
    const path = relative(DOCS_DIR, file);
    docs.push({ path, slug: slugOf(path), frontmatter, body: text.slice(match[0].length) });
  }
  return docs;
}

/** The lines of a section opened by a heading of the given text, up to the next heading of
 * the same or a higher level, or a closing tab. */
function section(body: string, heading: string): string[] {
  const lines = body.split("\n");
  const start = lines.findIndex((line) => new RegExp(`^(#{2,4})\\s+${heading}\\s*$`).test(line));
  if (start === -1) return [];
  const level = (/^(#+)/.exec(lines[start]) as RegExpExecArray)[1].length;
  const out: string[] = [];
  for (const line of lines.slice(start + 1)) {
    const heading = /^(#{1,6})\s/.exec(line);
    if ((heading && heading[1].length <= level) || line.trim() === "</TabItem>") break;
    out.push(line);
  }
  return out;
}

function tableRows(lines: string[]): string[][] {
  return lines
    .filter((line) => line.trim().startsWith("|"))
    .map((line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()))
    .filter((cells) => !cells.every((cell) => /^:?-+:?$/.test(cell)));
}

/** Every dotted key path of a simple YAML mapping file (no flow mappings, no anchors). */
function yamlKeyPaths(text: string): Set<string> {
  const paths = new Set<string>();
  const stack: { indent: number; key: string }[] = [];
  for (const raw of text.split("\n")) {
    if (/^\s*(#|-|$)/.test(raw)) continue;
    const match = /^(\s*)([A-Za-z_][\w-]*):/.exec(raw);
    if (!match) continue;
    const indent = match[1].length;
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    stack.push({ indent, key: match[2] });
    paths.add(stack.map((entry) => entry.key).join("."));
  }
  return paths;
}

describe("Foundry Console documentation", () => {
  const docs = loadDocs();
  const page = (id: string) => docs.find((d) => d.frontmatter["id"] === id);

  intent(
    "INT-FC-DOCS-001",
    "the maintenance module page carries the loop, its ceremony modes, the verdict gate, the derived read and the console-role merge identity",
    () => {
      const maintenance = page("DOC-FC-MODULE-MAINTENANCE");
      expect(maintenance, "maintenance module page missing").toBeTruthy();
      const body = maintenance!.body;
      for (const needle of ["gated", "one-shot", "direct", "VERDICT: PASS", "VERDICT: FAIL"]) {
        expect(body, `the maintenance page lost the loop's "${needle}"`).toContain(needle);
      }
      expect(body).toMatch(/[Nn]othing merges unreviewed/);
      expect(body, "the maintenance read named as derived, in one sentence").toMatch(
        /[^.]*\b[Mm]aintenance\b[^.]*\bderived\b|[^.]*\bderived\b[^.]*\b[Mm]aintenance\b/,
      );
      expect(body, "the console-role merge identity, stated plainly").toMatch(/console-role git identity/i);
      expect(body).toMatch(/press is the operator'?s/);
    },
  );

  intent(
    "INT-FC-DOCS-002",
    "the ticket-marker conventions are documented: both markers + vocabularies, the two body shapes, and the org .github rollout",
    () => {
      const conventions = page("DOC-FOUNDRY-CONSOLE-006");
      expect(conventions, "ticket-conventions page missing").toBeTruthy();
      const body = conventions!.body;
      for (const needle of ["Complexity", "Priority", "Low", "Medium", "High", "Lowest", "Highest"]) {
        expect(body, `ticket-conventions page lost "${needle}"`).toContain(needle);
      }
      expect(body, "the Issue-Form field-block shape").toMatch(/###\s+Complexity/);
      expect(body, "the hand-typed trailer-line shape").toMatch(/Complexity:\s*High/);
      expect(body).toMatch(/default community health files/i);
      expect(body).toMatch(/\.github/);
      expect(body).toMatch(/Issue Type/i);
      expect(body, "Type must be explained as native, distinct from the body markers").toMatch(
        /Type comes from GitHub/i,
      );
    },
  );

  intent(
    "INT-FC-DOCS-003",
    "the module pages' HTTP surfaces cover the API export exactly: every operation in one module, no row the export lacks",
    () => {
      const spec = JSON.parse(readFileSync(join(APP_ROOT, "frontend", "src", "models", "openapi.json"), "utf-8"));
      const exported = new Set<string>();
      for (const [route, item] of Object.entries<Record<string, unknown>>(spec.paths)) {
        for (const method of Object.keys(item)) {
          if (["get", "post", "put", "patch", "delete"].includes(method)) exported.add(`${method.toUpperCase()} ${route}`);
        }
      }
      const owners = new Map<string, string[]>();
      const extra: string[] = [];
      for (const doc of docs.filter((d) => d.frontmatter["type"] === "Module")) {
        for (const cells of tableRows(section(doc.body, "HTTP surface")).slice(1)) {
          const operation = `${cells[0]} ${cells[1].replace(/`/g, "")}`;
          if (!exported.has(operation)) extra.push(`${doc.path}: ${operation}`);
          owners.set(operation, [...(owners.get(operation) ?? []), doc.path]);
        }
      }
      const missing = [...exported].filter((operation) => !owners.has(operation));
      const shared = [...owners].filter(([, pages]) => pages.length > 1).map(([op, pages]) => `${op}: ${pages.join(", ")}`);
      expect(extra, "rows naming an operation the API export lacks").toEqual([]);
      expect(missing, "operations no module page documents").toEqual([]);
      expect(shared, "operations documented by more than one module").toEqual([]);
    },
  );

  intent(
    "INT-FC-DOCS-004",
    "the configuration reference names the chart's values and the application's environment as the sources hold them",
    () => {
      const reference = page("DOC-FC-REF-CONFIGURATION");
      expect(reference, "configuration reference missing").toBeTruthy();
      const values = yamlKeyPaths(readFileSync(join(APP_ROOT, "k8s", "values.yaml"), "utf-8"));
      const documented = tableRows(section(reference!.body, "Chart values"))
        .slice(1)
        .map((cells) => cells[0].replace(/`/g, ""));
      expect(documented.filter((key) => !values.has(key)), "values the chart does not have").toEqual([]);
      const topLevel = [...values].filter((key) => !key.includes("."));
      expect(
        topLevel.filter((key) => !documented.some((doc) => doc === key || doc.startsWith(`${key}.`))),
        "top-level chart values the reference does not name",
      ).toEqual([]);

      const read = new Set<string>();
      const lookup = /(?:environ\.get|getenv|_require_install_value)\(\s*["'](FC_[A-Z0-9_]+)["']|environ\[\s*["'](FC_[A-Z0-9_]+)["']/g;
      for (const file of walk(join(APP_ROOT, "orchestrator"), [".py"])) {
        for (const match of readFileSync(file, "utf-8").matchAll(lookup)) read.add(match[1] ?? match[2]);
      }
      const environment = tableRows(section(reference!.body, "Application environment"))
        .slice(1)
        .map((cells) => cells[0].replace(/`/g, ""));
      expect(environment.filter((name) => !read.has(name)), "variables the application never reads").toEqual([]);
      expect([...read].filter((name) => !environment.includes(name)).sort(), "variables the reference leaves out").toEqual([]);
    },
  );

  intent(
    "INT-FC-DOCS-005",
    "the decisions index lists every decision record of the collection, and only those",
    () => {
      const index = page("DOC-FC-DECISIONS");
      expect(index, "decisions index missing").toBeTruthy();
      const records = docs
        .filter((d) => d.slug.startsWith("decisions/"))
        .map((d) => d.slug.slice("decisions/".length))
        .sort();
      const rows = tableRows(section(index!.body, "Current")).slice(1);
      const listed = rows
        .map((cells) => (/\]\(([^)/]+)\/?\)/.exec(cells[0]) ?? [])[1])
        .filter(Boolean)
        .sort();
      expect(listed).toEqual(records);
      for (const cells of rows) {
        const target = (/\]\(([^)/]+)\/?\)/.exec(cells[0]) ?? [])[1];
        const record = docs.find((d) => d.slug === `decisions/${target}`);
        expect(cells[0], `the row linking ${target} carries that record's title`).toContain(
          record?.frontmatter["title"] ?? "<no record>",
        );
      }
    },
  );

  intent(
    "INT-FC-DOCS-006",
    "every relative link between pages resolves to a page of the site",
    () => {
      const slugs = new Set(docs.map((d) => d.slug));
      const broken: string[] = [];
      for (const doc of docs) {
        const base = new URL(`https://site.invalid/${doc.slug ? `${doc.slug}/` : ""}`);
        const prose = doc.body.replace(FENCE_RE, "").replace(MDX_COMMENT_RE, "");
        for (const match of prose.matchAll(/\]\(([^)\s]+)\)|href="([^"]+)"/g)) {
          const target = (match[1] ?? match[2]).split("#")[0].split("?")[0];
          if (!target || /^[a-z]+:/i.test(target) || ASSET_RE.test(target)) continue;
          const resolved = new URL(target, base).pathname.replace(/^\/|\/$/g, "");
          if (!slugs.has(resolved)) broken.push(`${doc.path}: ${target}`);
        }
      }
      expect(broken, "links that resolve to no page").toEqual([]);
    },
  );

  intent(
    "INT-FC-DOCS-007",
    "outside the decisions collection, no page links a decision record or names one by its number",
    () => {
      const offenders: string[] = [];
      for (const doc of docs.filter((d) => !d.slug.startsWith("decisions/") && d.slug !== "decisions")) {
        const base = new URL(`https://site.invalid/${doc.slug ? `${doc.slug}/` : ""}`);
        const prose = doc.body.replace(FENCE_RE, "").replace(MDX_COMMENT_RE, "");
        for (const match of prose.matchAll(/\]\(([^)\s]+)\)|href="([^"]+)"/g)) {
          const target = (match[1] ?? match[2]).split("#")[0];
          if (!target || /^[a-z]+:/i.test(target)) continue;
          const resolved = new URL(target, base).pathname.replace(/^\/|\/$/g, "");
          if (resolved.startsWith("decisions/")) offenders.push(`${doc.path}: links ${target}`);
        }
        for (const match of prose.matchAll(/\b(?:ADR|decision)[\s#-]*\d{3,4}\b/gi)) {
          offenders.push(`${doc.path}: names ${match[0]}`);
        }
      }
      expect(offenders, "the why is reached through the decisions collection, never one record").toEqual([]);
    },
  );
});
