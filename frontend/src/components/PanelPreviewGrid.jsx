import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

function cropFromBbox(img, bbox) {
  if (!Array.isArray(bbox) || bbox.length !== 4) {
    return { x: 0, y: 0, width: img.naturalWidth || img.width, height: img.naturalHeight || img.height };
  }
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  const [x1, y1, x2, y2] = bbox.map(Number);
  const x = Math.max(0, Math.min(x1, width - 1));
  const y = Math.max(0, Math.min(y1, height - 1));
  const w = Math.max(1, Math.min(x2, width) - x);
  const h = Math.max(1, Math.min(y2, height) - y);
  return { x, y, width: w, height: h };
}

function CroppedPanelImage({ src, bbox, alt, className, maxHeight = 320 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!src) return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.referrerPolicy = "no-referrer";
    let cancelled = false;

    img.onload = () => {
      if (cancelled) return;
      const crop = cropFromBbox(img, bbox);
      const maxW = canvas.parentElement?.clientWidth || 240;
      const maxH = maxHeight;
      const scale = Math.min(maxW / crop.width, maxH / crop.height, 1.5);
      const drawW = Math.max(1, Math.round(crop.width * scale));
      const drawH = Math.max(1, Math.round(crop.height * scale));
      canvas.width = drawW;
      canvas.height = drawH;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, crop.x, crop.y, crop.width, crop.height, 0, 0, drawW, drawH);
    };
    img.onerror = () => {
      if (cancelled) return;
      const ctx = canvas.getContext("2d");
      canvas.width = 160;
      canvas.height = 120;
      ctx.fillStyle = "#111827";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    };
    img.src = src;
    return () => {
      cancelled = true;
    };
  }, [src, bbox, maxHeight]);

  return (
    <canvas
      ref={canvasRef}
      aria-label={alt}
      className={className}
    />
  );
}

export default function PanelPreviewGrid({ cards }) {
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!preview) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setPreview(null);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [preview]);

  if (!cards?.length) return null;

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-2 sm:gap-3 md:gap-4">
        {cards.map((card) => (
          <button
            key={card.id}
            type="button"
            onClick={() => setPreview(card)}
            className="relative group text-left rounded-lg sm:rounded-xl border border-purple-500/20 bg-black/30 overflow-hidden hover:border-purple-400/60 hover:scale-[1.02] transition-all shadow-lg focus:outline-none focus:ring-2 focus:ring-purple-400"
          >
            <CroppedPanelImage
              src={card.src}
              bbox={card.bbox}
              alt={card.label}
              className="w-full h-28 sm:h-32 md:h-40 lg:h-48 object-contain bg-black"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-center pb-1.5 sm:pb-2">
              <span className="text-xs text-white font-medium">{card.label}</span>
            </div>
          </button>
        ))}
      </div>

      {preview &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
            role="dialog"
            aria-modal="true"
            aria-label={`${preview.label} preview`}
            onClick={() => setPreview(null)}
          >
            <div
              className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-purple-500/30 bg-gray-950 p-4 shadow-2xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-white">{preview.label}</h4>
                <button
                  type="button"
                  onClick={() => setPreview(null)}
                  className="rounded-lg p-1.5 text-gray-300 hover:bg-white/10 hover:text-white"
                  aria-label="Close preview"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex justify-center bg-black rounded-xl overflow-hidden">
                <CroppedPanelImage
                  src={preview.src}
                  bbox={preview.bbox}
                  alt={preview.label}
                  maxHeight={Math.min(window.innerHeight * 0.7, 720)}
                  className="max-w-full object-contain"
                />
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
