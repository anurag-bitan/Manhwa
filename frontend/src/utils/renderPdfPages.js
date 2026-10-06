const PDFJS_CDN = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build";

let pdfjsPromise;

async function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(/* @vite-ignore */ `${PDFJS_CDN}/pdf.min.mjs`).then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.mjs`;
      return pdfjs;
    });
  }
  return pdfjsPromise;
}

export async function renderPdfPagesToJpegs(
  file,
  { maxWidth = 1100, quality = 0.65, onProgress } = {},
) {
  const pdfjs = await loadPdfjs();
  const data = await file.arrayBuffer();
  const pdf = await pdfjs.getDocument({ data }).promise;
  const blobs = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const unscaled = page.getViewport({ scale: 1 });
    const scale = Math.min(1.1, maxWidth / Math.max(unscaled.width, 1));
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.floor(viewport.width));
    canvas.height = Math.max(1, Math.floor(viewport.height));
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      throw new Error("Could not create a canvas to render the PDF.");
    }
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvasContext: context, viewport }).promise;
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(
        (result) => {
          if (result) resolve(result);
          else reject(new Error("Could not encode a page as JPEG."));
        },
        "image/jpeg",
        quality,
      );
    });
    blobs.push(blob);
    onProgress?.(pageNumber, pdf.numPages);
  }

  return blobs;
}
