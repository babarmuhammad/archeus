import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import MarkdownIt from 'markdown-it';

const DIR = path.join(process.cwd(), 'content', 'blog');
const md = new MarkdownIt({ html: false, linkify: true });

export type Post = {
  slug: string;
  title: string;
  description: string;
  /** ISO yyyy-mm-dd */
  date: string;
  tags: string[];
  author: string;
  faq: { q: string; a: string }[];
  html: string;
  text: string;
};

/** gray-matter turns an unquoted YAML date into a Date; normalise both shapes. */
const isoDate = (v: unknown): string =>
  v instanceof Date
    ? v.toISOString().slice(0, 10)
    : String(v ?? '').slice(0, 10);

function parse(file: string): Post {
  const raw = fs.readFileSync(path.join(DIR, file), 'utf8');
  const { data, content } = matter(raw);
  const html = md.render(content.replace(/^#\s+.+\n/, ''));
  return {
    slug: file.replace(/\.md$/, ''),
    title: String(data.title ?? file),
    description: String(data.description ?? ''),
    date: isoDate(data.date),
    tags: Array.isArray(data.tags) ? data.tags.map(String) : [],
    author: String(data.author ?? 'Babar Muhammad Anas'),
    faq: Array.isArray(data.faq)
      ? data.faq.map((f: { q?: unknown; a?: unknown }) => ({
          q: String(f?.q ?? ''),
          a: String(f?.a ?? ''),
        }))
      : [],
    html,
    text: content.trim(),
  };
}

/** Newest first. Missing directory is an empty blog, not a failed build. */
export function allPosts(): Post[] {
  let files: string[] = [];
  try {
    files = fs.readdirSync(DIR).filter((f) => f.endsWith('.md'));
  } catch {
    return [];
  }
  return files.map(parse).sort((a, b) => b.date.localeCompare(a.date));
}

export const getPost = (slug: string): Post | undefined =>
  allPosts().find((p) => p.slug === slug);
