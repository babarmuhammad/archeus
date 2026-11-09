// A QR code of a pairing URL, drawn here (p16-design-gate D10): no image
// service, no network. The code in it is a 120-second, single-use bootstrap,
// not a credential (P15 §6.1).
import qrcode from 'qrcode-generator';

export function QR({ text, label }: { text: string; label: string }) {
  const q = qrcode(0, 'M');
  q.addData(text);
  q.make();
  const n = q.getModuleCount();
  let d = '';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c + 4} ${r + 4}h1v1h-1z`;
  return (
    <svg className="qr" viewBox={`0 0 ${n + 8} ${n + 8}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect width={n + 8} height={n + 8} fill="#fff" />
      <path d={d} fill="#000" />
    </svg>
  );
}
