import type { APIRoute } from 'astro';
import { readFileSync } from 'fs';
import { join } from 'path';
import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';

const regularFont = readFileSync(join(process.cwd(), 'src', 'assets', 'fonts', 'Inter-Regular.ttf'));
const boldFont = readFileSync(join(process.cwd(), 'src', 'assets', 'fonts', 'Inter-Bold.ttf'));

function fmt(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return n.toString();
}

export const GET: APIRoute = async () => {
  let stats: any = {};
  try {
    stats = JSON.parse(readFileSync(join(process.cwd(), '..', 'data', 'exports', 'stats.json'), 'utf-8'));
  } catch {}

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
                { type: 'div', props: { style: { fontSize: '64px', fontWeight: 700, lineHeight: 1.1 }, children: 'Discover momentum in open-source AI' } },
                { type: 'div', props: { style: { fontSize: '28px', color: '#a1a1aa', lineHeight: 1.35 }, children: 'Velocity scoring, trend detection and breakout predictions for every AI repo on GitHub.' } },
              ],
            },
          },
          {
            type: 'div',
            props: {
              style: { display: 'flex', alignItems: 'center', gap: '32px', fontSize: '28px', color: '#d4d4d8' },
              children: [
                { type: 'div', props: { children: `${fmt(stats.total_repos || 0)} projects tracked` } },
                { type: 'div', props: { children: `★ ${fmt(stats.total_stars || 0)} stars indexed` } },
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
