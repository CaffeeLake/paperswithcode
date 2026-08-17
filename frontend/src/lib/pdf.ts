import { pdfjs } from "react-pdf";

import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjs };

export function assertPdfWorkerConfigured(): void {
  if (!pdfjs.GlobalWorkerOptions.workerSrc) {
    throw new Error("The bundled PDF worker is not configured.");
  }
  if (pdfjs.version !== "4.8.69") {
    throw new Error(`PDF runtime version mismatch (${pdfjs.version}).`);
  }
}
