import type { RunResult } from "./types";

export function contentToText(content: unknown): string {
  if (content == null) return "";
  if (typeof content === "string") {
    return content.replace(/\\n/g, "\n").trim();
  }
  if (Array.isArray(content)) {
    return content.map((x) => String(x)).join("\n");
  }
  return JSON.stringify(content, null, 2);
}

export function contentToMarkdown(content: unknown, title = "Graph of Thoughts output"): string {
  const body = contentToText(content);
  const looksBullets = body.split("\n").some((ln) => /^\s*[-*•]/.test(ln));
  const rendered = looksBullets
    ? body
    : body
        .split("\n")
        .filter(Boolean)
        .map((ln) => `- ${ln}`)
        .join("\n");
  return `# ${title}\n\n${rendered}\n`;
}

export function downloadFile(filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportResult(result: RunResult, ext: "txt" | "md"): void {
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const task = result.task ?? "got";
  const title = `GoT ${task} · ${stamp}`;
  if (ext === "md") {
    downloadFile(
      `${task}-merged-${stamp}.md`,
      contentToMarkdown(result.final_content, title),
      "text/markdown;charset=utf-8"
    );
    return;
  }
  downloadFile(
    `${task}-merged-${stamp}.txt`,
    contentToText(result.final_content),
    "text/plain;charset=utf-8"
  );
}
