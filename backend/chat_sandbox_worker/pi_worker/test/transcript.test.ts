import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";
import { TranscriptMirror } from "../src/transcript.js";

test("mirror advances each append batch only to a leaf contained in that batch", async () => {
  const requests: Record<string, unknown>[] = [];
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", () => {
      requests.push(JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>);
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end('{"result":{}}');
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(8765, "127.0.0.1", resolve).once("error", reject));
  try {
    const mirror = new TranscriptMirror("00000000-0000-4000-8000-000000000001", 0, null);
    mirror.append({ type: "session", id: "00000000-0000-4000-8000-000000000001" });
    for (let index = 1; index <= 64; index += 1) {
      mirror.append({ type: "message", id: `entry-${index}`, parentId: index === 1 ? null : `entry-${index - 1}` });
    }
    await mirror.flush();
    assert.equal(requests.length, 2);
    assert.equal(requests[0]?.current_leaf_id, "entry-63");
    assert.equal(requests[1]?.current_leaf_id, "entry-64");
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
