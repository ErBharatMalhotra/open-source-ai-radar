import type { APIRoute, GetStaticPaths } from 'astro';
import { readFileSync } from 'fs';
import { join } from 'path';
import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';

export const getStaticPaths = (() => {
  // Rendering every project's card adds minutes to the build; real cards
  // only matter for the projects people actually see and share.
  try {
    const index = JSON.parse(readFileSync(join(process.cwd(), '..', 'data', 'exports', 'projects-index.json'), 'utf-8'));
    return (index.projects || [])
      .sort((a: any, b: any) => (b.radar_score || 0) - (a.radar_score || 0))
      .slice(0, 800)
      .map((p: any) => {
        const [owner, repo] = p.full_name.split('/');
        return { params: { owner, repo } };
      });
  } catch {
    return [];
  }
}) satisfies GetStaticPaths;

const regularFont = readFileSync(join(process.cwd(), 'src', 'assets', 'fonts', 'Inter-Regular.ttf'));
const boldFont = readFileSync(join(process.cwd(), 'src', 'assets', 'fonts', 'Inter-Bold.ttf'));

function fmt(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return n.toString();
}

function scoreColor(s: number): string {
  if (s >= 75) return '#4ade80';
  if (s >= 50) return '#fbbf24';
  return '#f87171';
}

export const GET: APIRoute = async ({ params }) => {
  const { owner, repo } = params;
  const projectKey = `${owner}__${repo}`;
  let project: any = {};
  try {
    project = JSON.parse(readFileSync(join(process.cwd(), '..', 'data', 'exports', 'projects', `${projectKey}.json`), 'utf-8'));
  } catch {}

  const score = project.radar_score ? project.radar_score.toFixed(1) : '—';
  const desc = (project.description || '').slice(0, 120);

  const svg = await satori(
    {
      type: 'div',
      props: {
        style: {
          width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
          justifyContent: 'space-between', padding: '56px',
          background: 'linear-gradient(135deg, #09090b 0%, #13131a 60%, #171326 100%)',
          color: '#fafafa', fontFamily: 'Inter',
        },
        children: [
          {
            type: 'div',
            props: {
              style: { display: 'flex', alignItems: 'center', gap: '14px', fontSize: '24px', fontWeight: 600, color: '#a78bfa' },
              children: [
                { type: 'div', props: { style: { width: '36px', height: '36px', borderRadius: '10px', background: 'linear-gradient(135deg,#7c3aed,#4f46e5)', display: 'flex' } } },
                { type: 'div', props: { children: 'Open Source AI Radar' } },
              ],
            },
          },
          {
            type: 'div',
            props: {
              style: { display: 'flex', flexDirection: 'column', gap: '20px' },
              children: [
                { type: 'div', props: { style: { fontSize: '58px', fontWeight: 700, lineHeight: 1.1 }, children: `${owner}/${repo}` } },
                ...(desc ? [{ type: 'div', props: { style: { fontSize: '26px', color: '#a1a1aa', lineHeight: 1.35 }, children: desc } }] : []),
              ],
            },
          },
          {
            type: 'div',
            props: {
              style: { display: 'flex', alignItems: 'center', gap: '28px', fontSize: '26px', color: '#d4d4d8' },
              children: [
                { type: 'div', props: { style: { display: 'flex', alignItems: 'center', gap: '10px', background: 'rgba(255,255,255,0.06)', border: `2px solid ${scoreColor(project.radar_score || 0)}`, borderRadius: '12px', padding: '10px 22px', color: scoreColor(project.radar_score || 0), fontWeight: 700, fontSize: '30px' }, children: `Score ${score}` } },
                { type: 'div', props: { children: `★ ${fmt(project.stars || 0)} stars` } },
                ...(project.language ? [{ type: 'div', props: { children: project.language } }] : []),
                ...(project.category && project.category !== 'Uncategorized' ? [{ type: 'div', props: { children: project.category } }] : []),
              ],
            },
          },
        ],
      },
    },
    { width: 1200, height: 630, fonts: [
      { name: 'Inter', data: regularFont, weight: 400, style: 'normal' },
      { name: 'Inter', data: boldFont, weight: 700, style: 'normal' },
    ] }
  );

  const png = new Resvg(svg, { fitTo: { mode: 'width', value: 1200 }, font: { loadSystemFonts: false } }).render().asPng();
  return new Response(png as unknown as BodyInit, {
    headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' },
  });
};
